"""In-memory session registry with TTL cleanup for FastAPI server sessions."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from dcs_simulation_engine.core.session_manager import SessionManager
from loguru import logger

SessionStatus = Literal["active", "paused", "closed"]


@dataclass
class SessionEntry:
    """Represents one in-memory API session record."""

    session_id: str
    player_id: str | None
    game_name: str
    manager: SessionManager
    assignment_id: str | None = None
    status: SessionStatus = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    opening_sent: bool = False
    ws_connected: bool = False

    def touch(self) -> None:
        """Refresh the last-activity timestamp."""
        self.last_active = datetime.now(timezone.utc)


class SessionRegistry:
    """Thread-safe in-memory session store with async TTL sweeping."""

    def __init__(self, *, ttl_seconds: int = 3600, sweep_interval_seconds: int = 60) -> None:
        """Initialize registry settings and empty storage."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        if sweep_interval_seconds <= 0:
            raise ValueError("sweep_interval_seconds must be > 0")

        self._ttl = timedelta(seconds=ttl_seconds)
        self._sweep_interval_seconds = sweep_interval_seconds
        self._store: dict[str, SessionEntry] = {}
        self._lock = RLock()
        self._pending_hydration: set[str] = set()
        self._sweep_task: asyncio.Task[None] | None = None
        self._provider: Any = None

    def add(
        self,
        *,
        player_id: str | None,
        game_name: str,
        manager: SessionManager,
        assignment_id: str | None = None,
    ) -> SessionEntry:
        """Create and store a new session entry."""
        session_id = str(uuid4())
        entry = SessionEntry(
            session_id=session_id,
            player_id=player_id,
            game_name=game_name,
            manager=manager,
            assignment_id=assignment_id,
        )
        with self._lock:
            self._store[session_id] = entry
        logger.info("Session %s created (%d active)", session_id, self.size)
        return entry

    def reinsert(self, session_id: str, entry: SessionEntry) -> None:
        """Re-add a hydrated session under its original session_id.

        Used after a process restart to restore a paused session that was
        evicted from the in-memory registry.  Raises ``ValueError`` if a live
        entry already exists for this id (prevents a hydration race from
        overwriting an already-connected session).
        """
        with self._lock:
            if session_id in self._store:
                raise ValueError(f"Session {session_id} already exists in registry; skipping reinsert.")
            self._pending_hydration.discard(session_id)
            self._store[session_id] = entry
        logger.info("Session %s reinserted from snapshot (%d active)", session_id, self.size)

    def get(self, session_id: str) -> SessionEntry | None:
        """Get a session entry by id, or None if it does not exist."""
        with self._lock:
            return self._store.get(session_id)

    def claim_hydration(self, session_id: str) -> bool:
        """Mark session_id as being hydrated.

        Returns True if this caller won
        the race; False if another coroutine is already hydrating it.
        """
        with self._lock:
            if session_id in self._store or session_id in self._pending_hydration:
                return False
            self._pending_hydration.add(session_id)
            return True

    def release_hydration(self, session_id: str) -> None:
        """Remove the pending-hydration marker (called on success or failure)."""
        with self._lock:
            self._pending_hydration.discard(session_id)

    def list_for_player(self, player_id: str) -> list[SessionEntry]:
        """List sessions owned by a specific player, newest first."""
        with self._lock:
            entries = [entry for entry in self._store.values() if entry.player_id == player_id]
        return sorted(entries, key=lambda item: item.created_at, reverse=True)

    def touch(self, session_id: str) -> None:
        """Refresh a session's idle timer if present."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.touch()

    def mark_opening_sent(self, session_id: str) -> None:
        """Mark that the opening turn has already been sent."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.opening_sent = True

    def pause(self, session_id: str) -> None:
        """Mark a session as paused; keep it and its manager alive for resume."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.status = "paused"
                entry.ws_connected = False
                entry.touch()

    def set_active(self, session_id: str) -> None:
        """Mark a paused session as active again after a successful reconnect."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.status = "active"
                entry.ws_connected = True
                entry.touch()

    def set_ws_connected(self, session_id: str, connected: bool) -> None:
        """Update the WebSocket connection flag for a session."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.ws_connected = connected

    def close(self, session_id: str) -> None:
        """Mark a session as closed but keep it until explicit removal/TTL expiry."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.status = "closed"
                entry.ws_connected = False
                entry.touch()

    def remove(self, session_id: str) -> SessionEntry | None:
        """Remove and return a session entry if it exists."""
        with self._lock:
            entry = self._store.pop(session_id, None)
        if entry is not None:
            logger.info("Session %s removed (%d remaining)", session_id, self.size)
        return entry

    @property
    def size(self) -> int:
        """Current number of live session entries."""
        with self._lock:
            return len(self._store)

    async def sweep_async(self, provider: Any = None) -> list[str]:
        """Async sweep variant that awaits async session finalization when available.

        When ``provider`` is given, expired sessions that belong to an
        run assignment are marked ``interrupted`` so the player can
        start that assignment again.
        """
        from dcs_simulation_engine.utils.async_utils import maybe_await

        cutoff = datetime.now(timezone.utc) - self._ttl
        with self._lock:
            stale_ids = [sid for sid, entry in self._store.items() if entry.last_active < cutoff]
            stale_entries = [(sid, self._store.pop(sid)) for sid in stale_ids]

        for session_id, entry in stale_entries:
            try:
                if not entry.manager.exited:
                    await entry.manager.exit_async("session ttl expired")
            except Exception:
                logger.exception("Failed to exit stale session cleanly: %s", session_id)

            if provider is not None and entry.assignment_id is not None:
                try:
                    await maybe_await(
                        provider.update_assignment_status(
                            assignment_id=entry.assignment_id,
                            status="interrupted",
                        )
                    )
                    logger.info(
                        "Marked assignment %s interrupted after TTL expiry of session %s.",
                        entry.assignment_id,
                        session_id,
                    )
                except Exception:
                    logger.exception(
                        "Failed to mark assignment %s interrupted after TTL expiry of session %s.",
                        entry.assignment_id,
                        session_id,
                    )

        if stale_ids:
            logger.warning("Swept %d stale session(s)", len(stale_ids))
        return stale_ids

    def set_provider(self, provider: Any) -> None:
        """Attach a data provider so the TTL sweep can mark assignments interrupted."""
        self._provider = provider

    async def start(self) -> None:
        """Start background TTL sweeping if it is not already running."""
        if self._sweep_task is not None:
            return
        self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def stop(self) -> None:
        """Stop the background TTL sweeper task."""
        if self._sweep_task is None:
            return
        self._sweep_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._sweep_task
        self._sweep_task = None

    async def _sweep_loop(self) -> None:
        """Run periodic sweep ticks until cancelled."""
        while True:
            await asyncio.sleep(self._sweep_interval_seconds)
            await self.sweep_async(provider=self._provider)


