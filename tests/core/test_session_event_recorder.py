"""Unit tests for async event persistence primitives."""
# ruff: noqa: D102,D103,D105,D107

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from dcs_simulation_engine.core.session_event_recorder import (
    SessionEventRecorder,
    _validate_event_classification,
)
from dcs_simulation_engine.dal.mongo.async_writer import AsyncMongoWriter
from dcs_simulation_engine.dal.mongo.const import MongoColumns


class _InsertOneResult:
    def __init__(self, inserted_id: str) -> None:
        self.inserted_id = inserted_id


class FakeAsyncCollection:
    """Minimal async collection emulation for unit tests."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    async def insert_many(self, docs: list[dict[str, Any]], ordered: bool = True) -> None:
        _ = ordered
        self.docs.extend(dict(doc) for doc in docs)

    async def insert_one(self, doc: dict[str, Any]) -> _InsertOneResult:
        self.docs.append(dict(doc))
        return _InsertOneResult(str(len(self.docs)))

    async def update_one(self, filt: dict[str, Any], update: dict[str, Any], upsert: bool = False) -> None:
        match_idx = None
        for idx, doc in enumerate(self.docs):
            if all(doc.get(k) == v for k, v in filt.items()):
                match_idx = idx
                break
        if match_idx is None:
            if not upsert:
                return
            base = dict(filt)
            base.update(update.get("$setOnInsert", {}))
            base.update(update.get("$set", {}))
            self.docs.append(base)
            return
        self.docs[match_idx].update(update.get("$set", {}))


class FakeAsyncDB(dict):
    """Mapping-like async DB shim keyed by collection name."""

    def __getitem__(self, key: str) -> FakeAsyncCollection:  # type: ignore[override]
        return dict.__getitem__(self, key)


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_mongo_writer_flushes_on_batch_size() -> None:
    """Writer flushes from the background loop when batch threshold is reached."""
    coll = FakeAsyncCollection()
    async with AsyncMongoWriter[dict[str, Any]](
        collection=coll,
        batch_size=2,
        flush_interval_ms=1000,
        max_queue_size=10,
    ) as writer:
        await writer.enqueue({"k": 1})
        assert len(coll.docs) == 0
        await writer.enqueue({"k": 2})
        await asyncio.sleep(0.02)
        assert len(coll.docs) == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_async_mongo_writer_flushes_on_interval() -> None:
    """Writer flushes buffered docs when periodic interval elapses."""
    coll = FakeAsyncCollection()
    async with AsyncMongoWriter[dict[str, Any]](
        collection=coll,
        batch_size=10,
        flush_interval_ms=20,
        max_queue_size=10,
    ) as writer:
        await writer.enqueue({"k": "delayed"})
        await asyncio.sleep(0.05)
        assert len(coll.docs) == 1


@pytest.mark.unit
@pytest.mark.anyio
async def test_session_event_recorder_records_sequence_and_finalize() -> None:
    """Recorder persists ordered events and finalized session metadata."""
    db = FakeAsyncDB(
        {
            MongoColumns.SESSIONS: FakeAsyncCollection(),
            MongoColumns.SESSION_EVENTS: FakeAsyncCollection(),
        }
    )
    started_at = datetime.now(timezone.utc)
    session_doc = {
        "session_id": "session-1",
        "player_id": "player-1",
        "game_name": "Explore",
        "source": "api",
        "pc_hid": "human-normative",
        "npc_hid": "flatworm",
        "session_started_at": started_at,
        "session_ended_at": None,
        "termination_reason": None,
        "status": "active",
        "turns_completed": 0,
        "model_profile": {"updater_model": "m", "validator_model": "m", "scorer_model": None},
        "game_config_snapshot": {"name": "Explore"},
        "last_seq": 0,
        "created_at": started_at,
        "updated_at": started_at,
    }

    explicit_event_ts = started_at + timedelta(microseconds=123)

    async with SessionEventRecorder(db=db, session_doc=session_doc, flush_interval_ms=10) as recorder:
        inbound = await recorder.record_inbound(
            content="/help",
            turn_index=1,
            event_type="command",
            command_name="help",
            command_args="",
        )
        info_outbound = await recorder.record_outbound(
            event_type="command",
            event_source="system",
            content="help text",
            turn_index=1,
            command_name="help",
            command_args="",
            event_ts=explicit_event_ts,
        )
        ai_outbound = await recorder.record_outbound(
            event_type="message",
            event_source="npc",
            content="scene",
            turn_index=1,
        )
        await recorder.finalize(termination_reason="user_exit_command", status="closed", turns_completed=1)

    sessions_docs = db[MongoColumns.SESSIONS].docs
    events_docs = db[MongoColumns.SESSION_EVENTS].docs

    assert len(sessions_docs) == 1
    session = sessions_docs[0]
    assert session["status"] == "closed"
    assert session["termination_reason"] == "user_exit_command"
    assert session["turns_completed"] == 1
    assert session["last_seq"] >= 4
    assert session["session_ended_at"] is not None

    assert len(events_docs) >= 4
    seqs = [doc["seq"] for doc in events_docs]
    assert seqs == sorted(seqs)
    assert events_docs[0]["direction"] == "inbound"
    assert events_docs[0]["event_type"] == "command"
    assert events_docs[0]["event_source"] == "user"
    assert events_docs[0]["event_id"] == inbound.event_id
    assert events_docs[1]["direction"] == "outbound"
    assert events_docs[1]["event_type"] == "command"
    assert events_docs[1]["event_source"] == "system"
    assert events_docs[1]["event_id"] == info_outbound.event_id
    assert events_docs[1]["event_ts"] == explicit_event_ts
    assistant_doc = next(
        doc
        for doc in events_docs
        if doc["direction"] == "outbound" and doc["event_type"] == "message" and doc["event_source"] == "npc"
    )
    assert assistant_doc["event_id"] == ai_outbound.event_id
    assert (
        any(
            doc["direction"] == "internal" and doc["event_type"] == "session_start" and doc["event_source"] == "system"
            for doc in events_docs
        )
        is False
    )
    assert any(
        doc["direction"] == "internal" and doc["event_type"] == "session_end" and doc["event_source"] == "system"
        for doc in events_docs
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("direction", "event_source", "event_type", "is_valid"),
    [
        ("internal", "system", "session_start", True),
        ("internal", "system", "session_end", True),
        ("inbound", "user", "message", True),
        ("inbound", "user", "command", True),
        ("outbound", "npc", "message", True),
        ("outbound", "system", "command", True),
        ("outbound", "system", "info", True),
        ("outbound", "system", "error", True),
        ("outbound", "npc", "info", False),
        ("inbound", "user", "error", False),
        ("internal", "system", "info", False),
    ],
)
def test_validate_event_classification_accepts_only_supported_combinations(
    direction: str,
    event_source: str,
    event_type: str,
    is_valid: bool,
) -> None:
    """Only the normalized session-event taxonomy is accepted."""
    if is_valid:
        _validate_event_classification(
            direction=direction,
            event_source=event_source,
            event_type=event_type,
        )
        return

    with pytest.raises(ValueError):
        _validate_event_classification(
            direction=direction,
            event_source=event_source,
            event_type=event_type,
        )
