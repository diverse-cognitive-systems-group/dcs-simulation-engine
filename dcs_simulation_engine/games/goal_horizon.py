"""Goal Horizon game — new-style implementation."""

from enum import StrEnum
from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import (
    UpdaterClient,
    ValidatorClient,
)
from dcs_simulation_engine.games.const import (
    GoalHorizon as C,
)
from dcs_simulation_engine.games.prompts import (
    build_updater_prompt,
    build_validator_prompt,
)
from loguru import logger


class Command(StrEnum):
    """Game-level slash commands recognised by GoalHorizonGame."""

    HELP = "help"
    PREDICT_CAPABILITIES = "predict-capabilities"


class GoalHorizonGame(Game):
    """Goal Horizon game: player interacts with NPC across scenes to understand their limits."""

    DEFAULT_RETRY_BUDGET = 10
    DEFAULT_MAX_INPUT_LENGTH = 350

    def __init__(
        self,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
        validator: ValidatorClient,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        max_input_length: int = DEFAULT_MAX_INPUT_LENGTH,
    ) -> None:
        """Initialise the game. Use create_from_context() as the public entry point."""
        self._pc = pc
        self._npc = npc
        self._updater = updater
        self._validator = validator
        self._retry_budget = retry_budget
        self._max_input_length = max_input_length
        self._entered = False
        self._exited = False
        self._exit_reason = ""
        self._awaiting_capability_prediction = False
        self._capability_prediction = ""

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "GoalHorizonGame":
        """Factory called by SessionManager. Builds clients from character dicts.

        Accepted kwargs:
            retry_budget (int): overrides DEFAULT_RETRY_BUDGET
            max_input_length (int): overrides DEFAULT_MAX_INPUT_LENGTH
        """
        updater = UpdaterClient(system_prompt=build_updater_prompt(pc, npc))
        validator = ValidatorClient(system_prompt_template=build_validator_prompt(pc, npc))
        return cls(
            pc=pc,
            npc=npc,
            updater=updater,
            validator=validator,
            retry_budget=kwargs.get("retry_budget", cls.DEFAULT_RETRY_BUDGET),
            max_input_length=kwargs.get("max_input_length", cls.DEFAULT_MAX_INPUT_LENGTH),
        )

    def exit(self, reason: str) -> None:
        """Mark the game as ended."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        logger.info(f"GoalHorizonGame exited: {reason}")

    @property
    def exited(self) -> bool:
        """True if the game has ended."""
        return self._exited

    @property
    def exit_reason(self) -> str:
        """Reason the game ended, or empty string."""
        return self._exit_reason

    @property
    def capability_prediction(self) -> str:
        """Player's inferred capability limits, or empty string."""
        return self._capability_prediction

    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn, yielding one or more GameEvents."""
        if self._exited:
            return

        if not self._entered:
            self._entered = True
            yield GameEvent.now(
                type="info",
                content=C.ENTER_CONTENT.format(
                    pc_hid=self._pc.hid,
                    pc_short_description=self._pc.short_description,
                    npc_hid=self._npc.hid,
                    npc_short_description=self._npc.short_description,
                ),
            )
            opening = await self._updater.chat(None)
            yield GameEvent.now(type="ai", content=opening)
            return

        if not user_input:
            return

        if self._awaiting_capability_prediction:
            self._capability_prediction = user_input
            self._awaiting_capability_prediction = False
            self.exit("game completed")
            yield GameEvent.now(type="info", content="Thank you. Game complete.")
            return

        command_event = self._handle_command(user_input)
        if command_event is not None:
            yield command_event
            return

        if len(user_input) > self._max_input_length:
            yield GameEvent.now(
                type="error",
                content=f"Input exceeds maximum length of {self._max_input_length} characters.",
            )
            return

        validation = await self._validator.validate(user_input)
        if validation.get("type") == "error":
            self._retry_budget -= 1
            logger.debug(f"Validation failed. Retry budget remaining: {self._retry_budget}")
            if self._retry_budget <= 0:
                self.exit("retry budget exhausted")
                yield GameEvent.now(type="error", content=validation.get("content", "Invalid action."))
                yield GameEvent.now(type="info", content="You have used all your allowed retries. The game is ending.")
                return
            yield GameEvent.now(type="error", content=validation.get("content", "Invalid action."))
            return

        reply = await self._updater.chat(user_input)
        yield GameEvent.now(type="ai", content=reply)

    def _handle_command(self, user_input: str) -> GameEvent | None:
        """Return a GameEvent for recognised game-level commands, or None to continue."""
        stripped = user_input.strip()
        if not stripped.startswith("/"):
            return None

        command_body = stripped[1:].strip()
        if not command_body:
            return None
        parts = command_body.split(maxsplit=1)
        cmd = parts[0].lower()
        remainder = parts[1].strip() if len(parts) > 1 else ""

        if cmd == Command.HELP:
            return GameEvent.now(type="info", content=C.HELP_CONTENT, command_response=True)
        if cmd == Command.PREDICT_CAPABILITIES:
            if remainder:
                self._capability_prediction = remainder
                self._awaiting_capability_prediction = False
                self.exit("game completed")
                return GameEvent.now(type="info", content="Thank you. Game complete.", command_response=True)
            self._awaiting_capability_prediction = True
            return GameEvent.now(type="info", content=C.CAPABILITY_PREDICTION_QUESTION, command_response=True)

        return None
