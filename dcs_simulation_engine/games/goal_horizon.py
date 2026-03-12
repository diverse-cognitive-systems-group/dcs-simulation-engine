"""Goal Horizon game — new-style implementation."""

from enum import StrEnum
from typing import Any, AsyncIterator

from loguru import logger

from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.games.ai_client import UpdaterClient, ValidatorClient
from dcs_simulation_engine.games.const import GoalHorizonV2 as C
from dcs_simulation_engine.games.prompts import build_updater_prompt, build_validator_prompt


class Command(StrEnum):
    """Game-level slash commands recognised by GoalHorizonGame."""

    HELP = "help"
    ABILITIES = "abilities"


class GoalHorizonGame(Game):
    """Goal Horizon game: player interacts with NPC across scenes to understand their goalspace."""

    DEFAULT_RETRY_BUDGET = 10
    DEFAULT_MAX_INPUT_LENGTH = 350

    def __init__(
        self,
        pc: dict[str, Any],
        npc: dict[str, Any],
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

    @classmethod
    def create_from_context(cls, pc: dict[str, Any], npc: dict[str, Any], **kwargs: Any) -> "GoalHorizonGame":
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

    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn, yielding one or more GameEvents."""
        if self._exited:
            return

        # ENTER: first call — emit welcome message then generate the opening scene.
        if not self._entered:
            self._entered = True
            yield GameEvent(
                type="info",
                content=C.ENTER_CONTENT.format(
                    pc_hid=self._pc.get("hid", ""),
                    pc_short_description=self._pc.get("short_description", ""),
                    npc_hid=self._npc.get("hid", ""),
                    npc_short_description=self._npc.get("short_description", ""),
                ),
            )
            opening = await self._updater.chat(None)
            yield GameEvent(type="ai", content=opening)
            return

        if not user_input:
            return

        # Game-level commands (/help, /abilities). Session-level commands
        # (/exit, /quit, /feedback) are already handled by SessionManager.
        command_event = self._handle_command(user_input)
        if command_event is not None:
            yield command_event
            return

        if len(user_input) > self._max_input_length:
            yield GameEvent(
                type="error",
                content=f"Input exceeds maximum length of {self._max_input_length} characters.",
            )
            return

        # Validate before advancing the scene.
        validation = await self._validator.validate(user_input)
        if validation.get("type") == "error":
            self._retry_budget -= 1
            logger.debug(f"Validation failed. Retry budget remaining: {self._retry_budget}")
            if self._retry_budget <= 0:
                self.exit("retry budget exhausted")
                yield GameEvent(type="error", content=validation.get("content", "Invalid action."))
                yield GameEvent(type="info", content="You have used all your allowed retries. The game is ending.")
                return
            yield GameEvent(type="error", content=validation.get("content", "Invalid action."))
            return

        reply = await self._updater.chat(user_input)
        yield GameEvent(type="ai", content=reply)

    def _handle_command(self, user_input: str) -> GameEvent | None:
        """Return a GameEvent for recognised game-level commands, or None to continue."""
        stripped = user_input.strip()
        if not stripped.startswith(("/", "\\")):
            return None

        cmd = stripped.lstrip("/\\").split()[0].lower()

        if cmd == Command.HELP:
            return GameEvent(type="info", content=C.HELP_CONTENT)

        if cmd == Command.ABILITIES:
            return GameEvent(
                type="info",
                content=C.ABILITIES_CONTENT.format(
                    pc_hid=self._pc.get("hid", ""),
                    pc_short_description=self._pc.get("short_description", ""),
                    pc_abilities=self._pc.get("abilities", ""),
                    npc_hid=self._npc.get("hid", ""),
                    npc_short_description=self._npc.get("short_description", ""),
                    npc_abilities=self._npc.get("abilities", ""),
                ),
            )

        # Unrecognised — return None so SessionManager can handle it.
        return None
