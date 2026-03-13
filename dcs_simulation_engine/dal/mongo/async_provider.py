"""Async MongoDB implementation for runtime server paths."""
# ruff: noqa: D102,D107

from datetime import datetime
from typing import Any

from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    PlayerRecord,
    SessionEventRecord,
    SessionRecord,
)
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)
from dcs_simulation_engine.dal.mongo.util import (
    player_doc_to_record,
    player_id_variants,
    sanitize_player_data,
    split_pii,
)
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.auth import generate_access_key
from dcs_simulation_engine.utils.time import utc_now


async def _cursor_to_docs(cursor: Any) -> list[dict[str, Any]]:
    """Convert a sync/async cursor into a plain list of documents."""
    if hasattr(cursor, "__aiter__"):
        return [doc async for doc in cursor]
    return list(cursor)


def _to_character_record(doc: dict[str, Any]) -> CharacterRecord:
    """Map raw Mongo character doc to CharacterRecord."""
    known = {"hid", "_id", "name", "short_description"}

    return CharacterRecord(
        hid=doc.get("hid", ""),
        name=doc.get("name", ""),
        short_description=doc.get("short_description", ""),
        data={k: v for k, v in doc.items() if k not in known},
    )


def _to_session_record(doc: dict[str, Any]) -> SessionRecord:
    known = {
        MongoColumns.ID,
        MongoColumns.SESSION_ID,
        MongoColumns.PLAYER_ID,
        MongoColumns.GAME_NAME,
        MongoColumns.STATUS,
        MongoColumns.CREATED_AT,
    }
    return SessionRecord(
        session_id=str(doc.get(MongoColumns.SESSION_ID, "")),
        player_id=str(doc.get(MongoColumns.PLAYER_ID, "")),
        game_name=str(doc.get(MongoColumns.GAME_NAME, "")),
        status=str(doc.get(MongoColumns.STATUS, "")),
        created_at=doc.get(MongoColumns.CREATED_AT),
        data={k: v for k, v in doc.items() if k not in known},
    )


def _to_session_event_record(doc: dict[str, Any]) -> SessionEventRecord:
    known = {
        MongoColumns.ID,
        MongoColumns.SESSION_ID,
        MongoColumns.SEQ,
        MongoColumns.EVENT_ID,
        MongoColumns.EVENT_TS,
        MongoColumns.DIRECTION,
        MongoColumns.KIND,
        MongoColumns.ROLE,
        MongoColumns.CONTENT,
    }
    return SessionEventRecord(
        session_id=str(doc.get(MongoColumns.SESSION_ID, "")),
        seq=int(doc.get(MongoColumns.SEQ, 0)),
        event_id=str(doc.get(MongoColumns.EVENT_ID, "")),
        event_ts=doc.get(MongoColumns.EVENT_TS),
        direction=str(doc.get(MongoColumns.DIRECTION, "")),
        kind=str(doc.get(MongoColumns.KIND, "")),
        role=str(doc.get(MongoColumns.ROLE, "")),
        content=str(doc.get(MongoColumns.CONTENT, "")),
        data={k: v for k, v in doc.items() if k not in known},
    )


