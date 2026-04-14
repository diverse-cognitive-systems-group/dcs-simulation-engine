"""Infer Intent game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import EngineClient, UpdaterClient, ValidatorClient
from dcs_simulation_engine.games.const import InferIntent as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown
from dcs_simulation_engine.games.prompts import build_updater_prompt, build_validator_prompt


class InferIntentGame(Game):
    """Infer Intent game: player interacts with NPC and infers their hidden goal."""

    GAME_NAME = "Infer Intent"
    GAME_DESCRIPTION = "Players are tasked with understanding the intention of another character."

    DEFAULT_RETRY_BUDGET = 3
    DEFAULT_MAX_INPUT_LENGTH = 350

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for InferIntentGame."""

        player_retry_budget: int = 3
        hide_npc_details: bool = False

    def __init__(
        self,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        engine: Any,
        retry_budget: int,
        max_input_length: int,
        hide_npc_details: bool,
    ) -> None:
        """Initialise with game-specific inference state."""
        super().__init__(pc=pc, npc=npc, engine=engine, retry_budget=retry_budget, max_input_length=max_input_length)
        self._hide_npc_details = hide_npc_details
        self._goal_inference = ""
        self._goal_inference_confidence = ""
        self._evaluation: dict[str, Any] = {}
        self._awaiting_confidence = False

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "InferIntentGame":
        """Factory called by SessionManager."""
        overrides = cls.Overrides.model_validate(kwargs)
        engine = EngineClient(
            updater=UpdaterClient(system_prompt=build_updater_prompt(pc, npc, additional_rules=C.ADDITIONAL_UPDATER_RULES)),
            validator=ValidatorClient(system_prompt_template=build_validator_prompt(pc, npc)),
        )
        return cls(
            pc=pc,
            npc=npc,
            engine=engine,
            retry_budget=overrides.player_retry_budget,
            max_input_length=cls.DEFAULT_MAX_INPUT_LENGTH,
            hide_npc_details=overrides.hide_npc_details,
        )

    @property
    def finish_command(self) -> str:
        """``/predict-intent`` starts the finish flow."""
        return "predict-intent"

    @property
    def goal_inference(self) -> str:
        """Player's inferred goal, or empty string."""
        return self._goal_inference

    @property
    def goal_inference_confidence(self) -> str:
        """Player's confidence in their goal inference, or empty string."""
        return self._goal_inference_confidence

    @property
    def evaluation(self) -> dict[str, Any]:
        """LLM scoring result, or empty dict."""
        return self._evaluation

    def get_help_content(self) -> str:
        """Return the /help message content."""
        return C.HELP_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            npc_hid=self._npc.hid,
        )

    def get_abilities_content(self) -> str:
        """Return the /abilities message content."""
        npc_abilities = (
            format_abilities_markdown(self._npc.data.get("abilities", ""))
            if self._hide_npc_details
            else "*NPC details are hidden.*"
        )
        return C.ABILITIES_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            pc_abilities=format_abilities_markdown(self._pc.data.get("abilities", "")),
            npc_hid=self._npc.hid,
            npc_abilities=npc_abilities,
        )

    async def on_finish(self) -> AsyncIterator[GameEvent]:
        """Start the inference collection flow."""
        self._in_finish_flow = True
        self._awaiting_confidence = False
        yield GameEvent.now(type="info", content=C.GOAL_INFERENCE_QUESTION, command_response=True)

    async def on_finish_input(self, user_input: str) -> AsyncIterator[GameEvent]:
        """Collect inference then confidence, then exit."""
        if not self._awaiting_confidence:
            self._goal_inference = user_input
            self._awaiting_confidence = True
            yield GameEvent.now(type="info", content=C.GOAL_INFERENCE_CONFIDENCE)
        else:
            self._goal_inference_confidence = user_input
            self._in_finish_flow = False
            self.exit("player finished")
            yield GameEvent.now(type="info", content=C.FINISH_CONTENT.format(finish_reason="player finished"))
