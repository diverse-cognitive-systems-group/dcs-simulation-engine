"""Goal Horizon game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import EngineClient, UpdaterClient, ValidatorClient
from dcs_simulation_engine.games.const import GoalHorizon as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown
from dcs_simulation_engine.games.prompts import build_updater_prompt, build_validator_prompt


class GoalHorizonGame(Game):
    """Goal Horizon game: player interacts with NPC across scenes to understand their limits."""

    GAME_NAME = "Goal Horizon"
    GAME_DESCRIPTION = "Players are tasked with understanding the capabilities and limitations of another character."

    DEFAULT_RETRY_BUDGET = 10
    DEFAULT_MAX_INPUT_LENGTH = 350

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for GoalHorizonGame."""

        player_retry_budget: int = 10

    def __init__(self, *, pc: CharacterRecord, npc: CharacterRecord, engine: Any, retry_budget: int, max_input_length: int) -> None:
        """Initialise with game-specific prediction state."""
        super().__init__(pc=pc, npc=npc, engine=engine, retry_budget=retry_budget, max_input_length=max_input_length)
        self._capability_prediction = ""
        self._capability_prediction_confidence = ""
        self._awaiting_confidence = False

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "GoalHorizonGame":
        """Factory called by SessionManager."""
        overrides = cls.Overrides.model_validate(kwargs)
        engine = EngineClient(
            updater=UpdaterClient(system_prompt=build_updater_prompt(pc, npc)),
            validator=ValidatorClient(system_prompt_template=build_validator_prompt(pc, npc)),
        )
        return cls(
            pc=pc,
            npc=npc,
            engine=engine,
            retry_budget=overrides.player_retry_budget,
            max_input_length=cls.DEFAULT_MAX_INPUT_LENGTH,
        )

    @property
    def finish_command(self) -> str:
        """``/predict-capabilities`` starts the finish flow."""
        return "predict-capabilities"

    @property
    def capability_prediction(self) -> str:
        """Player's inferred capability limits, or empty string."""
        return self._capability_prediction

    @property
    def capability_prediction_confidence(self) -> str:
        """Player's confidence in their capability prediction, or empty string."""
        return self._capability_prediction_confidence

    def get_setup_content(self) -> str:
        """Return the enter message (different from help content for this game)."""
        return C.ENTER_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            npc_hid=self._npc.hid,
            npc_short_description=self._npc.short_description,
        )

    def get_help_content(self) -> str:
        """Return the /help message content."""
        return C.HELP_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            npc_hid=self._npc.hid,
        )

    def get_abilities_content(self) -> str:
        """Return the /abilities message content."""
        return C.ABILITIES_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            pc_abilities=format_abilities_markdown(self._pc.data.get("abilities", "")),
            npc_hid=self._npc.hid,
            npc_short_description=self._npc.short_description,
            npc_abilities=format_abilities_markdown(self._npc.data.get("abilities", "")),
        )

    async def on_finish(self) -> AsyncIterator[GameEvent]:
        """Start the capability prediction collection flow."""
        self._in_finish_flow = True
        self._awaiting_confidence = False
        yield GameEvent.now(
            type="info",
            content=C.CAPABILITY_PREDICTION_QUESTION.format(npc_hid=self._npc.hid),
            command_response=True,
        )

    async def on_finish_input(self, user_input: str) -> AsyncIterator[GameEvent]:
        """Collect prediction then confidence, then exit."""
        if not self._awaiting_confidence:
            self._capability_prediction = user_input
            self._awaiting_confidence = True
            yield GameEvent.now(type="info", content=C.CAPABILITY_PREDICTION_CONFIDENCE)
        else:
            self._capability_prediction_confidence = user_input
            self._in_finish_flow = False
            self.exit("player finished")
            yield GameEvent.now(type="info", content=C.FINISH_CONTENT.format(finish_reason="player finished"))
