"""Session event persistence for deterministic transcript reconstruction."""
# ruff: noqa: D102,D105,D107

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any, NamedTuple
from uuid import uuid4

from dcs_simulation_engine.dal.mongo.async_writer import AsyncMongoWriter
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger
from pymongo.asynchronous.database import AsyncDatabase

if TYPE_CHECKING:
    from dcs_simulation_engine.games.ai_client import ValidationResult

_ALLOWED_EVENT_CLASSIFICATIONS = {
    ("internal", "system", "session_start"),
    ("internal", "system", "session_end"),
    ("inbound", "user", "message"),
    ("inbound", "user", "command"),
    ("outbound", "npc", "message"),
    ("outbound", "system", "command"),
    ("outbound", "system", "info"),
    ("outbound", "system", "error"),
    # Validation violations pack source+character-type into event_source:
    # pc_human, pc_llm, npc_llm.
    ("internal", "pc_human", "validation_violation"),
    ("internal", "pc_llm", "validation_violation"),
    ("internal", "npc_llm", "validation_violation"),
}


def _validate_event_classification(*, direction: str, event_source: str, event_type: str) -> None:
    if (direction, event_source, event_type) not in _ALLOWED_EVENT_CLASSIFICATIONS:
        raise ValueError(
            f"Invalid session event classification: direction={direction!r}, event_source={event_source!r}, event_type={event_type!r}"
        )


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

    async def flush_pending(self) -> None:
        """Force currently buffered event docs to Mongo."""
        await self._writer.flush()

    async def record_inbound(
        self,
        *,
        content: str,
        turn_index: int,
        event_type: str,
        command_name: str | None = None,
        command_args: str | None = None,
    ) -> "RecordedSessionEvent":
        return await self._enqueue_event(
            direction="inbound",
            event_source="user",
            event_type=event_type,
            content=content,
            content_format="plain_text",
            turn_index=turn_index,
            command_name=command_name,
            command_args=command_args,
            event_ts=None,
        )

    async def record_outbound(
        self,
        *,
        event_type: str,
        event_source: str,
        content: str,
        turn_index: int,
        command_name: str | None = None,
        command_args: str | None = None,
        event_ts: datetime | None = None,
    ) -> "RecordedSessionEvent":
        return await self._enqueue_event(
            direction="outbound",
            event_source=event_source,
            event_type=event_type,
            content=content,
            content_format="markdown",
            turn_index=turn_index,
            command_name=command_name,
            command_args=command_args,
            event_ts=event_ts,
        )

    async def record_internal(self, *, event_type: str, detail: str, turn_index: int) -> "RecordedSessionEvent":
        return await self._enqueue_event(
            direction="internal",
            event_source="system",
            event_type=event_type,
            content=f"{event_type}: {detail}",
            content_format="plain_text",
            turn_index=turn_index,
            command_name=None,
            command_args=None,
            event_ts=None,
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

        ended_at = utc_now()
        await self.record_internal(event_type="session_end", detail=termination_reason, turn_index=turns_completed)
        await self._writer.flush()
        await self._sessions_coll.update_one(
            {MongoColumns.SESSION_ID: self._session_id},
            {
                "$set": {
                    MongoColumns.STATUS: status,
                    MongoColumns.TERMINATION_REASON: termination_reason,
                    MongoColumns.SESSION_ENDED_AT: ended_at,
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
        event_source: str,
        event_type: str,
        content: str,
        content_format: str,
        turn_index: int,
        command_name: str | None,
        command_args: str | None,
        event_ts: datetime | None,
    ) -> "RecordedSessionEvent":
        _validate_event_classification(
            direction=direction,
            event_source=event_source,
            event_type=event_type,
        )
        ts = event_ts or utc_now()
        seq = self._next_seq()
        event_id = str(uuid4())
        doc = {
            MongoColumns.SESSION_ID: self._session_id,
            MongoColumns.SEQ: seq,
            MongoColumns.EVENT_ID: event_id,
            MongoColumns.EVENT_TS: ts,
            MongoColumns.DIRECTION: direction,
            MongoColumns.EVENT_TYPE: event_type,
            MongoColumns.EVENT_SOURCE: event_source,
            MongoColumns.CONTENT: content,
            MongoColumns.CONTENT_FORMAT: content_format,
            MongoColumns.TURN_INDEX: turn_index,
            MongoColumns.COMMAND_NAME: command_name,
            MongoColumns.COMMAND_ARGS: command_args,
            MongoColumns.VISIBLE_TO_USER: True,
        }
        await self._writer.enqueue(doc)
        return RecordedSessionEvent(event_id=event_id, seq=seq)

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq


class RecordedSessionEvent(NamedTuple):
    """Metadata for an event that has been queued for persistence."""

    event_id: str
    seq: int


class ValidationEventRecorder(SessionEventRecorder):
    """Sidecar recorder for validation rule violations.

    Shares seq allocation with a primary `SessionEventRecorder` so that
    the `(session_id, seq)` unique index holds across both instances.
    """

    def __init__(
        self,
        *,
        db: AsyncDatabase[Any],
        session_doc: dict[str, Any],
        primary: SessionEventRecorder,
        batch_size: int = 20,
        flush_interval_ms: int = 200,
        max_queue_size: int = 1000,
    ) -> None:
        super().__init__(
            db=db,
            session_doc=session_doc,
            batch_size=batch_size,
            flush_interval_ms=flush_interval_ms,
            max_queue_size=max_queue_size,
        )
        self._primary = primary

    async def __aenter__(self) -> "ValidationEventRecorder":
        if self._entered:
            return self
        self._entered = True
        await self._writer.__aenter__()
        return self

    async def finalize(
        self,
        *,
        termination_reason: str,
        status: str,
        turns_completed: int,
    ) -> None:
        _ = (termination_reason, status, turns_completed)
        return

    def _next_seq(self) -> int:
        self._primary._seq += 1
        return self._primary._seq

    async def record_violation(
        self,
        *,
        event_source: str,
        violation_type: str,
        violation_ensemble: str,
        response: str,
        violation_reason: str,
        turn_index: int,
    ) -> RecordedSessionEvent:
        payload = json.dumps({
            "violation_type": violation_type,
            "violation_ensemble": violation_ensemble,
            "response": response,
            "violation_reason": violation_reason,
        })
        return await self._enqueue_event(
            direction="internal",
            event_source=event_source,
            event_type="validation_violation",
            content=payload,
            content_format="json",
            turn_index=turn_index,
            command_name=None,
            command_args=None,
            event_ts=None,
        )

    async def record_ensemble_violations(
        self,
        *,
        event_source: str,
        ensemble_name: str,
        failed: list["ValidationResult"],
        response: str,
        turn_index: int,
    ) -> None:
        for r in failed:
            await self.record_violation(
                event_source=event_source,
                violation_type=r.rule,
                violation_ensemble=ensemble_name,
                response=response,
                violation_reason=r.reason,
                turn_index=turn_index,
            )
