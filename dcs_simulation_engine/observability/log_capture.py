"""Loguru sink that captures important engine logs in Mongo."""

import hashlib
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.dal.mongo.log_events import MongoLogEventWriter
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger

_CONTROL_EXTRA_KEYS = {
    "detail",
    "persist_log",
    "throttle",
    "throttle_key",
    "throttle_seconds",
}
_CONTEXT_EXTRA_KEYS = {
    "assignment_id",
    "game_name",
    "npc_hid",
    "pc_hid",
    "player_id",
    "run_name",
    "session_id",
    "turn_index",
}
_REDACT_KEYS = {
    "access_key",
    "api_key",
    "authorization",
    "email",
    "full_name",
    "name",
    "phone",
    "phone_number",
    "token",
}


@dataclass
class _ThrottleState:
    first_seen_at: datetime
    last_seen_at: datetime
    next_emit_at: datetime
    suppressed_count: int
    last_doc: dict[str, Any]


class PersistentLogCapture:
    """Capture selected Loguru records into Mongo without blocking callers."""

    def __init__(
        self,
        *,
        db: Any,
        source: str,
        run_name: str | None = None,
        min_level_no: int = 30,
        throttle_seconds: int = 60,
        batch_size: int = 20,
        flush_interval_ms: int = 200,
        max_queue_size: int = 1000,
        max_throttle_keys: int = 2000,
    ) -> None:
        self._source = source
        self._run_name = run_name
        self._min_level_no = min_level_no
        self._default_throttle_seconds = throttle_seconds
        self._max_throttle_keys = max_queue_size if max_throttle_keys <= 0 else max_throttle_keys
        self._writer = MongoLogEventWriter(
            db=db,
            batch_size=batch_size,
            flush_interval_ms=flush_interval_ms,
            max_queue_size=max_queue_size,
        )
        self._sink_id: int | None = None
        self._throttle: dict[str, _ThrottleState] = {}
        self._started = False
        self._closed = False

    async def start(self) -> None:
        """Start the backing writer."""
        if self._started:
            return
        await self._writer.start()
        self._started = True

    def install(self) -> None:
        """Attach this capture sink to Loguru."""
        if not self._started:
            raise RuntimeError("PersistentLogCapture.start() must be awaited before install().")
        if self._sink_id is None:
            self._sink_id = logger.add(self, level="DEBUG", enqueue=False, catch=True)

    async def close(self) -> None:
        """Remove the Loguru sink and flush queued/suppressed log events."""
        if self._closed:
            return
        self._closed = True
        if self._sink_id is not None:
            logger.remove(self._sink_id)
            self._sink_id = None
        self.flush_suppressed()
        await self._writer.close()

    def __call__(self, message: Any) -> None:
        """Loguru sink entrypoint."""
        if self._closed:
            return
        try:
            doc = self._record_to_doc(message.record)
        except Exception as exc:
            sys.stderr.write(f"Failed to normalize log event for persistence: {exc}\n")
            return
        if doc is None:
            return
        self._capture_doc(doc)

    def flush_suppressed(self) -> None:
        """Emit summary rows for throttled events that never got a later write."""
        for state in list(self._throttle.values()):
            if state.suppressed_count <= 0:
                continue
            summary = dict(state.last_doc)
            summary["event_id"] = str(uuid4())
            summary["throttled"] = True
            summary["suppressed_count"] = state.suppressed_count
            summary["first_seen_at"] = state.first_seen_at
            summary["last_seen_at"] = state.last_seen_at
            self._writer.enqueue_nowait(summary)
            state.suppressed_count = 0

    def _record_to_doc(self, record: dict[str, Any]) -> dict[str, Any] | None:
        extra = dict(record.get("extra") or {})
        if extra.get("persist_log") is False:
            return None

        level = record.get("level")
        level_no = int(getattr(level, "no", 0) or 0)
        persist_log = bool(extra.get("persist_log", False))
        if level_no < self._min_level_no and not persist_log:
            return None

        event_ts = record.get("time") or utc_now()
        if not isinstance(event_ts, datetime):
            event_ts = utc_now()

        file_info = record.get("file")
        message = str(record.get("message") or "")
        doc: dict[str, Any] = {
            "event_id": str(uuid4()),
            "schema_version": 1,
            MongoColumns.EVENT_TS: event_ts,
            MongoColumns.SOURCE: str(extra.get("source") or self._source),
            "run_name": str(extra.get("run_name") or self._run_name or ""),
            "level": str(getattr(level, "name", record.get("level", ""))),
            "level_no": level_no,
            "message": message,
            "module": record.get("module"),
            "function": record.get("function"),
            "line": record.get("line"),
            "file_name": getattr(file_info, "name", None),
            "file_path": getattr(file_info, "path", None),
            "exception": _serialize_exception(record.get("exception")),
            "fingerprint": "",
            "throttled": False,
            "suppressed_count": 0,
            "first_seen_at": event_ts,
            "last_seen_at": event_ts,
            "_capture_throttle": extra.get("throttle", True),
            "_capture_throttle_seconds": extra.get("throttle_seconds"),
        }

        for key in _CONTEXT_EXTRA_KEYS:
            if key in extra and extra[key] is not None:
                doc[key] = _sanitize(extra[key])

        detail = extra.get("detail")
        if detail is not None:
            doc["detail"] = _sanitize(detail)

        remaining_extra = {
            key: value
            for key, value in extra.items()
            if key not in _CONTROL_EXTRA_KEYS and key not in _CONTEXT_EXTRA_KEYS and key != "source"
        }
        if remaining_extra:
            doc["extra"] = _sanitize(remaining_extra)

        throttle_key = extra.get("throttle_key")
        doc["fingerprint"] = str(throttle_key) if throttle_key else _fingerprint(doc)
        return doc

    def _capture_doc(self, doc: dict[str, Any]) -> None:
        throttle_seconds = _throttle_seconds(doc, self._default_throttle_seconds)
        if throttle_seconds <= 0:
            self._writer.enqueue_nowait(doc)
            return

        key = str(doc["fingerprint"])
        now = doc[MongoColumns.EVENT_TS]
        state = self._throttle.get(key)
        if state is None:
            self._writer.enqueue_nowait(doc)
            self._throttle[key] = _ThrottleState(
                first_seen_at=now,
                last_seen_at=now,
                next_emit_at=now + timedelta(seconds=throttle_seconds),
                suppressed_count=0,
                last_doc=doc,
            )
            self._prune_throttle_state()
            return

        if now < state.next_emit_at:
            state.suppressed_count += 1
            state.last_seen_at = now
            state.last_doc = doc
            return

        if state.suppressed_count > 0:
            doc["throttled"] = True
            doc["suppressed_count"] = state.suppressed_count
            doc["first_seen_at"] = state.first_seen_at
            doc["last_seen_at"] = now

        self._writer.enqueue_nowait(doc)
        self._throttle[key] = _ThrottleState(
            first_seen_at=now,
            last_seen_at=now,
            next_emit_at=now + timedelta(seconds=throttle_seconds),
            suppressed_count=0,
            last_doc=doc,
        )

    def _prune_throttle_state(self) -> None:
        while len(self._throttle) > self._max_throttle_keys:
            key = next(iter(self._throttle))
            self._throttle.pop(key, None)


