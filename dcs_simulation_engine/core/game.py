"""Base classes for new-style game implementations."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, NamedTuple

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.utils.time import utc_now
from pydantic import BaseModel, ConfigDict


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


class BaseGameOverrides(BaseModel):
    """Common overridable parameters shared across all games.

    Run configs may supply any of these fields in a game's ``overrides`` block.
    Subclass this in each game to add game-specific overridable fields.
    """

    model_config = ConfigDict(extra="forbid")

    # Stopping-condition overrides (None = use game YAML default)
    max_turns: int | None = None
    max_playtime: int | None = None


class Game(ABC):
    """Abstract base class.

    SessionManager drives this class.

    Each concrete subclass must:
    - Declare an inner ``Overrides`` model (subclass of ``BaseGameOverrides``) listing
      every kwarg the run config is allowed to supply.
    - Implement all abstract methods.
    """

    class Overrides(BaseGameOverrides):
        """Base overrides — no additional fields.

        Concrete games replace this with their own typed model that adds
        game-specific overridable parameters (e.g. ``player_retry_budget``).
        """

    @classmethod
    def parse_overrides(cls, raw: dict[str, Any]) -> "Game.Overrides":
        """Validate and coerce a raw overrides dict from the run config.

        Raises ``pydantic.ValidationError`` if ``raw`` contains unknown keys
        or values that fail type coercion.
        """
        return cls.Overrides.model_validate(raw)

    @abstractmethod
    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn.

        Async-yields one or more GameEvents. Handles command detection,
        validation, AI calls, and lifecycle transitions internally.
        """

    @abstractmethod
    def exit(self, reason: str) -> None:
        """Signal the game to end."""

    @property
    @abstractmethod
    def exited(self) -> bool:
        """True if the game has ended."""

    @property
    @abstractmethod
    def exit_reason(self) -> str:
        """Reason the game ended, or empty string."""

    @classmethod
    @abstractmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "Game":
        """Factory method called by SessionManager.

        Receives character records loaded from the DB and any additional
        kwargs (validated against ``cls.Overrides``). Returns a fully
        initialized Game instance.
        """