class AsyncMongoProvider:
    """Async provider backed by PyMongo AsyncMongoClient."""

    def __init__(self, db: Any) -> None:
        # We inject the database instance rather than creating it here.
        # This makes the class easily testable (you can pass in a mock database).
        self._db = db

    def get_db(self) -> Any:
        return self._db

    async def get_characters(self, *, hid: str | None = None) -> list[CharacterRecord] | CharacterRecord:
        """Fetch a specific character by ID, or list all of them if no ID is provided."""
        if hid is not None:
            # projection={"_id": 0} tells Mongo to NOT return its internal ObjectId.
            # We do this because ObjectIds often aren't JSON serializable by default.
            doc = await maybe_await(self._db[MongoColumns.CHARACTERS].find_one({"hid": hid}, projection={"_id": 0}))
            if not doc:
                raise ValueError(f"Character with hid='{hid}' not found")
            return _to_character_record(doc)

        # If no 'hid' was provided, fall back to fetching everything.
        return await self.list_characters()

    async def get_character(self, *, hid: str) -> CharacterRecord:
        """Strict version of get_characters that guarantees a single record is returned."""
        result = await self.get_characters(hid=hid)
        if not isinstance(result, CharacterRecord):
            raise ValueError(f"Character with hid='{hid}' not found")
        return result

    async def list_characters(self) -> list[CharacterRecord]:
        """Fetch all character records from the database."""
        # Find with an empty query `{}` means "get everything".
        cursor = self._db[MongoColumns.CHARACTERS].find({}, projection={"_id": 0})
        docs = await _cursor_to_docs(cursor)
        return [_to_character_record(doc) for doc in docs]

    async def get_player(self, *, player_id: str) -> PlayerRecord | None:
        """Look up a player by their ID."""
        # player_id_variants likely handles the fact that an ID could be stored
        # as a raw string or an ObjectId in the database.
        ids = player_id_variants(player_id)
        if not ids:
            return None

        # $or is a Mongo operator: "Find a document where _id matches ANY of the IDs in this list."
        doc = await maybe_await(self._db[MongoColumns.PLAYERS].find_one({"$or": [{"_id": pid} for pid in ids]}))
        if not doc:
            return None

        # Rename the internal Mongo '_id' to a standard 'id' for the application to use.
        # .pop() removes it from the dict and returns the value at the same time.
        doc["id"] = str(doc.pop("_id"))
        return player_doc_to_record(doc)

    async def create_player(
        self,
        *,
        player_data: dict[str, Any],
        player_id: str | None = None,
        issue_access_key: bool = False,
    ) -> tuple[PlayerRecord, str | None]:
        """Create or update a player, optionally issuing them a new access key."""
        sanitized = sanitize_player_data(player_data)
        raw_key: str | None = None

        # Security/Auth logic: Generate a token if requested.
        if issue_access_key:
            raw_key = generate_access_key()
            sanitized.update(
                {
                    "access_key": raw_key,
                    "access_key_revoked": False,
                    "last_key_issued_at": utc_now(),
                }
            )

        # SECURITY BEST PRACTICE: Split PII (Personally Identifiable Information like emails/names)
        # away from standard gameplay data. This makes GDPR compliance and data deletion much easier.
        non_pii_data, pii_fields = split_pii(sanitized)
        coll = self._db[MongoColumns.PLAYERS]

        if player_id is not None:
            # upsert=True means "Update this document if it exists. If it doesn't, create it."
            # $set ensures we only update the fields provided, leaving other existing fields alone.
            await maybe_await(coll.update_one({"_id": player_id}, {"$set": non_pii_data}, upsert=True))
            created_id = str(player_id)
        else:
            # If no ID was provided, just insert it and let Mongo generate a new ObjectId.
            created_id = str((await maybe_await(coll.insert_one(non_pii_data))).inserted_id)

        # Store the sensitive PII data in an entirely different database collection.
        if pii_fields:
            await maybe_await(
                self._db[MongoColumns.PII].update_one(
                    {"player_id": created_id},
                    {
                        "$set": {
                            "player_id": created_id,
                            "fields": pii_fields,
                            "updated_at": utc_now(),
                        },
                        # $setOnInsert is a cool Mongo feature: this field is ONLY written
                        # if the document is being created for the first time, ignored on updates.
                        "$setOnInsert": {"created_at": utc_now()},
                    },
                    upsert=True,
                )
            )

        # Reconstruct a complete domain model to return to the application.
        doc = dict(non_pii_data)
        doc["id"] = created_id
        return player_doc_to_record(doc), raw_key

    async def get_players(self, *, access_key: str | None = None) -> list[PlayerRecord] | PlayerRecord | None:
        """Fetch all players, or specifically authenticate and fetch one by access_key."""
        if access_key is not None:
            key = access_key.strip()
            if not key:
                return None

            # $ne means "Not Equal". Find the user with this key, where revoked is NOT True.
            doc = await maybe_await(
                self._db[MongoColumns.PLAYERS].find_one(
                    {"access_key": key, "access_key_revoked": {"$ne": True}},
                    projection={"access_key": 0},  # Never return the key back out in the results
                )
            )
            if not doc:
                return None
            doc["id"] = str(doc.pop("_id"))
            return player_doc_to_record(doc)

        out: list[PlayerRecord] = []
        cursor = self._db[MongoColumns.PLAYERS].find({}, projection={"access_key": 0})
        for doc in await _cursor_to_docs(cursor):
            doc["id"] = str(doc.pop("_id"))
            out.append(player_doc_to_record(doc))
        return out

    async def upsert_character(self, data: dict[str, Any], *, character_id: str | None = None) -> str:
        """Create a new character or update an existing one."""
        if not isinstance(data, dict):
            raise ValueError("data must be a dict")

        doc = dict(data)
        # setdefault only applies the timestamp if 'created_at' isn't already in the dict.
        doc.setdefault(MongoColumns.CREATED_AT, utc_now())

        coll = self._db[MongoColumns.CHARACTERS]
        hid = character_id or doc.get("hid")

        if hid:
            await maybe_await(coll.update_one({"hid": hid}, {"$set": doc}, upsert=True))
            return str(hid)

        result = await maybe_await(coll.insert_one(doc))
        return str(result.inserted_id)

    async def delete_character(self, character_id: str) -> None:
        """Remove a character by ID."""
        await maybe_await(self._db[MongoColumns.CHARACTERS].delete_one({"hid": character_id}))

    async def delete_player(self, player_id: str) -> None:
        """Remove a player by ID, checking all variant ID types."""
        ids = player_id_variants(player_id)
        if not ids:
            return
        await maybe_await(self._db[MongoColumns.PLAYERS].delete_one({"$or": [{"_id": pid} for pid in ids]}))

    async def create_session(self, session_doc: dict[str, Any]) -> None:
        """Log the start of a new game/app session."""
        await maybe_await(self._db[MongoColumns.SESSIONS].insert_one(session_doc))

    async def finalize_session(
        self,
        *,
        session_id: str,
        termination_reason: str,
        status: str,
        session_ended_at: datetime,
        session_ended_at_ns: int,
        turns_completed: int,
        last_seq: int,
    ) -> None:
        """Update a session record with final metrics when it ends."""
        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "termination_reason": termination_reason,
                        "status": status,
                        "session_ended_at": session_ended_at,
                        "session_ended_at_ns": session_ended_at_ns,  # Nanosecond precision tracking
                        "turns_completed": turns_completed,
                        "last_seq": last_seq,
                        "updated_at": utc_now(),
                    }
                },
            )
        )

    async def get_session(self, *, session_id: str, player_id: str) -> SessionRecord | None:
        """Return a single persisted session record for the player."""
        doc = await maybe_await(
            self._db[MongoColumns.SESSIONS].find_one(
                {
                    MongoColumns.SESSION_ID: session_id,
                    MongoColumns.PLAYER_ID: player_id,
                }
            )
        )
        if not doc:
            return None
        return _to_session_record(doc)

    async def list_session_events(self, *, session_id: str) -> list[SessionEventRecord]:
        """Return all persisted session events in sequence order."""
        cursor = self._db[MongoColumns.SESSION_EVENTS].find({MongoColumns.SESSION_ID: session_id})
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter(MongoColumns.SEQ, 1)
        docs = await _cursor_to_docs(cursor)
        return [_to_session_event_record(doc) for doc in docs]

    async def get_session_reconstruction(
        self,
        *,
        session_id: str,
        player_id: str,
    ) -> dict[str, Any] | None:
        """Return session metadata and ordered event stream for replay."""
        # 1. Fetch the parent session record
        session_doc = await maybe_await(
            self._db[MongoColumns.SESSIONS].find_one(
                {"session_id": session_id, "player_id": player_id},
                projection={"_id": 0},
            )
        )
        if not session_doc:
            return None

        # 2. Fetch all individual events tied to this session
        events: list[dict[str, Any]] = []
        cursor = self._db[MongoColumns.SESSION_EVENTS].find(
            {"session_id": session_id},
            projection={"_id": 0},
        )

        # 3. Ensure the events are sorted by their sequence number ('seq') in ascending order (1).
        # This guarantees they are replayed in the exact order they occurred.
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter("seq", 1)

        events.extend(await _cursor_to_docs(cursor))

        # Return both parts together
        return {"session": session_doc, "events": events}
