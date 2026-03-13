"""Session event persistence for deterministic transcript reconstruction."""
# ruff: noqa: D102,D105,D107

import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from dcs_simulation_engine.dal.mongo.async_writer import AsyncMongoWriter
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger
from pymongo.asynchronous.database import AsyncDatabase


def _now_ns() -> int:
    return time.time_ns()


def _dt_from_ns(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=timezone.utc)


def _parse_command(text: str) -> tuple[str, str] | None:
    stripped = text.strip()
    if not stripped.startswith(("/", "\\")):
        return None
    parts = stripped.lstrip("/\\").split(maxsplit=1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""
    return (cmd, args)


class SessionEventRecorder:
    """Session-scoped persistence helper for `sessions` + `session_events`."""

    def __init__(
        self,
        *,
        db: AsyncDatabase[Any],
        session_doc: dict[str, Any],
        batch_size: int = 20,
        flush_interval_ms: int = 200,
        max_queue_size: int = 1000,
    ) -> None:
        self._db = db
        self._session_doc = dict(session_doc)
        self._session_id = str(session_doc[MongoColumns.SESSION_ID])
        self._events_coll = db[MongoColumns.SESSION_EVENTS]
        self._sessions_coll = db[MongoColumns.SESSIONS]
        self._writer = AsyncMongoWriter[dict[str, Any]](
            collection=self._events_coll,
            batch_size=batch_size,
            flush_interval_ms=flush_interval_ms,
            max_queue_size=max_queue_size,
            persisted_at_field=MongoColumns.PERSISTED_AT,
            ignore_duplicate_key_errors=True,
        )
        self._seq = 0
        self._finalized = False
        self._entered = False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def last_seq(self) -> int:
        return self._seq

    async def __aenter__(self) -> "SessionEventRecorder":
        if self._entered:
            return self
        self._entered = True
        await self._writer.__aenter__()
        await self._sessions_coll.insert_one(self._session_doc)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            await self._writer.flush()
        finally:
            await self._writer.__aexit__(exc_type, exc, tb)

    async def record_inbound(self, *, content: str, turn_index: int) -> None:
        cmd = _parse_command(content)
        if cmd is not None:
            kind = "command_input"
            command_name, command_args = cmd
        else:
            kind = "user_input"
            command_name, command_args = (None, None)
        await self._enqueue_event(
            direction="inbound",
            kind=kind,
            role="user",
            content=content,
            content_format="plain_text",
            turn_index=turn_index,
            command_name=command_name,
            command_args=command_args,
            metadata=None,
            event_ts_ns=None,
        )

    async def record_outbound(
        self,
        *,
        event_type: str,
        content: str,
        turn_index: int,
        command_context: bool,
        event_ts_ns: int | None = None,
    ) -> None:
        event_type = str(event_type or "info").lower()
        if event_type == "error":
            kind = "error_message"
            role = "system"
        elif command_context:
            kind = "command_output"
            role = "system"
        elif event_type == "ai":
            kind = "assistant_message"
            role = "assistant"
        else:
            kind = "system_message"
            role = "system"

        await self._enqueue_event(
            direction="outbound",
            kind=kind,
            role=role,
            content=content,
            content_format="markdown",
            turn_index=turn_index,
            command_name=None,
            command_args=None,
            metadata={"event_type": event_type},
            event_ts_ns=event_ts_ns,
        )

    async def record_marker(self, *, label: str, detail: str, turn_index: int) -> None:
        await self._enqueue_event(
            direction="system",
            kind="session_marker",
            role="system",
            content=f"{label}: {detail}",
            content_format="plain_text",
            turn_index=turn_index,
            command_name=None,
            command_args=None,
            metadata={"label": label},
            event_ts_ns=None,
        )

    async def finalize(
        self,
        *,
        termination_reason: str,
        status: str,
        turns_completed: int,
    ) -> None:
        if self._finalized:
            return
        self._finalized = True

        ended_ns = _now_ns()
        ended_at = _dt_from_ns(ended_ns)
        await self.record_marker(label="session_end", detail=termination_reason, turn_index=turns_completed)
        await self._writer.flush()
        await self._sessions_coll.update_one(
            {MongoColumns.SESSION_ID: self._session_id},
            {
                "$set": {
                    MongoColumns.STATUS: status,
                    MongoColumns.TERMINATION_REASON: termination_reason,
                    MongoColumns.SESSION_ENDED_AT: ended_at,
                    MongoColumns.SESSION_ENDED_AT_NS: ended_ns,
                    MongoColumns.TURNS_COMPLETED: turns_completed,
                    MongoColumns.LAST_SEQ: self._seq,
                    MongoColumns.UPDATED_AT: utc_now(),
                }
            },
        )
        logger.info("Finalized session persistence: {} ({})", self._session_id, termination_reason)

    async def _enqueue_event(
        self,
        *,
        direction: str,
        kind: str,
        role: str,
        content: str,
        content_format: str,
        turn_index: int,
        command_name: str | None,
        command_args: str | None,
        metadata: dict[str, Any] | None,
        event_ts_ns: int | None,
    ) -> None:
        ts_ns = event_ts_ns if event_ts_ns is not None else _now_ns()
        ts = _dt_from_ns(ts_ns)
        self._seq += 1
        doc = {
            MongoColumns.SESSION_ID: self._session_id,
            MongoColumns.SEQ: self._seq,
            MongoColumns.EVENT_ID: str(uuid4()),
            MongoColumns.EVENT_TS: ts,
            MongoColumns.EVENT_TS_NS: ts_ns,
            MongoColumns.DIRECTION: direction,
            MongoColumns.KIND: kind,
            MongoColumns.ROLE: role,
            MongoColumns.CONTENT: content,
            MongoColumns.CONTENT_FORMAT: content_format,
            MongoColumns.TURN_INDEX: turn_index,
            MongoColumns.COMMAND_NAME: command_name,
            MongoColumns.COMMAND_ARGS: command_args,
            MongoColumns.VISIBLE_TO_USER: True,
            MongoColumns.METADATA: metadata or {},
        }
        await self._writer.enqueue(doc)
