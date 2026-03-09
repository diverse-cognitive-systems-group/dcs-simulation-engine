"""Base classes for new-style game implementations."""

from dataclasses import dataclass
from typing import Any, AsyncIterator

from dcs_simulation_engine.dal.base import CharacterRecord


@dataclass
class GameEvent:
    """A single event yielded by a game step."""

    type: str  # "ai" | "info" | "error" | "warning"
    content: str


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

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "Game":
        """Factory method called by SessionManager.

        Receives character records loaded from the DB and any additional
        kwargs (e.g. model names). Returns a fully initialised Game instance.
        """
        raise NotImplementedError
