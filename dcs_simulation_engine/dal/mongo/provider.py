"""MongoDB implementation of DataProvider."""

from typing import Any, Optional

from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    DataProvider,
    PlayerRecord,
    RunRecord,
)
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)
from dcs_simulation_engine.dal.mongo.util import (
    now,
    player_doc_to_record,
    player_id_variants,
    sanitize_player_data,
    save_run_data,
    split_pii,
    write_pii_fields,
)
from dcs_simulation_engine.utils.auth import (
    generate_access_key,
)
from loguru import logger
from pymongo.database import Database

_KEY_PREFIX_LEN = 12


def _to_character_record(doc: dict[str, Any]) -> CharacterRecord:
    known = {"hid", "_id", "name", "short_description"}
    return CharacterRecord(
        hid=doc.get("hid", ""),
        name=doc.get("name", ""),
        short_description=doc.get("short_description", ""),
        data={k: v for k, v in doc.items() if k not in known},
    )


class MongoProvider(DataProvider):
    """DataProvider backed by MongoDB."""

    def __init__(self, db: Database[Any]) -> None:
        """Bind the provider to the given MongoDB database handle."""
        self._db = db

    def get_db(self) -> Database[Any]:
        """Return the active Mongo database handle."""
        return self._db

    def get_characters(self, *, hid: str | None = None) -> list[CharacterRecord] | CharacterRecord:
        """Return all characters, or a single character if hid is given."""
        if hid is not None:
            logger.debug(f"Loading character by hid='{hid}'")
            doc = self._db[MongoColumns.CHARACTERS].find_one({"hid": hid}, projection={"_id": 0})
            if not doc:
                raise ValueError(f"Character with hid='{hid}' not found")
            return _to_character_record(doc)

        return self.list_characters()

    def list_characters(self) -> list[CharacterRecord]:
        """Return all characters."""
        docs = self._db[MongoColumns.CHARACTERS].find({}, projection={"_id": 0})
        return [_to_character_record(doc) for doc in docs]

    def get_player(self, *, player_id: str) -> PlayerRecord | None:
        """Return a single player by id, or None if no match exists."""
        ids = player_id_variants(player_id)
        if not ids:
            return None
        doc = self._db[MongoColumns.PLAYERS].find_one({"$or": [{"_id": pid} for pid in ids]})
        if not doc:
            return None
        doc["id"] = str(doc.pop("_id"))
        return player_doc_to_record(doc)

    def list_runs(
        self,
        *,
        player_id: str | None = None,
        game_name: str | None = None,
    ) -> list[RunRecord]:
        """Return runs optionally filtered by player and game."""
        clauses: list[dict[str, Any]] = []

        if player_id is not None:
            ids = player_id_variants(player_id)
            if not ids:
                return []
            clauses.append({"$or": [{"player_id": pid} for pid in ids]})

        if game_name is not None:
            clauses.append(
                {
                    "$or": [
                        {"game_name": game_name},
                        {"game_config.name": game_name},
                    ]
                }
            )

        if not clauses:
            filt: dict[str, Any] = {}
        elif len(clauses) == 1:
            filt = clauses[0]
        else:
            filt = {"$and": clauses}

        known = {"id", "_id", "player_id", "created_at", "game_name"}
        out: list[RunRecord] = []

        for doc in self._db[MongoColumns.RUNS].find(filt):
            doc_id = str(doc.pop("_id"))
            inferred_game_name = doc.get("game_name")
            if not inferred_game_name and isinstance(doc.get("game_config"), dict):
                inferred_game_name = doc["game_config"].get("name", "")
            data = {k: v for k, v in doc.items() if k not in known}
            npc_hid = data.get("npc_hid")
            if not (isinstance(npc_hid, str) and npc_hid):
                context = data.get("context")
                if isinstance(context, dict):
                    npc = context.get("npc")
                    if isinstance(npc, dict):
                        legacy_hid = npc.get("hid")
                        if isinstance(legacy_hid, str) and legacy_hid:
                            data["npc_hid"] = legacy_hid

            out.append(
                RunRecord(
                    id=doc_id,
                    player_id=str(doc.get("player_id", "")),
                    game_name=str(inferred_game_name or ""),
                    created_at=doc.get(MongoColumns.CREATED_AT),
                    data=data,
                )
            )

        return out

    def create_player(
        self,
        *,
        player_data: dict[str, Any],
        player_id: str | None = None,
        issue_access_key: bool = False,
    ) -> tuple[PlayerRecord, str | None]:
        """Create or upsert a player, optionally issuing a raw access key."""
        sanitized = sanitize_player_data(player_data)

        raw_key: str | None = None
        if issue_access_key:
            raw_key = generate_access_key()
            sanitized.update(
                {
                    "access_key": raw_key,
                    "access_key_revoked": False,
                    "last_key_issued_at": now(),
                }
            )

        non_pii_data, pii_fields = split_pii(sanitized)

        coll = self._db[MongoColumns.PLAYERS]
        if player_id is not None:
            coll.update_one({"_id": player_id}, {"$set": non_pii_data}, upsert=True)
            created_id = str(player_id)
        else:
            created_id = str(coll.insert_one(non_pii_data).inserted_id)

        try:
            if pii_fields:
                write_pii_fields(self._db, created_id, pii_fields)
        except Exception:
            logger.exception("Failed to write PII fields for player %s", created_id)

        doc = dict(non_pii_data)
        doc["id"] = created_id
        record = player_doc_to_record(doc)
        logger.info("Created/updated player: %s (issued_key=%s)", created_id, bool(raw_key))
        return record, raw_key

    def get_players(self, *, access_key: str | None = None) -> list[PlayerRecord] | PlayerRecord | None:
        """Return all players, or one player matching a raw access key."""
        if access_key is not None:
            key = access_key.strip()
            if not key:
                return None
            try:
                coll = self._db[MongoColumns.PLAYERS]
                doc = coll.find_one(
                    {
                        "access_key": key,
                        "access_key_revoked": {"$ne": True},
                    },
                    projection={"access_key": 0},
                )
                if doc:
                    doc["id"] = str(doc.pop("_id"))
                    return player_doc_to_record(doc)
            except Exception as exc:
                logger.error("get_players(access_key=...) failed: %s", exc)
            return None

        players = []
        for doc in self._db[MongoColumns.PLAYERS].find({}, projection={"access_key": 0}):
            doc["id"] = str(doc.pop("_id"))
            players.append(player_doc_to_record(doc))
        return players

    def save_run(
        self,
        player_id: str,
        run_data: dict[str, Any],
        *,
        run_id: Optional[str] = None,
    ) -> RunRecord:
        """Persist a run and return its RunRecord."""
        run_id_str = save_run_data(self._db, player_id, run_data, run_id=run_id)
        game_name = run_data.get("game_name")
        if not game_name and isinstance(run_data.get("game_config"), dict):
            game_name = run_data["game_config"].get("name", "")

        return RunRecord(
            id=run_id_str,
            player_id=str(player_id),
            game_name=str(game_name or ""),
            created_at=run_data.get(MongoColumns.CREATED_AT),
            data={k: v for k, v in run_data.items() if k not in (MongoColumns.CREATED_AT, "game_name")},
        )

    def get_runs(self) -> list[RunRecord]:
        """Return all runs as RunRecords."""
        return self.list_runs()

    def upsert_character(self, data: dict[str, Any], *, character_id: str | None = None) -> str:
        """Create or update a character. Returns the character's hid or inserted id."""
        if not isinstance(data, dict):
            raise ValueError("data must be a dict")
        doc = dict(data)
        doc.setdefault(MongoColumns.CREATED_AT, now())
        coll = self._db[MongoColumns.CHARACTERS]
        hid = character_id or doc.get("hid")
        if hid:
            coll.update_one({"hid": hid}, {"$set": doc}, upsert=True)
            return str(hid)
        result = coll.insert_one(doc)
        return str(result.inserted_id)

    def delete_character(self, character_id: str) -> None:
        """Delete a character by hid."""
        self._db[MongoColumns.CHARACTERS].delete_one({"hid": character_id})

    def delete_player(self, player_id: str) -> None:
        """Delete a player by id (string or ObjectId)."""
        ids = player_id_variants(player_id)
        if not ids:
            return
        filt = {"$or": [{"_id": pid} for pid in ids]}
        self._db[MongoColumns.PLAYERS].delete_one(filt)
