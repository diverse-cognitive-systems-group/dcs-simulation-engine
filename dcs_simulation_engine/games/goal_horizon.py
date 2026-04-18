"""Goal Horizon game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter
from dcs_simulation_engine.dal.character_filters.base import CharacterFilter
from dcs_simulation_engine.games.ai_client import ScorerClient, SimulatorClient
from dcs_simulation_engine.games.const import GoalHorizon as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown, format_score_markdown
from dcs_simulation_engine.games.prompts import SCORER_GOAL_BOUNDS, build_scorer_prompt
from loguru import logger


class GoalHorizonGame(Game):
    """Goal Horizon game: player interacts with NPC across scenes to understand their limits."""

    GAME_NAME = "Goal Horizon"
    GAME_DESCRIPTION = "Players are tasked with understanding the capabilities and limitations of another character."

    DEFAULT_PCS_ALLOWED: CharacterFilter = get_character_filter("human-normative")

    class Overrides(Game.Overrides):
        """Run-config-overridable parameters for GoalHorizonGame."""

        show_npc_details: bool = False
        show_final_score: bool = True

    def __init__(
        self,
        *,
        show_npc_details: bool,
        show_final_score: bool,
        scorer: ScorerClient | None = None,
        **kwargs: Any,  # kwargs for base args
    ) -> None:
        """Initialise with game-specific prediction state."""
        super().__init__(**kwargs)
        self._show_npc_details = show_npc_details
        self._show_final_score = show_final_score
        self._scorer = scorer or ScorerClient()
        self._capability_prediction = ""
        self._capability_prediction_confidence = ""
        self._awaiting_confidence = False

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "GoalHorizonGame":
        """Factory called by SessionManager."""
        scorer = kwargs.pop("scorer", None)
        overrides = cls.Overrides.model_validate(kwargs)
        engine = SimulatorClient(
            pc=pc,
            npc=npc,
        )
        return cls(
            pc=pc,
            npc=npc,
            engine=engine,
            scorer=scorer,
            **cls.build_base_init_kwargs(overrides),
            show_npc_details=overrides.show_npc_details,
            show_final_score=overrides.show_final_score,
        )

    @property
    def capability_prediction(self) -> str:
        """Player's inferred capability limits, or empty string."""
        return self._capability_prediction

    @property
    def capability_prediction_confidence(self) -> str:
        """Player's confidence in their capability prediction, or empty string."""
        return self._capability_prediction_confidence

    def get_help_content(self) -> str:
        """Return the /help message content."""
        return C.HELP_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            npc_hid=self._npc.hid,
            npc_short_description=self._npc.data.get("short_description", "") if self._show_npc_details else "*NPC details are hidden.*",
        )

    def get_abilities_content(self) -> str:
        """Return the /abilities message content."""
        npc_abilities = (
            format_abilities_markdown(self._npc.data.get("abilities", "")) if self._show_npc_details else "*NPC details are hidden.*"
        )
        return C.ABILITIES_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            pc_abilities=format_abilities_markdown(self._pc.data.get("abilities", "")),
            npc_hid=self._npc.hid,
            npc_short_description=(self._npc.data.get("short_description", "") if self._show_npc_details else "*NPC details are hidden.*"),
            npc_abilities=npc_abilities,
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
            return

        self._capability_prediction_confidence = user_input
        self._in_finish_flow = False

        await self._score_capability_prediction()

        if self._show_final_score:
            yield GameEvent.now(type="info", content=format_score_markdown(self._score))

        self.exit("player finished")
        yield GameEvent.now(type="info", content=C.FINISH_CONTENT.format(finish_reason="player finished"))

    async def _score_capability_prediction(self) -> None:
        """Score the player's capability prediction."""
        try:
            transcript = self.get_transcript().strip()
            if not transcript:
                raise ValueError("Goal Horizon scoring requires a non-empty transcript.")

            prompt = build_scorer_prompt(
                scoring_template=SCORER_GOAL_BOUNDS,
                npc=self._npc,
                transcript=transcript,
                guess=self._capability_prediction,
            )

            result = await self._scorer.score(prompt=prompt, transcript=transcript)
            self._score = result.evaluation or {}

            # Guard against malformed scorer output
            if not isinstance(self._score, dict):
                raise ValueError("Invalid scorer output format.")

        except Exception:
            logger.exception("Failed to compute final score.")
            self._score = {
                "tier": None,
                "score": None,
                "reasoning": "Final score couldn't be computed.",
            }
