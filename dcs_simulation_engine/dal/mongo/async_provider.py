"""Async MongoDB implementation for runtime server paths."""
# ruff: noqa: D102,D107

from datetime import datetime
from typing import Any
from uuid import uuid4

from dcs_simulation_engine.dal.base import (
    AssignmentRecord,
    CharacterRecord,
    ExperimentRecord,
    PlayerFormsRecord,
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
from dcs_simulation_engine.utils.auth import generate_access_key, validate_access_key
from dcs_simulation_engine.utils.time import utc_now


async def _cursor_to_docs(cursor: Any) -> list[dict[str, Any]]:
    """Convert a sync/async cursor into a plain list of documents."""
    if hasattr(cursor, "__aiter__"):
        return [doc async for doc in cursor]
    return list(cursor)


ACTIVE_ASSIGNMENT_STATUSES = {"assigned", "in_progress", "interrupted"}


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
        player_id=(None if doc.get(MongoColumns.PLAYER_ID) is None else str(doc.get(MongoColumns.PLAYER_ID))),
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
        MongoColumns.EVENT_TYPE,
        MongoColumns.EVENT_SOURCE,
        MongoColumns.CONTENT,
    }
    return SessionEventRecord(
        session_id=str(doc.get(MongoColumns.SESSION_ID, "")),
        seq=int(doc.get(MongoColumns.SEQ, 0)),
        event_id=str(doc.get(MongoColumns.EVENT_ID, "")),
        event_ts=doc.get(MongoColumns.EVENT_TS),
        direction=str(doc.get(MongoColumns.DIRECTION, "")),
        event_type=str(doc.get(MongoColumns.EVENT_TYPE, "")),
        event_source=str(doc.get(MongoColumns.EVENT_SOURCE, "")),
        content=str(doc.get(MongoColumns.CONTENT, "")),
        data={k: v for k, v in doc.items() if k not in known},
    )


def _to_experiment_record(doc: dict[str, Any]) -> ExperimentRecord:
    known = {
        MongoColumns.ID,
        MongoColumns.NAME,
        MongoColumns.CREATED_AT,
        MongoColumns.UPDATED_AT,
    }
    return ExperimentRecord(
        name=str(doc.get(MongoColumns.NAME, "")),
        created_at=doc.get(MongoColumns.CREATED_AT),
        updated_at=doc.get(MongoColumns.UPDATED_AT),
        data={k: v for k, v in doc.items() if k not in known},
    )


