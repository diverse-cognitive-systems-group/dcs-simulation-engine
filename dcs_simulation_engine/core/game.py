"""Base classes for new-style game implementations."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Callable, ClassVar, NamedTuple

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter, list_character_filter_names
from dcs_simulation_engine.dal.character_filters.base import CharacterFilter
from dcs_simulation_engine.utils.time import utc_now
from loguru import logger
from pydantic import BaseModel, ConfigDict

NumericRange = tuple[int, int]


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

    max_turns: int | None = None
    max_playtime: int | None = None

    player_retry_budget: int | None = None
    max_input_length: int | None = None
    pcs_allowed: str | None = None
    npcs_allowed: str | None = None


class Game(ABC):
    """Abstract base class.

    Provides a concrete ``step()`` that handles the full turn lifecycle:
    setup on first call, finish-flow routing, command dispatch, input
    validation, and scene advancement.  Subclasses only need to implement
    the game-specific pieces.

    Each concrete subclass must also declare an inner ``Overrides`` model
    (subclass of ``BaseGameOverrides``) listing every kwarg a run config
    may supply.

    Each concrete subclass must also define GAME_NAME and GAME_DESCRIPTION
    class attributes with non-empty string values.
    """

    GAME_NAME: ClassVar[str]
    GAME_DESCRIPTION: ClassVar[str]

    DEFAULT_MAX_TURNS = 50
    ALLOWED_MAX_TURNS_RANGE: ClassVar[NumericRange] = (1, 500)
    DEFAULT_MAX_PLAYTIME = 600
    ALLOWED_MAX_PLAYTIME_RANGE: ClassVar[NumericRange] = (1, 3600)
    DEFAULT_PLAYER_RETRY_BUDGET = 10
    ALLOWED_PLAYER_RETRY_BUDGET_RANGE: ClassVar[NumericRange] = (0, 10)
    DEFAULT_MAX_INPUT_LENGTH = 350
    ALLOWED_MAX_INPUT_LENGTH_RANGE: ClassVar[NumericRange] = (1, 350)
    DEFAULT_PCS_FILTER: CharacterFilter = get_character_filter("pc-eligible")
    DEFAULT_NPCS_FILTER: CharacterFilter = get_character_filter("all")
    ALLOWED_PCS: ClassVar[frozenset[str]] = frozenset(
        {
            "pc-eligible",
            "human-normative",
            "divergent",
            "hypersensitive",
            "hyposensitive",
            "neurotypical",
            "neurodivergent",
            "physical-divergence",
        }
    )
    ALLOWED_NPCS: ClassVar[frozenset[str]] = frozenset(list_character_filter_names())
    OPENING_PREFIX = "Opening scene: "
    SIMULATOR_PREFIX = "Simulator: "
    PLAYER_PREFIX = "Player"

    # ---- Overrides schema ------------------------------------------------

    class Overrides(BaseGameOverrides):
        """Base overrides — no additional fields.

        Concrete games replace this with their own typed model.
        """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Enforce that concrete game subclasses define GAME_NAME and GAME_DESCRIPTION."""
        super().__init_subclass__(**kwargs)

        parent_game_cls = next((base for base in cls.__mro__[1:] if issubclass(base, Game)), None)
        if parent_game_cls is None:
            return

        cls._validate_class_bounds(parent_game_cls)

        # Skip abstract intermediates for concrete metadata checks.
        if getattr(cls, "__abstractmethods__", None):
            return

        for field in ("GAME_NAME", "GAME_DESCRIPTION"):
            value = getattr(cls, field, None)
            if not isinstance(value, str) or not value.strip():
                raise TypeError(f"{cls.__name__} must define non-empty {field} class attribute. Got: {field}={value!r}")

    @classmethod
    def parse_overrides(cls, raw: dict[str, Any]) -> "Game.Overrides":
        """Validate and coerce a raw overrides dict from the run config."""
        overrides = cls.Overrides.model_validate(raw)
        cls._validate_common_overrides(overrides)
        return overrides

    @classmethod
    def _coerce_numeric_range(cls, value: Any, *, field_name: str) -> NumericRange:
        """Validate and normalize a numeric bounds tuple."""
        if not isinstance(value, tuple):
            value = tuple(value)
        if len(value) != 2:
            raise TypeError(f"{cls.__name__}.{field_name} must contain exactly two integers.")
        lower, upper = value
        if isinstance(lower, bool) or not isinstance(lower, int) or isinstance(upper, bool) or not isinstance(upper, int):
            raise TypeError(f"{cls.__name__}.{field_name} must contain only integers.")
        if lower > upper:
            raise TypeError(f"{cls.__name__}.{field_name} must be an inclusive range with lower <= upper.")
        return (lower, upper)

    @classmethod
    def _coerce_allowed_filter_names(cls, value: Any, *, field_name: str) -> frozenset[str]:
        """Validate and normalize the allowed filter-name set."""
        try:
            names = frozenset(value)
        except TypeError as exc:
            raise TypeError(f"{cls.__name__}.{field_name} must be an iterable of filter names.") from exc
        if not names:
            raise TypeError(f"{cls.__name__}.{field_name} must not be empty.")
        invalid_names = sorted(name for name in names if not isinstance(name, str) or not name.strip())
        if invalid_names:
            raise TypeError(f"{cls.__name__}.{field_name} must contain non-empty strings. Got: {invalid_names!r}")
        unknown_names = sorted(name for name in names if name not in set(list_character_filter_names()))
        if unknown_names:
            raise TypeError(f"{cls.__name__}.{field_name} contains unknown filters: {unknown_names!r}")
        return names

    @classmethod
    def _get_filter_name(cls, value: Any, *, field_name: str) -> str:
        """Return a validated registry name from a default CharacterFilter."""
        name = getattr(value, "name", None)
        if not isinstance(name, str) or not name.strip():
            raise TypeError(f"{cls.__name__}.{field_name} must define a CharacterFilter with a non-empty name.")
        try:
            get_character_filter(name)
        except ValueError as exc:
            raise TypeError(f"{cls.__name__}.{field_name} uses unknown character filter {name!r}.") from exc
        return name

    @classmethod
    def _validate_default_in_range(cls, *, field_name: str, value: Any, allowed_range: NumericRange) -> None:
        """Validate that a numeric default falls within its inclusive range."""
        lower, upper = allowed_range
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{cls.__name__}.{field_name} must be an integer.")
        if not lower <= value <= upper:
            raise TypeError(f"{cls.__name__}.{field_name}={value} is outside allowed range [{lower}, {upper}].")

    @classmethod
    def _validate_override_number(cls, *, field_name: str, value: int | None, allowed_range: NumericRange) -> None:
        """Reject numeric override values that fall outside the configured range."""
        if value is None:
            return
        lower, upper = allowed_range
        if not lower <= value <= upper:
            raise ValueError(f"{cls.__name__} override {field_name!r}={value} is outside allowed range [{lower}, {upper}].")

    @classmethod
    def _validate_override_filter_name(cls, *, field_name: str, value: str | None, allowed_names: frozenset[str]) -> None:
        """Reject unknown or disallowed filter override values."""
        if value is None:
            return
        get_character_filter(value)
        if value not in allowed_names:
            raise ValueError(f"{cls.__name__} override {field_name!r}={value!r} is not allowed. Allowed values: {sorted(allowed_names)!r}")

    @classmethod
    def _validate_common_overrides(cls, overrides: BaseGameOverrides) -> None:
        """Validate shared override values against the class bounds."""
        cls._validate_override_number(
            field_name="max_turns",
            value=overrides.max_turns,
            allowed_range=cls.ALLOWED_MAX_TURNS_RANGE,
        )
        cls._validate_override_number(
            field_name="max_playtime",
            value=overrides.max_playtime,
            allowed_range=cls.ALLOWED_MAX_PLAYTIME_RANGE,
        )
        cls._validate_override_number(
            field_name="player_retry_budget",
            value=overrides.player_retry_budget,
            allowed_range=cls.ALLOWED_PLAYER_RETRY_BUDGET_RANGE,
        )
        cls._validate_override_number(
            field_name="max_input_length",
            value=overrides.max_input_length,
            allowed_range=cls.ALLOWED_MAX_INPUT_LENGTH_RANGE,
        )
        cls._validate_override_filter_name(
            field_name="pcs_allowed",
            value=overrides.pcs_allowed,
            allowed_names=cls.ALLOWED_PCS,
        )
        cls._validate_override_filter_name(
            field_name="npcs_allowed",
            value=overrides.npcs_allowed,
            allowed_names=cls.ALLOWED_NPCS,
        )

    @classmethod
    def _validate_narrowed_range(
        cls,
        *,
        field_name: str,
        child_range: NumericRange,
        parent_range: NumericRange,
    ) -> None:
        """Ensure a child inclusive range is not wider than its parent."""
        child_lower, child_upper = child_range
        parent_lower, parent_upper = parent_range
        if child_lower < parent_lower or child_upper > parent_upper:
            raise TypeError(
                f"{cls.__name__}.{field_name}={child_range} widens parent range {parent_range}. "
                "Child ranges must be equal to or narrower than the parent."
            )

    @classmethod
    def _validate_subset(
        cls,
        *,
        field_name: str,
        child_values: frozenset[str],
        parent_values: frozenset[str],
    ) -> None:
        """Ensure a child allowed-set is not wider than its parent."""
        if not child_values.issubset(parent_values):
            extras = sorted(child_values - parent_values)
            raise TypeError(
                f"{cls.__name__}.{field_name} contains values not allowed by the parent: {extras!r}. "
                "Child allowed sets must be subsets of the parent."
            )

    @classmethod
    def _validate_class_bounds(cls, parent_game_cls: type["Game"]) -> None:
        """Validate subclass defaults and allowed bounds against the parent Game class."""
        cls.ALLOWED_MAX_TURNS_RANGE = cls._coerce_numeric_range(cls.ALLOWED_MAX_TURNS_RANGE, field_name="ALLOWED_MAX_TURNS_RANGE")
        cls.ALLOWED_MAX_PLAYTIME_RANGE = cls._coerce_numeric_range(
            cls.ALLOWED_MAX_PLAYTIME_RANGE,
            field_name="ALLOWED_MAX_PLAYTIME_RANGE",
        )
        cls.ALLOWED_PLAYER_RETRY_BUDGET_RANGE = cls._coerce_numeric_range(
            cls.ALLOWED_PLAYER_RETRY_BUDGET_RANGE,
            field_name="ALLOWED_PLAYER_RETRY_BUDGET_RANGE",
        )
        cls.ALLOWED_MAX_INPUT_LENGTH_RANGE = cls._coerce_numeric_range(
            cls.ALLOWED_MAX_INPUT_LENGTH_RANGE,
            field_name="ALLOWED_MAX_INPUT_LENGTH_RANGE",
        )
        cls.ALLOWED_PCS = cls._coerce_allowed_filter_names(cls.ALLOWED_PCS, field_name="ALLOWED_PCS")
        cls.ALLOWED_NPCS = cls._coerce_allowed_filter_names(cls.ALLOWED_NPCS, field_name="ALLOWED_NPCS")

        cls._validate_narrowed_range(
            field_name="ALLOWED_MAX_TURNS_RANGE",
            child_range=cls.ALLOWED_MAX_TURNS_RANGE,
            parent_range=parent_game_cls.ALLOWED_MAX_TURNS_RANGE,
        )
        cls._validate_narrowed_range(
            field_name="ALLOWED_MAX_PLAYTIME_RANGE",
            child_range=cls.ALLOWED_MAX_PLAYTIME_RANGE,
            parent_range=parent_game_cls.ALLOWED_MAX_PLAYTIME_RANGE,
        )
        cls._validate_narrowed_range(
            field_name="ALLOWED_PLAYER_RETRY_BUDGET_RANGE",
            child_range=cls.ALLOWED_PLAYER_RETRY_BUDGET_RANGE,
            parent_range=parent_game_cls.ALLOWED_PLAYER_RETRY_BUDGET_RANGE,
        )
        cls._validate_narrowed_range(
            field_name="ALLOWED_MAX_INPUT_LENGTH_RANGE",
            child_range=cls.ALLOWED_MAX_INPUT_LENGTH_RANGE,
            parent_range=parent_game_cls.ALLOWED_MAX_INPUT_LENGTH_RANGE,
        )
        cls._validate_subset(
            field_name="ALLOWED_PCS",
            child_values=cls.ALLOWED_PCS,
            parent_values=parent_game_cls.ALLOWED_PCS,
        )
        cls._validate_subset(
            field_name="ALLOWED_NPCS",
            child_values=cls.ALLOWED_NPCS,
            parent_values=parent_game_cls.ALLOWED_NPCS,
        )

        cls._validate_default_in_range(
            field_name="DEFAULT_MAX_TURNS",
            value=cls.DEFAULT_MAX_TURNS,
            allowed_range=cls.ALLOWED_MAX_TURNS_RANGE,
        )
        cls._validate_default_in_range(
            field_name="DEFAULT_MAX_PLAYTIME",
            value=cls.DEFAULT_MAX_PLAYTIME,
            allowed_range=cls.ALLOWED_MAX_PLAYTIME_RANGE,
        )
        cls._validate_default_in_range(
            field_name="DEFAULT_PLAYER_RETRY_BUDGET",
            value=cls.DEFAULT_PLAYER_RETRY_BUDGET,
            allowed_range=cls.ALLOWED_PLAYER_RETRY_BUDGET_RANGE,
        )
        cls._validate_default_in_range(
            field_name="DEFAULT_MAX_INPUT_LENGTH",
            value=cls.DEFAULT_MAX_INPUT_LENGTH,
            allowed_range=cls.ALLOWED_MAX_INPUT_LENGTH_RANGE,
        )

        pcs_filter_name = cls._get_filter_name(cls.DEFAULT_PCS_FILTER, field_name="DEFAULT_PCS_FILTER")
        npcs_filter_name = cls._get_filter_name(cls.DEFAULT_NPCS_FILTER, field_name="DEFAULT_NPCS_FILTER")
        if pcs_filter_name not in cls.ALLOWED_PCS:
            raise TypeError(f"{cls.__name__}.DEFAULT_PCS_FILTER={pcs_filter_name!r} is not included in {cls.__name__}.ALLOWED_PCS.")
        if npcs_filter_name not in cls.ALLOWED_NPCS:
            raise TypeError(f"{cls.__name__}.DEFAULT_NPCS_FILTER={npcs_filter_name!r} is not included in {cls.__name__}.ALLOWED_NPCS.")

    @classmethod
    def _resolve_character_filter(
        cls,
        *,
        override_value: str | None,
        default_value: CharacterFilter,
        field_name: str,
        allowed_names: frozenset[str],
    ) -> CharacterFilter:
        """Resolve an optional filter override string into a CharacterFilter."""
        if override_value is None:
            return default_value
        cls._validate_override_filter_name(field_name=field_name, value=override_value, allowed_names=allowed_names)
        return get_character_filter(override_value)

    @classmethod
    def build_base_init_kwargs(cls, overrides: BaseGameOverrides) -> dict[str, Any]:
        """Build common constructor kwargs from validated overrides.

        Subclasses can use this in ``create_from_context`` and only add
        game-specific constructor arguments.
        """
        return {
            "player_retry_budget": (
                overrides.player_retry_budget if overrides.player_retry_budget is not None else cls.DEFAULT_PLAYER_RETRY_BUDGET
            ),
            "max_input_length": (overrides.max_input_length if overrides.max_input_length is not None else cls.DEFAULT_MAX_INPUT_LENGTH),
            "pcs_allowed": cls._resolve_character_filter(
                override_value=overrides.pcs_allowed,
                default_value=cls.DEFAULT_PCS_FILTER,
                field_name="pcs_allowed",
                allowed_names=cls.ALLOWED_PCS,
            ),
            "npcs_allowed": cls._resolve_character_filter(
                override_value=overrides.npcs_allowed,
                default_value=cls.DEFAULT_NPCS_FILTER,
                field_name="npcs_allowed",
                allowed_names=cls.ALLOWED_NPCS,
            ),
        }

    # ---- Constructor (common state) --------------------------------------

    def __init__(
        self,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        engine: Any,  # SimulatorClient from ai_client.py
        player_retry_budget: int | None = None,
        max_input_length: int | None = None,
        pcs_allowed: CharacterFilter | None = None,
        npcs_allowed: CharacterFilter | None = None,
    ) -> None:
        """Initialise shared game state. Call via super().__init__() in subclasses."""
        self._pc = pc
        self._npc = npc
        self._engine = engine
        self._player_retry_budget = player_retry_budget if player_retry_budget is not None else type(self).DEFAULT_PLAYER_RETRY_BUDGET
        self._max_input_length = max_input_length if max_input_length is not None else type(self).DEFAULT_MAX_INPUT_LENGTH
        self._pcs_allowed = pcs_allowed if pcs_allowed is not None else type(self).DEFAULT_PCS_FILTER
        self._npcs_allowed = npcs_allowed if npcs_allowed is not None else type(self).DEFAULT_NPCS_FILTER
        self._entered = False
        self._exited = False
        self._exit_reason = ""
        self._in_finish_flow = False
        self._filtered_transcript_buffer: list[str] = []

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

    def get_transcript(self) -> str:
        """Return the filtered game transcript (opening + successful turns only)."""
        return "\n".join(self._filtered_transcript_buffer)

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
            self._consume_model_metadata(stage="opening", metadata=opening.metadata)
            self._filtered_transcript_buffer.append(f"{self.OPENING_PREFIX}{opening.content}")
            yield GameEvent.now(type=opening.type, content=opening.content)
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

        result = await self._engine.step(user_input)
        self._consume_turn_metadata(result)
        if result.ok:
            self._filtered_transcript_buffer.append(f"{self.PLAYER_PREFIX} ({self._pc.hid}): {user_input}")
            self._filtered_transcript_buffer.append(f"{self.SIMULATOR_PREFIX}{result.simulator_response}")
        yield GameEvent.now(
            type="ai" if result.ok else "error", content=result.simulator_response if result.ok else (result.error_message or "")
        )
        if not result.ok:
            self._player_retry_budget -= 1
            logger.debug(f"Validation failed. Retry budget remaining: {self._player_retry_budget}")
            if self._player_retry_budget <= 0:
                self.exit("retry budget exhausted")
                yield GameEvent.now(
                    type="info",
                    content="You have used all your allowed retries. The game is ending.",
                )

    def _consume_model_metadata(self, *, stage: str, metadata: dict[str, Any]) -> None:
        """Consume optional structured metadata attached to a model response."""
        return

    def _consume_turn_metadata(self, result: Any) -> None:
        """Forward optional component metadata from a simulator turn to the game hook."""
        for stage, component in (("updater", getattr(result, "updater_result", None)),):
            if component is None:
                continue
            self._consume_model_metadata(stage=stage, metadata=getattr(component, "metadata", {}) or {})

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

        if cmd == "finish":
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

    @abstractmethod
    async def on_finish(self) -> AsyncIterator[GameEvent]:
        """Called when ``/finish`` is issued.

        Simple games call ``self.exit()`` and yield a closing message.
        Multi-step games set ``self._in_finish_flow = True`` and yield a
        question; subsequent inputs are routed to ``on_finish_input()``.
        """
        raise NotImplementedError
        yield  # pragma: no cover — keeps this typed as an async generator

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
        the ``/finish``.  Return ``None`` for unrecognised commands so
        ``SessionManager`` can handle them.
        """
        return None

    def _export_engine_state(self) -> dict[str, Any]:
        """Return a serialisable snapshot of the engine state when supported."""
        export_state = getattr(self._engine, "export_state", None)
        if callable(export_state):
            state = export_state()
            if isinstance(state, dict):
                return state

        export_history = getattr(self._engine, "export_history", None)
        if callable(export_history):
            return {"history": list(export_history())}

        return {}

    def _import_engine_state(self, state: dict[str, Any]) -> None:
        """Restore engine state, including legacy history-only snapshots."""
        import_state = getattr(self._engine, "import_state", None)
        engine_state = state.get("engine_state")
        legacy_history = state.get("updater_history", [])

        if callable(import_state):
            if isinstance(engine_state, dict):
                import_state(engine_state)
                return
            import_state({"history": legacy_history, "transcript_events": legacy_history})
            return

        import_history = getattr(self._engine, "import_history", None)
        if callable(import_history):
            import_history(legacy_history)

    def _export_additional_state(self) -> dict[str, Any]:
        """Return subclass-specific mutable state."""
        return {}

    def _import_additional_state(self, state: dict[str, Any]) -> None:
        """Restore subclass-specific mutable state."""
        return

    def export_state(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of this game's mutable state.

        Must include every field needed to restore behaviour exactly — lifecycle
        flags, retry budgets, state-machine booleans, collected player inputs,
        and evaluation payloads.  The returned dict is stored under the
        ``game_state`` key of the session ``runtime_state`` document.
        """
        state = {
            "entered": self._entered,
            "exited": self._exited,
            "exit_reason": self._exit_reason,
            "player_retry_budget": self._player_retry_budget,
            "in_finish_flow": self._in_finish_flow,
            "filtered_transcript_buffer": list(self._filtered_transcript_buffer),
            "engine_state": self._export_engine_state(),
        }
        state.update(self._export_additional_state())
        return state

    def import_state(self, state: dict[str, Any]) -> None:
        """Restore mutable state from a snapshot produced by ``export_state``.

        Called by ``SessionManager.create_from_snapshot`` immediately after the
        game instance is constructed via ``create_from_context``.
        """
        legacy_retry_budget = state.get("retry_budget", type(self).DEFAULT_PLAYER_RETRY_BUDGET)
        self._entered = bool(state.get("entered", False))
        self._exited = bool(state.get("exited", False))
        self._exit_reason = str(state.get("exit_reason", ""))
        self._player_retry_budget = int(state.get("player_retry_budget", legacy_retry_budget))
        self._in_finish_flow = bool(state.get("in_finish_flow", False))

        transcript_buffer = state.get("filtered_transcript_buffer")
        if isinstance(transcript_buffer, list):
            self._filtered_transcript_buffer = [str(entry) for entry in transcript_buffer]
        else:
            legacy_history = state.get("updater_history", [])
            self._filtered_transcript_buffer = [str(entry) for entry in legacy_history] if isinstance(legacy_history, list) else []

        self._import_engine_state(state)
        self._import_additional_state(state)

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
    @abstractmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "Game":
        """Factory method called by SessionManager.

        Receives character records and any run-config kwargs (validated against
        ``cls.Overrides``).  Returns a fully initialised Game instance.
        """
