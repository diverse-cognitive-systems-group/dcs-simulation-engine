"""Teamwork game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter
from dcs_simulation_engine.dal.character_filters.base import CharacterFilter
from dcs_simulation_engine.games.ai_client import ScorerClient, SimulatorClient
from dcs_simulation_engine.games.const import Teamwork as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown, format_score_markdown
from dcs_simulation_engine.games.prompts import OPENER_WITH_SHARED_GOAL, SCORER_SHARED_GOAL, build_scorer_prompt
from loguru import logger


class TeamworkGame(Game):
    """Teamwork game: player collaborates with NPC toward a shared goal."""

    GAME_NAME = "Teamwork"
    GAME_DESCRIPTION = "Players are tasked with collaborating with another character to achieve a shared goal."

    DEFAULT_PCS_ALLOWED: CharacterFilter = get_character_filter("human-normative")
    # Note: NPCs have to be able to move towards a textually described objective. All pc_eligible characters can do this.
    DEFAULT_NPCS_ALLOWED: CharacterFilter = get_character_filter("all")

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for TeamworkGame."""

        show_npc_details: bool = True
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
        self._challenges = ""
        self._shared_goal = ""
        self._score: dict[str, Any] = {}

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "TeamworkGame":
        """Factory called by SessionManager."""
        scorer = kwargs.pop("scorer", None)
        overrides = cls.Overrides.model_validate(kwargs)
        engine = SimulatorClient(pc=pc, npc=npc, opener_template=OPENER_WITH_SHARED_GOAL)
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
    def shared_goal(self) -> str:
        """The shared goal for this game instance."""
        return self._shared_goal

    @property
    def challenges(self) -> str:
        """Player's reflection on challenges, or empty string."""
        return self._challenges

    @property
    def score(self) -> dict[str, Any]:
        """Scorer result, or empty dict."""
        return self._score

    def _consume_model_metadata(self, *, stage: str, metadata: dict[str, Any]) -> None:
        """Persist shared goal metadata produced by the model."""
        if stage != "opening":
            return

        shared_goal = metadata.get("shared_goal")
        if isinstance(shared_goal, str) and shared_goal.strip():
            self._shared_goal = shared_goal.strip()

    def get_setup_content(self) -> str:
        """Return custom setup with goal."""
        return self.get_help_content()

    def get_help_content(self) -> str:
        """Return the /help message content."""
        return C.HELP_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description.lower(),
            npc_hid=self._npc.hid,
            npc_short_description=(self._npc.data.get("short_description", "").lower() if self._show_npc_details else "*Details hidden.*"),
            shared_goal=self._shared_goal,
        )

    def get_abilities_content(self) -> str:
        """Return the /abilities message content."""
        npc_abilities = format_abilities_markdown(self._npc.data.get("abilities", "")) if self._show_npc_details else "*Details hidden.*"
        return C.ABILITIES_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            pc_abilities=format_abilities_markdown(self._pc.data.get("abilities", "")),
            npc_hid=self._npc.hid,
            npc_short_description=(self._npc.data.get("short_description", "") if self._show_npc_details else "*Details hidden.*"),
            npc_abilities=npc_abilities,
        )

    async def on_finish(self) -> AsyncIterator[GameEvent]:
        """Ask the challenges reflection question before exiting."""
        self._in_finish_flow = True
        yield GameEvent.now(type="info", content=C.CHALLENGES_QUESTION, command_response=True)

    async def on_finish_input(self, user_input: str) -> AsyncIterator[GameEvent]:
        """Store challenges answer, score, then exit."""
        self._challenges = user_input
        self._in_finish_flow = False

        await self._score_teamwork()

        if self._show_final_score:
            yield GameEvent.now(type="info", content=format_score_markdown(self._score))

        self.exit("player finished")
        yield GameEvent.now(type="info", content=C.FINISH_CONTENT.format(finish_reason="player finished"))

    async def _score_teamwork(self) -> None:
        """Score the player's teamwork reflection against collaborative performance."""
        try:
            transcript = self.get_transcript().strip()
            if not transcript:
                raise ValueError("Teamwork scoring requires a non-empty transcript.")

            prompt = build_scorer_prompt(
                scoring_template=SCORER_SHARED_GOAL,
                npc=self._npc,
                pc=self._pc,
                transcript=transcript,
                shared_goal=self._shared_goal,
                guess=self._challenges,
            )

            result = await self._scorer.score(prompt=prompt, transcript=transcript)
            self._score = result.evaluation or {}

            if not isinstance(self._score, dict):
                raise ValueError("Invalid scorer output format.")

        except Exception:
            logger.exception("Failed to compute final score.")
            self._score = {
                "tier": None,
                "score": None,
                "reasoning": "Final score couldn't be computed.",
            }