def _to_assignment_record(doc: dict[str, Any]) -> AssignmentRecord:
    known = {
        MongoColumns.ID,
        MongoColumns.ASSIGNMENT_ID,
        MongoColumns.EXPERIMENT_NAME,
        MongoColumns.PLAYER_ID,
        MongoColumns.GAME_NAME,
        MongoColumns.PC_HID,
        MongoColumns.NPC_HID,
        MongoColumns.STATUS,
        "assigned_at",
    }
    return AssignmentRecord(
        assignment_id=str(doc.get(MongoColumns.ASSIGNMENT_ID, "")),
        experiment_name=str(doc.get(MongoColumns.EXPERIMENT_NAME, "")),
        player_id=str(doc.get(MongoColumns.PLAYER_ID, "")),
        game_name=str(doc.get(MongoColumns.GAME_NAME, "")),
        pc_hid=str(doc.get(MongoColumns.PC_HID, "")),
        npc_hid=str(doc.get(MongoColumns.NPC_HID, "")),
        status=str(doc.get(MongoColumns.STATUS, "")),
        assigned_at=doc.get("assigned_at"),
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
        access_key: str | None = None,
    ) -> tuple[PlayerRecord, str | None]:
        """Create or update a player, optionally issuing them a new access key."""
        sanitized = sanitize_player_data(player_data)
        raw_key: str | None = None

        if issue_access_key and access_key is not None:
            raise ValueError("Use either issue_access_key=True or an explicit access_key, not both.")

        if access_key is not None:
            raw_key = validate_access_key(access_key)
            sanitized.update(
                {
                    "access_key": raw_key,
                    "access_key_revoked": False,
                    "last_key_issued_at": utc_now(),
                }
            )
        elif issue_access_key:
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
                        "turns_completed": turns_completed,
                        "last_seq": last_seq,
                        "updated_at": utc_now(),
                    }
                },
            )
        )

    async def pause_session(self, *, session_id: str, paused_at: datetime) -> None:
        """Update a session record to reflect it is paused and awaiting resume."""
        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "status": "paused",
                        "paused_at": paused_at,
                        "updated_at": utc_now(),
                    }
                },
            )
        )

    async def resume_session(self, *, session_id: str, resumed_at: datetime) -> None:
        """Update a session record to reflect it has been resumed."""
        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "status": "active",
                        "resumed_at": resumed_at,
                        "updated_at": utc_now(),
                    },
                    "$unset": {"paused_at": ""},
                },
            )
        )

    async def get_session(self, *, session_id: str, player_id: str | None) -> SessionRecord | None:
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

    async def save_runtime_state(self, *, session_id: str, runtime_state: dict) -> None:
        """Upsert the resumable runtime snapshot on a session document."""
        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {MongoColumns.SESSION_ID: session_id},
                {
                    "$set": {
                        MongoColumns.RUNTIME_STATE: runtime_state,
                        MongoColumns.UPDATED_AT: utc_now(),
                    }
                },
            )
        )

    async def get_resumable_session(
        self,
        *,
        player_id: str,
        game_name: str,
        pc_hid: str,
        npc_hid: str,
    ) -> SessionRecord | None:
        """Return the most recent paused session for this player/game/character combo."""
        cursor = self._db[MongoColumns.SESSIONS].find(
            {
                MongoColumns.PLAYER_ID: player_id,
                MongoColumns.GAME_NAME: game_name,
                MongoColumns.PC_HID: pc_hid,
                MongoColumns.NPC_HID: npc_hid,
                MongoColumns.STATUS: "paused",
            }
        )
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter(MongoColumns.UPDATED_AT, -1)
        docs = await _cursor_to_docs(cursor)
        if not docs:
            return None
        return _to_session_record(docs[0])

    async def list_session_events(self, *, session_id: str) -> list[SessionEventRecord]:
        """Return all persisted session events in sequence order."""
        cursor = self._db[MongoColumns.SESSION_EVENTS].find({MongoColumns.SESSION_ID: session_id})
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter(MongoColumns.SEQ, 1)
        docs = await _cursor_to_docs(cursor)
        return [_to_session_event_record(doc) for doc in docs]

    async def append_session_event(
        self,
        *,
        session_id: str,
        player_id: str | None,
        direction: str,
        event_type: str,
        event_source: str,
        content: str,
        content_format: str,
        turn_index: int,
        visible_to_user: bool,
    ) -> SessionEventRecord | None:
        """Append one owned session event and advance the parent session sequence counter."""
        session_doc = await maybe_await(
            self._db[MongoColumns.SESSIONS].find_one(
                {
                    MongoColumns.SESSION_ID: session_id,
                    MongoColumns.PLAYER_ID: player_id,
                },
                projection={
                    MongoColumns.SESSION_ID: 1,
                    MongoColumns.LAST_SEQ: 1,
                },
            )
        )
        if not session_doc:
            return None

        last_seq = int(session_doc.get(MongoColumns.LAST_SEQ, 0) or 0)
        next_seq = last_seq + 1
        now = utc_now()
        event_id = str(uuid4())
        doc = {
            MongoColumns.SESSION_ID: session_id,
            MongoColumns.SEQ: next_seq,
            MongoColumns.EVENT_ID: event_id,
            MongoColumns.EVENT_TS: now,
            MongoColumns.DIRECTION: direction,
            MongoColumns.EVENT_TYPE: event_type,
            MongoColumns.EVENT_SOURCE: event_source,
            MongoColumns.CONTENT: content,
            MongoColumns.CONTENT_FORMAT: content_format,
            MongoColumns.TURN_INDEX: turn_index,
            MongoColumns.VISIBLE_TO_USER: visible_to_user,
            MongoColumns.PERSISTED_AT: now,
            MongoColumns.UPDATED_AT: now,
        }
        await maybe_await(self._db[MongoColumns.SESSION_EVENTS].insert_one(doc))
        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {MongoColumns.SESSION_ID: session_id},
                {
                    "$set": {
                        MongoColumns.LAST_SEQ: next_seq,
                        MongoColumns.UPDATED_AT: now,
                    }
                },
            )
        )
        return _to_session_event_record(doc)

    async def set_session_event_feedback(
        self,
        *,
        session_id: str,
        player_id: str | None,
        event_id: str,
        feedback: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Store feedback on one persisted NPC message event owned by the player."""
        session_doc = await maybe_await(
            self._db[MongoColumns.SESSIONS].find_one(
                {
                    MongoColumns.SESSION_ID: session_id,
                    MongoColumns.PLAYER_ID: player_id,
                },
                projection={MongoColumns.SESSION_ID: 1},
            )
        )
        if not session_doc:
            return None

        now = utc_now()
        result = await maybe_await(
            self._db[MongoColumns.SESSION_EVENTS].update_one(
                {
                    MongoColumns.SESSION_ID: session_id,
                    MongoColumns.EVENT_ID: event_id,
                    MongoColumns.DIRECTION: "outbound",
                    MongoColumns.EVENT_TYPE: "message",
                    MongoColumns.EVENT_SOURCE: "npc",
                },
                {
                    "$set": {
                        MongoColumns.FEEDBACK: dict(feedback),
                        MongoColumns.UPDATED_AT: now,
                    }
                },
            )
        )
        if getattr(result, "matched_count", 0) == 0:
            return None

        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {MongoColumns.SESSION_ID: session_id},
                {"$set": {MongoColumns.UPDATED_AT: now}},
            )
        )
        return dict(feedback)

    async def clear_session_event_feedback(
        self,
        *,
        session_id: str,
        player_id: str | None,
        event_id: str,
    ) -> bool:
        """Remove feedback from one persisted NPC message event owned by the player."""
        session_doc = await maybe_await(
            self._db[MongoColumns.SESSIONS].find_one(
                {
                    MongoColumns.SESSION_ID: session_id,
                    MongoColumns.PLAYER_ID: player_id,
                },
                projection={MongoColumns.SESSION_ID: 1},
            )
        )
        if not session_doc:
            return False

        now = utc_now()
        result = await maybe_await(
            self._db[MongoColumns.SESSION_EVENTS].update_one(
                {
                    MongoColumns.SESSION_ID: session_id,
                    MongoColumns.EVENT_ID: event_id,
                    MongoColumns.DIRECTION: "outbound",
                    MongoColumns.EVENT_TYPE: "message",
                    MongoColumns.EVENT_SOURCE: "npc",
                },
                {
                    "$unset": {
                        MongoColumns.FEEDBACK: "",
                    },
                    "$set": {
                        MongoColumns.UPDATED_AT: now,
                    },
                },
            )
        )
        if getattr(result, "matched_count", 0) == 0:
            return False

        await maybe_await(
            self._db[MongoColumns.SESSIONS].update_one(
                {MongoColumns.SESSION_ID: session_id},
                {"$set": {MongoColumns.UPDATED_AT: now}},
            )
        )
        return True

    async def get_experiment(self, *, experiment_name: str) -> ExperimentRecord | None:
        """Return one persisted experiment record."""
        doc = await maybe_await(self._db[MongoColumns.EXPERIMENTS].find_one({MongoColumns.NAME: experiment_name}))
        if not doc:
            return None
        return _to_experiment_record(doc)

    async def upsert_experiment(
        self,
        *,
        experiment_name: str,
        description: str,
        config_snapshot: dict[str, Any],
        progress: dict[str, Any],
    ) -> ExperimentRecord:
        """Create or update an experiment metadata row."""
        now = utc_now()
        await maybe_await(
            self._db[MongoColumns.EXPERIMENTS].update_one(
                {MongoColumns.NAME: experiment_name},
                {
                    "$set": {
                        MongoColumns.NAME: experiment_name,
                        "description": description,
                        MongoColumns.CONFIG_SNAPSHOT: config_snapshot,
                        MongoColumns.PROGRESS: progress,
                        MongoColumns.UPDATED_AT: now,
                    },
                    "$setOnInsert": {MongoColumns.CREATED_AT: now},
                },
                upsert=True,
            )
        )
        record = await self.get_experiment(experiment_name=experiment_name)
        if record is None:
            raise ValueError(f"Experiment {experiment_name!r} was not persisted")
        return record

    async def set_experiment_progress(
        self,
        *,
        experiment_name: str,
        progress: dict[str, Any],
    ) -> ExperimentRecord | None:
        """Persist the latest experiment progress snapshot."""
        now = utc_now()
        await maybe_await(
            self._db[MongoColumns.EXPERIMENTS].update_one(
                {MongoColumns.NAME: experiment_name},
                {
                    "$set": {
                        MongoColumns.PROGRESS: progress,
                        MongoColumns.UPDATED_AT: now,
                    }
                },
            )
        )
        return await self.get_experiment(experiment_name=experiment_name)

    async def create_assignment(self, *, assignment_doc: dict[str, Any], allow_concurrent: bool = False) -> AssignmentRecord:
        """Persist a new experiment assignment row."""
        experiment_name = str(assignment_doc.get(MongoColumns.EXPERIMENT_NAME) or "")
        player_id = str(assignment_doc.get(MongoColumns.PLAYER_ID) or "")
        if not experiment_name or not player_id:
            raise ValueError("assignment_doc must include experiment_name and player_id")

        if not allow_concurrent:
            existing = await self.get_active_assignment(experiment_name=experiment_name, player_id=player_id)
            if existing is not None:
                raise ValueError("Player already has an active assignment for this experiment")

        now = utc_now()
        doc = dict(assignment_doc)
        doc.setdefault(MongoColumns.ASSIGNMENT_ID, str(uuid4()))
        doc.setdefault(MongoColumns.STATUS, "assigned")
        doc.setdefault("assigned_at", now)
        doc.setdefault(MongoColumns.CREATED_AT, now)
        doc[MongoColumns.UPDATED_AT] = now
        await maybe_await(self._db[MongoColumns.ASSIGNMENTS].insert_one(doc))
        record = await self.get_assignment(assignment_id=doc[MongoColumns.ASSIGNMENT_ID])
        if record is None:
            raise ValueError("Assignment insert did not persist")
        return record

    async def get_assignment(self, *, assignment_id: str) -> AssignmentRecord | None:
        """Return one assignment row by assignment_id."""
        doc = await maybe_await(self._db[MongoColumns.ASSIGNMENTS].find_one({MongoColumns.ASSIGNMENT_ID: assignment_id}))
        if not doc:
            return None
        return _to_assignment_record(doc)

    async def get_active_assignment(self, *, experiment_name: str, player_id: str) -> AssignmentRecord | None:
        """Return the current active assignment for one player in one experiment."""
        cursor = self._db[MongoColumns.ASSIGNMENTS].find(
            {
                MongoColumns.EXPERIMENT_NAME: experiment_name,
                MongoColumns.PLAYER_ID: player_id,
                MongoColumns.STATUS: {"$in": sorted(ACTIVE_ASSIGNMENT_STATUSES)},
            }
        )
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter(MongoColumns.UPDATED_AT, -1)
        docs = await _cursor_to_docs(cursor)
        if not docs:
            return None
        return _to_assignment_record(docs[0])

    async def get_assignment_for_session_id(self, *, session_id: str) -> AssignmentRecord | None:
        """Return the assignment that has this session as its active session."""
        doc = await maybe_await(self._db[MongoColumns.ASSIGNMENTS].find_one({MongoColumns.ACTIVE_SESSION_ID: session_id}))
        if not doc:
            return None
        return _to_assignment_record(doc)

    async def get_latest_experiment_assignment_for_player(self, *, player_id: str) -> AssignmentRecord | None:
        """Return the newest experiment assignment for one player."""
        cursor = self._db[MongoColumns.ASSIGNMENTS].find({MongoColumns.PLAYER_ID: player_id})
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter(MongoColumns.UPDATED_AT, -1)
        docs = await _cursor_to_docs(cursor)
        if not docs:
            return None
        return _to_assignment_record(docs[0])

    async def list_assignments(
        self,
        *,
        experiment_name: str,
        player_id: str | None = None,
        statuses: list[str] | None = None,
        game_name: str | None = None,
    ) -> list[AssignmentRecord]:
        """List assignment rows matching the requested filters."""
        query: dict[str, Any] = {MongoColumns.EXPERIMENT_NAME: experiment_name}
        if player_id is not None:
            query[MongoColumns.PLAYER_ID] = player_id
        if statuses:
            query[MongoColumns.STATUS] = {"$in": list(statuses)}
        if game_name is not None:
            query[MongoColumns.GAME_NAME] = game_name

        cursor = self._db[MongoColumns.ASSIGNMENTS].find(query)
        sorter = getattr(cursor, "sort", None)
        if callable(sorter):
            cursor = sorter("assigned_at", 1)
        docs = await _cursor_to_docs(cursor)
        return [_to_assignment_record(doc) for doc in docs]

    async def update_assignment_status(
        self,
        *,
        assignment_id: str,
        status: str,
        active_session_id: str | None = None,
    ) -> AssignmentRecord | None:
        """Update assignment status and lifecycle timestamps."""
        now = utc_now()
        updates: dict[str, Any] = {
            MongoColumns.STATUS: status,
            MongoColumns.UPDATED_AT: now,
        }
        if status == "assigned":
            updates.setdefault("assigned_at", now)
            updates[MongoColumns.ACTIVE_SESSION_ID] = None
        elif status == "in_progress":
            updates["started_at"] = now
            updates[MongoColumns.ACTIVE_SESSION_ID] = active_session_id
        elif status == "completed":
            updates["completed_at"] = now
            updates[MongoColumns.ACTIVE_SESSION_ID] = None
        elif status == "interrupted":
            updates["interrupted_at"] = now
            updates[MongoColumns.ACTIVE_SESSION_ID] = None

        await maybe_await(
            self._db[MongoColumns.ASSIGNMENTS].update_one(
                {MongoColumns.ASSIGNMENT_ID: assignment_id},
                {"$set": updates},
            )
        )
        return await self.get_assignment(assignment_id=assignment_id)

    async def set_assignment_form_response(
        self,
        *,
        assignment_id: str,
        form_key: str,
        response: dict[str, Any],
    ) -> AssignmentRecord | None:
        """Store one form response payload on an assignment row."""
        await maybe_await(
            self._db[MongoColumns.ASSIGNMENTS].update_one(
                {MongoColumns.ASSIGNMENT_ID: assignment_id},
                {
                    "$set": {
                        f"{MongoColumns.FORM_RESPONSES}.{form_key}": response,
                        MongoColumns.UPDATED_AT: utc_now(),
                    }
                },
            )
        )
        return await self.get_assignment(assignment_id=assignment_id)

    async def set_player_form_response(
        self,
        *,
        player_id: str,
        experiment_name: str,
        form_key: str,
        response: dict[str, Any],
    ) -> PlayerFormsRecord | None:
        """Upsert one before-play form response into the forms collection."""
        now = utc_now()
        await maybe_await(
            self._db[MongoColumns.FORMS].update_one(
                {MongoColumns.PLAYER_ID: player_id, MongoColumns.EXPERIMENT_NAME: experiment_name},
                {
                    "$set": {f"data.{form_key}": response, MongoColumns.UPDATED_AT: now},
                    "$setOnInsert": {
                        MongoColumns.PLAYER_ID: player_id,
                        MongoColumns.EXPERIMENT_NAME: experiment_name,
                        MongoColumns.CREATED_AT: now,
                    },
                },
                upsert=True,
            )
        )
        return await self.get_player_forms(player_id=player_id, experiment_name=experiment_name)

    async def get_player_forms(
        self,
        *,
        player_id: str,
        experiment_name: str,
    ) -> PlayerFormsRecord | None:
        """Return the before-play form responses for a player in an experiment."""
        doc = await maybe_await(
            self._db[MongoColumns.FORMS].find_one({MongoColumns.PLAYER_ID: player_id, MongoColumns.EXPERIMENT_NAME: experiment_name})
        )
        if not doc:
            return None
        return PlayerFormsRecord(
            player_id=doc[MongoColumns.PLAYER_ID],
            experiment_name=doc[MongoColumns.EXPERIMENT_NAME],
            data=doc.get("data", {}),
            created_at=doc.get(MongoColumns.CREATED_AT),
            updated_at=doc.get(MongoColumns.UPDATED_AT),
        )

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