def _throttle_seconds(doc: dict[str, Any], default: int) -> int:
    throttle = doc.pop("_capture_throttle", True)
    throttle_seconds = doc.pop("_capture_throttle_seconds", None)
    if throttle is False:
        return 0
    if throttle_seconds is not None:
        try:
            return int(throttle_seconds)
        except Exception:
            return default
    return default


def _serialize_exception(exc: Any) -> dict[str, Any] | None:
    if exc is None:
        return None
    exc_type = getattr(exc, "type", None)
    exc_value = getattr(exc, "value", None)
    exc_tb = getattr(exc, "traceback", None)
    if exc_type is None:
        return {"repr": repr(exc)}
    return {
        "type": getattr(exc_type, "__name__", str(exc_type)),
        "value": str(exc_value),
        "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
    }


def _fingerprint(doc: dict[str, Any]) -> str:
    parts = [
        str(doc.get(MongoColumns.SOURCE) or ""),
        str(doc.get("level") or ""),
        str(doc.get("module") or ""),
        str(doc.get("function") or ""),
        str(doc.get("line") or ""),
        _normalize_message(str(doc.get("message") or "")),
        str((doc.get("exception") or {}).get("type") if isinstance(doc.get("exception"), dict) else ""),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def _normalize_message(message: str) -> str:
    return re.sub(r"\s+", " ", message).strip()


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            key_s = str(key)
            if _should_redact(key_s):
                out[key_s] = "[redacted]"
            else:
                out[key_s] = _sanitize(item)
        return out
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool | datetime):
        return value
    return repr(value)


def _should_redact(key: str) -> bool:
    lowered = key.lower()
    return lowered in _REDACT_KEYS or lowered.endswith(("_email", "_phone", "_phone_number", "_token"))