async def hydrate_session_async(
    *,
    session_id: str,
    player_id: str | None,
    provider: Any,
    registry: "SessionRegistry",
) -> SessionEntry | None:
    """Reconstruct a dormant paused session from DB and insert it into the registry.

    Returns the hydrated ``SessionEntry`` on success, or ``None`` if:
    - the session is not found / not paused in the DB,
    - another coroutine won the hydration race,
    - the snapshot schema is unsupported (logs a warning).

    The returned entry has ``opening_sent=True`` and ``status="paused"`` so the
    WS handler sends replay events instead of regenerating the opening turn.
    """
    from dcs_simulation_engine.core.session_manager import SessionManager
    from dcs_simulation_engine.dal.mongo.const import MongoColumns
    from dcs_simulation_engine.utils.async_utils import maybe_await

    if not registry.claim_hydration(session_id):
        logger.info("Session %s hydration already in progress; skipping duplicate attempt.", session_id)
        return None

    try:
        session_record = await maybe_await(provider.get_session(session_id=session_id, player_id=player_id))
        if session_record is None:
            logger.info("Session %s not found in DB; cannot hydrate.", session_id)
            return None
        if session_record.status != "paused":
            logger.info(
                "Session %s has status=%r; only paused sessions can be hydrated.",
                session_id,
                session_record.status,
            )
            return None

        runtime_state = session_record.data.get(MongoColumns.RUNTIME_STATE)
        if not runtime_state:
            logger.warning("Session %s has no runtime_state snapshot; cannot hydrate.", session_id)
            return None

        try:
            manager = await SessionManager.create_from_snapshot(
                snapshot=runtime_state,
                session_record=session_record,
                provider=provider,
            )
        except ValueError as exc:
            logger.warning("Session %s hydration failed: %s", session_id, exc)
            return None

        assignment_record = await maybe_await(provider.get_assignment_for_session_id(session_id=session_id))

        entry = SessionEntry(
            session_id=session_id,
            player_id=session_record.player_id,
            game_name=session_record.game_name,
            manager=manager,
            assignment_id=getattr(assignment_record, "assignment_id", None) if assignment_record else None,
            status="paused",
            opening_sent=True,
        )

        try:
            registry.reinsert(session_id, entry)
        except ValueError:
            # Another coroutine won the race and already inserted; use theirs.
            logger.info("Session %s was inserted by a concurrent hydration; discarding duplicate.", session_id)
            return registry.get(session_id)

        logger.info("Session %s hydrated from snapshot successfully.", session_id)
        return entry

    finally:
        registry.release_hydration(session_id)
