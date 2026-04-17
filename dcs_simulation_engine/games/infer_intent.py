"""Infer Intent game."""

from enum import StrEnum
from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import (
    UpdaterClient,
    ValidationOrchestrator,
    ValidatorClient,
    format_ensemble_failures,
)
from dcs_simulation_engine.games.const import (
    InferIntent as C,
)
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown
from dcs_simulation_engine.games.prompts import (
    build_updater_prompt,
    build_validator_prompt,
)
from loguru import logger


class Command(StrEnum):
    """Game-level slash commands recognised by InferIntentGame."""

    HELP = "help"
    ABILITIES = "abilities"
    PREDICT_INTENT = "predict-intent"


class InferIntentGame(Game):
    """Infer Intent game: player interacts with NPC and infers their hidden goal."""

    DEFAULT_RETRY_BUDGET = 3
    DEFAULT_MAX_INPUT_LENGTH = 350

    def __init__(
        self,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
        validator: ValidatorClient,
        ensemble_orchestrator: ValidationOrchestrator | None = None,
        retry_budget: int = DEFAULT_RETRY_BUDGET,
        max_input_length: int = DEFAULT_MAX_INPUT_LENGTH,
    ) -> None:
        """Initialise the game. Use create_from_context() as the public entry point."""
        self._pc = pc
        self._npc = npc
        self._updater = updater
        self._validator = validator
        self._ensemble = ensemble_orchestrator
        self._retry_budget = retry_budget
        self._max_input_length = max_input_length
        self._entered = False
        self._exited = False
        self._exit_reason = ""

        self._awaiting_goal_inference = False
        self._awaiting_goal_inference_confidence = False
        self._goal_inference = ""
        self._goal_inference_confidence = ""
        self._evaluation: dict[str, Any] = {}

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "InferIntentGame":
        """Factory called by SessionManager. Builds clients from character dicts.

        Accepted kwargs:
            retry_budget (int): overrides DEFAULT_RETRY_BUDGET
            max_input_length (int): overrides DEFAULT_MAX_INPUT_LENGTH
            game_name (str): game name for GameValidator lookup
            is_llm_player (bool): whether the PC is LLM-controlled
        """
        updater = UpdaterClient(system_prompt=build_updater_prompt(pc, npc, additional_rules=C.ADDITIONAL_UPDATER_RULES))
        validator = ValidatorClient(system_prompt_template=build_validator_prompt(pc, npc))
        ensemble = ValidationOrchestrator.create(
            game_name=kwargs.get("game_name", "infer intent"),
            is_llm_player=kwargs.get("is_llm_player", False),
        )
        return cls(
            pc=pc,
            npc=npc,
            updater=updater,
            validator=validator,
            ensemble_orchestrator=ensemble,
            retry_budget=kwargs.get("retry_budget", cls.DEFAULT_RETRY_BUDGET),
            max_input_length=kwargs.get("max_input_length", cls.DEFAULT_MAX_INPUT_LENGTH),
        )

    def exit(self, reason: str) -> None:
        """Mark the game as ended."""
        if self._exited:
            return
        self._exited = True
        self._exit_reason = reason
        logger.info(f"InferIntentGame exited: {reason}")

    @property
    def exited(self) -> bool:
        """True if the game has ended."""
        return self._exited

    @property
    def exit_reason(self) -> str:
        """Reason the game ended, or empty string."""
        return self._exit_reason

    @property
    def goal_inference(self) -> str:
        """Player's goal inference, or empty string."""
        return self._goal_inference

    @property
    def goal_inference_confidence(self) -> str:
        """Player's confidence in their goal inference, or empty string."""
        return self._goal_inference_confidence

    @property
    def evaluation(self) -> dict[str, Any]:
        """LLM scoring result, or empty dict."""
        return self._evaluation

    async def step(self, user_input: str | None = None) -> AsyncIterator[GameEvent]:
        """Advance the game one turn, yielding one or more GameEvents."""
        if self._exited:
            return

        if not self._entered:
            self._entered = True
            yield GameEvent.now(
                type="info",
                content=C.HELP_CONTENT.format(
                    pc_hid=self._pc.hid,
                    pc_short_description=self._pc.short_description,
                    npc_hid=self._npc.hid,
                ),
            )
            if self._ensemble is not None:
                opening = await self._ensemble.generate_validated_npc_response(
                    None, pc=self._pc, npc=self._npc, updater=self._updater,
                )
                if opening is None:
                    yield GameEvent.now(type="error", content="The simulation could not initialize the scene.")
                    self.exit("npc_validation_failed")
                    return
            else:
                opening = await self._updater.chat(None)
            yield GameEvent.now(type="ai", content=opening)
            return

        if not user_input:
            return

        if self._awaiting_goal_inference:
            self._goal_inference = user_input
            self._awaiting_goal_inference = False
            self._awaiting_goal_inference_confidence = True
            yield GameEvent.now(type="info", content=C.GOAL_INFERENCE_CONFIDENCE)
            return

        if self._awaiting_goal_inference_confidence:
            self._goal_inference_confidence = user_input
            self._awaiting_goal_inference_confidence = False
            self.exit("player finished")
            yield GameEvent.now(type="info", content=C.FINISH_CONTENT.format(finish_reason="player finished"))

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
                yield GameEvent.now(type="info", content="You have used all your allowed retries. The game is closing.")
                return
            yield GameEvent.now(type="error", content=validation.get("content", "Invalid action."))
            return

        # Ensemble validation (Engine + Game + RolePlaying).
        if self._ensemble is not None:
            ensemble_result = await self._ensemble.validate_input(
                user_input, source="pc", pc=self._pc, npc=self._npc,
                updater=self._updater, player_action=user_input,
            )
            if ensemble_result is not None:
                msg = format_ensemble_failures(ensemble_result)
                logger.warning("Ensemble PC validation failed: {}", msg)
                if self._ensemble.is_llm_player:
                    self._retry_budget -= 1
                    if self._retry_budget <= 0:
                        self.exit("retry budget exhausted")
                        yield GameEvent.now(type="error", content=msg)
                        msg_end = "You have used all your allowed retries. The game is ending."
                        yield GameEvent.now(type="info", content=msg_end)
                        return
                yield GameEvent.now(type="error", content=msg)
                return

        # Generate and validate NPC response.
        if self._ensemble is not None:
            reply = await self._ensemble.generate_validated_npc_response(
                user_input, pc=self._pc, npc=self._npc, updater=self._updater,
            )
            if reply is None:
                npc_err = "The simulation could not produce a valid response. Please try a different action."
                yield GameEvent.now(type="error", content=npc_err)
                return
        else:
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
                content=C.HELP_CONTENT.format(
                    pc_hid=self._pc.hid,
                    pc_short_description=self._pc.short_description,
                    npc_hid=self._npc.hid,
                ),
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

        if cmd == Command.PREDICT_INTENT:
            self._awaiting_goal_inference = True
            return GameEvent.now(type="info", content=C.GOAL_INFERENCE_QUESTION, command_response=True)

        return None
