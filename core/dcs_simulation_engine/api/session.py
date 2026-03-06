import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from dcs_simulation_engine.game.game import Game

logger = logging.getLogger(__name__)

SessionStatus = Literal["active", "closed"]

# Sessions inactive for longer than this will be swept from memory
DEFAULT_TTL_MINUTES = 60

# How often the background sweep runs
SWEEP_INTERVAL_SECONDS = 60


@dataclass
class Session:
    """Represents a single game session."""

    id: str
    user_id: str
    game: Game
    status: SessionStatus = "active"
    # Updated on every advance() so the TTL sweep knows if this session is idle
    last_active: datetime = field(default_factory=datetime.now)

    def touch(self) -> None:
        """Reset the idle timer."""
        self.last_active = datetime.now()


class SessionManager:
    """In-memory store for active sessions with TTL-based cleanup."""

    def __init__(self, ttl_minutes: int = DEFAULT_TTL_MINUTES) -> None:
        """Initialize with an empty session store and start the sweep task."""
        self._sessions: dict[str, Session] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._sweep_task: asyncio.Task | None = None

    async def __aenter__(self) -> "SessionManager":
        """Start the background TTL sweep."""
        self._sweep_task = asyncio.create_task(self._sweep_loop())
        return self

    async def __aexit__(self, *_: object) -> None:
        """Cancel the background TTL sweep."""
        if self._sweep_task:
            self._sweep_task.cancel()
            self._sweep_task = None

    def add(self, game: Game, *, user_id: str) -> Session:
        """Create a new session, store it, and return it."""
        session = Session(id=str(uuid.uuid4()), user_id=user_id, game=game)
        self._sessions[session.id] = session
        logger.info("Session %s created (%d active)", session.id, len(self._sessions))
        return session

    def __getitem__(self, session_id: str) -> Session:
        """Return the session with the given ID, or raise KeyError."""
        return self._sessions[session_id]

    def __setitem__(self, session_id: str, session: Session) -> None:
        """Store a session under the given ID."""
        self._sessions[session_id] = session

    def __delitem__(self, session_id: str) -> None:
        """Remove a session immediately, or raise KeyError."""
        del self._sessions[session_id]
        logger.info("Session %s deleted (%d remaining)", session_id, len(self._sessions))

    def __contains__(self, session_id: object) -> bool:
        """Return True if the session ID exists."""
        return session_id in self._sessions

    def touch(self, session_id: str) -> None:
        """Update the last-active timestamp for a session."""
        self._sessions[session_id].touch()

    def close(self, session_id: str) -> None:
        """Mark a session as closed (keeps it in memory until swept or popped)."""
        if session_id in self._sessions:
            self._sessions[session_id].status = "closed"
            logger.info("Session %s closed", session_id)

    def pop(self, session_id: str) -> Session | None:
        """Remove and return a session, or return None if not found."""
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info("Session %s deleted (%d remaining)", session_id, len(self._sessions))
        return session

    async def _sweep_loop(self) -> None:
        """Periodically remove sessions that have been idle past the TTL."""
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            self._sweep()

    def _sweep(self) -> None:
        """Remove all sessions that have exceeded the idle TTL."""
        cutoff = datetime.now() - self._ttl
        stale = [sid for sid, s in self._sessions.items() if s.last_active < cutoff]
        for sid in stale:
            logger.warning("Session %s expired (idle > %s)", sid, self._ttl)
            self.pop(sid)
