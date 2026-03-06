from dataclasses import dataclass
from typing import Any


@dataclass
class GameState:
    """The result of a single advance() call."""

    message: str
    awaiting: str  # "user_input" | "done"


class Game:
    """Abstract base class for games."""

    async def advance(self, state: Any = None) -> GameState:
        """Advance the game by one AI turn and return the resulting state."""
        raise NotImplementedError

    def reset(self) -> None:
        """Reset the game to its initial state."""
        raise NotImplementedError
