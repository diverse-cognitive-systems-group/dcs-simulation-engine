"""Base classes for new-style game implementations."""

from datetime import datetime
from typing import Any, AsyncIterator, NamedTuple

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.utils.time import utc_now


class GameEvent(NamedTuple):
    """A single event yielded by a game step."""

    type: str
    content: str
    event_ts: datetime
    command_response: bool = False

    @classmethod
    def now(cls, *, type: str, content: str, command_response: bool = False) -> "GameEvent":
        """Build an event stamped with the current wall-clock time."""
        return cls(type=type, content=content, event_ts=utc_now(), command_response=command_response)


class Game:
    """Base class for new-style games.

    Replaces build_graph_config() / SimulationGraph for games that prefer
    to express their logic directly in Python rather than as a LangGraph graph.

    SessionManager drives this class instead of RunManager.
    """

    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn.

        Async-yields one or more GameEvents. Handles command detection,
        validation, AI calls, and lifecycle transitions internally.
        """
        raise NotImplementedError

    def exit(self, reason: str) -> None:
        """Signal the game to end."""
        raise NotImplementedError

    @property
    def exited(self) -> bool:
        """True if the game has ended."""
        raise NotImplementedError

    @property
    def exit_reason(self) -> str:
        """Reason the game ended, or empty string."""
        raise NotImplementedError

    def export_state(self) -> dict:
        """Return a JSON-serialisable snapshot of this game's mutable state.

        Must include every field needed to restore behaviour exactly — lifecycle
        flags, retry budgets, state-machine booleans, collected player inputs,
        and evaluation payloads.  The returned dict is stored under the
        ``game_state`` key of the session ``runtime_state`` document.
        """
        raise NotImplementedError

    def import_state(self, state: dict) -> None:
        """Restore mutable state from a snapshot produced by ``export_state``.

        Called by ``SessionManager.create_from_snapshot`` immediately after the
        game instance is constructed via ``create_from_context``.
        """
        raise NotImplementedError

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "Game":
        """Factory method called by SessionManager.

        Receives character records loaded from the DB and any additional
        kwargs (e.g. model names). Returns a fully initialised Game instance.
        """
        raise NotImplementedError
