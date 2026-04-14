"""Teamwork game."""

from enum import StrEnum
from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import (
    UpdaterClient,
    ValidatorClient,
)
from dcs_simulation_engine.games.const import Teamwork as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown
from dcs_simulation_engine.games.prompts import (
    build_updater_prompt,
    build_validator_prompt,
)
from loguru import logger


class Command(StrEnum):
    """Game-level slash commands recognised by TeamworkGame."""

    HELP = "help"
    ABILITIES = "abilities"
    FINISH = "finish"


class TeamworkGame(Game):
    """Teamwork game: player collaborates with NPC toward a shared goal."""

    GAME_NAME = "Teamwork"
    GAME_DESCRIPTION = "Players are tasked with collaborating with another character to achieve a shared goal."

    DEFAULT_RETRY_BUDGET = 10
    DEFAULT_MAX_INPUT_LENGTH = 350

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for TeamworkGame."""

        player_retry_budget: int = 10

    def __init__(
        self,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
        validator: ValidatorClient,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        max_input_length: int = DEFAULT_MAX_INPUT_LENGTH,
        enter_message: str | None = None,
        help_message: str | None = None,
        exit_message: str | None = None,
    ) -> None:
        """Initialise the game. Use create_from_context() as the public entry point."""
        self._pc = pc
        self._npc = npc
        self._updater = updater
        self._validator = validator
        self._retry_budget = retry_budget
        self._max_input_length = max_input_length
        self._enter_message = enter_message
        self._help_message = help_message
        self._exit_message = exit_message
        self._entered = False
        self._exited = False
        self._exit_reason = ""
        self._awaiting_challenges = False
        self._challenges = ""

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "TeamworkGame":
        """Factory called by SessionManager. Builds clients from character dicts.

        Accepted kwargs are validated against ``TeamworkGame.Overrides``.
        """
        overrides = cls.Overrides.model_validate(kwargs)
        updater = UpdaterClient(system_prompt=build_updater_prompt(pc, npc))
        validator = ValidatorClient(system_prompt_template=build_validator_prompt(pc, npc))
        return cls(
            pc=pc,
            npc=npc,
            updater=updater,
            validator=validator,
            retry_budget=overrides.player_retry_budget,
            max_input_length=cls.DEFAULT_MAX_INPUT_LENGTH,
        )

    def exit(self, reason: str) -> None:
        """Mark the game as ended."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        logger.info(f"TeamworkGame exited: {reason}")

    @property
    def exited(self) -> bool:
        """True if the game has ended."""
        return self._exited

    @property
    def exit_reason(self) -> str:
        """Reason the game ended, or empty string."""
        return self._exit_reason

    @property
    def challenges(self) -> str:
        """Player's reflection on challenges, or empty string."""
        return self._challenges

    def _format_help(self) -> str:
        return self._help_message or C.HELP_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            npc_hid=self._npc.hid,
        )

    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn, yielding one or more GameEvents."""
        if self._exited:
            return

        if not self._entered:
            self._entered = True
            yield GameEvent.now(
                type="info",
                content=self._enter_message or self._format_help(),
            )
            opening = await self._updater.chat(None)
            yield GameEvent.now(type="ai", content=opening)
            return

        if not user_input:
            return

        if self._awaiting_challenges:
            self._challenges = user_input
            self._awaiting_challenges = False
            self.exit("player finished")
            yield GameEvent.now(
                type="info",
                content=self._exit_message or C.FINISH_CONTENT.format(finish_reason="player finished"),
            )

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
        cmd = command_body.split()[0].lower()

        if cmd == Command.HELP:
            return GameEvent.now(
                type="info",
                content=self._format_help(),
                command_response=True,
            )

        if cmd == Command.ABILITIES:
            return GameEvent.now(
                type="info",
                content=C.ABILITIES_CONTENT.format(
                    pc_hid=self._pc.hid,
                    pc_short_description=self._pc.short_description,
                    pc_abilities=format_abilities_markdown(self._pc.data.get("abilities", "")),
                    npc_hid=self._npc.hid,
                ),
                command_response=True,
            )

        if cmd == Command.FINISH:
            self._awaiting_challenges = True
            return GameEvent.now(type="info", content=C.CHALLENGES_QUESTION, command_response=True)

        return None
