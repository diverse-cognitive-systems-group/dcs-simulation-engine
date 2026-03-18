"""In-memory session registry with TTL cleanup for FastAPI server sessions."""

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Literal
from uuid import uuid4

from dcs_simulation_engine.core.session_manager import SessionManager
from loguru import logger

SessionStatus = Literal["active", "closed"]


@dataclass
class SessionEntry:
    """Represents one in-memory API session record."""

    session_id: str
    player_id: str | None
    game_name: str
    manager: SessionManager
    experiment_name: str | None = None
    assignment_id: str | None = None
    status: SessionStatus = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    opening_sent: bool = False

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
        self._sweep_task: asyncio.Task[None] | None = None

    def add(
        self,
        *,
        player_id: str | None,
        game_name: str,
        manager: SessionManager,
        experiment_name: str | None = None,
        assignment_id: str | None = None,
    ) -> SessionEntry:
        """Create and store a new session entry."""
        session_id = str(uuid4())
        entry = SessionEntry(
            session_id=session_id,
            player_id=player_id,
            game_name=game_name,
            manager=manager,
            experiment_name=experiment_name,
            assignment_id=assignment_id,
        )
        with self._lock:
            self._store[session_id] = entry
        logger.info("Session %s created (%d active)", session_id, self.size)
        return entry

    def get(self, session_id: str) -> SessionEntry | None:
        """Get a session entry by id, or None if it does not exist."""
        with self._lock:
            return self._store.get(session_id)

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

    def close(self, session_id: str) -> None:
        """Mark a session as closed but keep it until explicit removal/TTL expiry."""
        with self._lock:
            entry = self._store.get(session_id)
            if entry is not None:
                entry.status = "closed"
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

    async def sweep_async(self) -> list[str]:
        """Async sweep variant that awaits async session finalization when available."""
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

        if stale_ids:
            logger.warning("Swept %d stale session(s)", len(stale_ids))
        return stale_ids

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
            await self.sweep_async()
