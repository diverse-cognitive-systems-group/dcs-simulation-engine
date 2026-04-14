"""Base classes for new-style game implementations."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Callable, NamedTuple

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger
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

    Provides a concrete ``step()`` that handles the full turn lifecycle:
    setup on first call, finish-flow routing, command dispatch, input
    validation, and scene advancement.  Subclasses only need to implement
    the game-specific pieces.

    Each concrete subclass must also declare an inner ``Overrides`` model
    (subclass of ``BaseGameOverrides``) listing every kwarg a run config
    may supply.
    """

    # ---- Overrides schema ------------------------------------------------

    class Overrides(BaseGameOverrides):
        """Base overrides — no additional fields.

        Concrete games replace this with their own typed model.
        """

    @classmethod
    def parse_overrides(cls, raw: dict[str, Any]) -> "Game.Overrides":
        """Validate and coerce a raw overrides dict from the run config."""
        return cls.Overrides.model_validate(raw)

    # ---- Constructor (common state) --------------------------------------

    def __init__(
        self,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        engine: Any,  # EngineClient from ai_client.py
        retry_budget: int,
        max_input_length: int,
    ) -> None:
        """Initialise shared game state. Call via super().__init__() in subclasses."""
        self._pc = pc
        self._npc = npc
        self._engine = engine
        self._retry_budget = retry_budget
        self._max_input_length = max_input_length
        self._entered = False
        self._exited = False
        self._exit_reason = ""
        self._in_finish_flow = False

    # ---- Concrete lifecycle (no more boilerplate in each game) -----------

    def exit(self, reason: str) -> None:
        """Mark the game as ended."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        logger.info(f"{type(self).__name__} exited: {reason}")

    @property
    def exited(self) -> bool:
        """True if the game has ended."""
        return self._exited

    @property
    def exit_reason(self) -> str:
        """Reason the game ended, or empty string."""
        return self._exit_reason

    # ---- Default step() with routing -------------------------------------

    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn, yielding one or more GameEvents.

        Routing order:
        1. Exited → no-op.
        2. First call → setup phase (welcome message + opening scene).
        3. In finish flow → delegate to on_finish_input().
        4. Command (starts with ``/``) → dispatch to command handler.
        5. Normal input → length check, then engine step (validate + update).
        """
        if self._exited:
            return

        if not self._entered:
            self._entered = True
            yield GameEvent.now(type="info", content=self.get_setup_content())
            opening = await self._engine.chat(None)
            yield GameEvent.now(type="ai", content=opening)
            return

        if not user_input:
            return

        if self._in_finish_flow:
            async for event in self.on_finish_input(user_input):
                yield event
            return

        if user_input.strip().startswith("/"):
            async for event in self._dispatch_command(user_input):
                yield event
            return

        if len(user_input) > self._max_input_length:
            yield GameEvent.now(
                type="error",
                content=f"Input exceeds maximum length of {self._max_input_length} characters.",
            )
            return

        valid, content = await self._engine.step(user_input)
        yield GameEvent.now(type="ai" if valid else "error", content=content)
        if not valid:
            self._retry_budget -= 1
            logger.debug(f"Validation failed. Retry budget remaining: {self._retry_budget}")
            if self._retry_budget <= 0:
                self.exit("retry budget exhausted")
                yield GameEvent.now(
                    type="info",
                    content="You have used all your allowed retries. The game is ending.",
                )

    async def _dispatch_command(self, user_input: str) -> AsyncIterator[GameEvent]:
        """Route a slash command to the appropriate handler."""
        command_body = user_input.strip()[1:].strip()
        if not command_body:
            return
        cmd = command_body.split()[0].lower()

        if cmd == "help":
            yield GameEvent.now(type="info", content=self.get_help_content(), command_response=True)
            return

        if cmd == "abilities":
            yield GameEvent.now(type="info", content=self.get_abilities_content(), command_response=True)
            return

        if cmd == self.finish_command:
            async for event in self.on_finish():
                yield event
            return

        handler = self.get_command_handler(cmd)
        if handler is not None:
            async for event in handler():
                yield event

    # ---- Abstract methods (must be implemented by each game) -------------

    def get_setup_content(self) -> str:
        """Content for the initial enter message. Defaults to ``get_help_content()``."""
        return self.get_help_content()

    @abstractmethod
    def get_help_content(self) -> str:
        """Content for the ``/help`` command response."""

    @abstractmethod
    def get_abilities_content(self) -> str:
        """Content for the ``/abilities`` command response."""

    @property
    @abstractmethod
    def finish_command(self) -> str:
        """Command name (without ``/``) that triggers the finish flow."""

    @abstractmethod
    async def on_finish(self) -> AsyncIterator[GameEvent]:
        """Called when ``finish_command`` is issued.

        Simple games call ``self.exit()`` and yield a closing message.
        Multi-step games set ``self._in_finish_flow = True`` and yield a
        question; subsequent inputs are routed to ``on_finish_input()``.
        """

    async def on_finish_input(self, user_input: str) -> AsyncIterator[GameEvent]:
        """Handle user input during a multi-step finish flow.

        Override when the finish phase requires one or more follow-up inputs
        (e.g. a confidence-rating question after a prediction).  The default
        implementation is a no-op.
        """
        return
        yield  # pragma: no cover — makes this an async generator

    def get_command_handler(self, cmd: str) -> Callable[[], AsyncIterator[GameEvent]] | None:
        """Return a zero-argument async-generator handler for extra commands.

        Override to support commands beyond ``/help``, ``/abilities``, and
        the ``finish_command``.  Return ``None`` for unrecognised commands so
        ``SessionManager`` can handle them.
        """
        return None

    @classmethod
    @abstractmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "Game":
        """Factory method called by SessionManager.

        Receives character records and any run-config kwargs (validated against
        ``cls.Overrides``).  Returns a fully initialised Game instance.
        """
