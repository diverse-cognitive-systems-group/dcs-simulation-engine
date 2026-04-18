"""Foresight game."""

import re
from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters import get_character_filter
from dcs_simulation_engine.dal.character_filters.base import CharacterFilter
from dcs_simulation_engine.games.ai_client import ScorerClient, SimulatorClient
from dcs_simulation_engine.games.const import Foresight as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown, format_score_markdown
from dcs_simulation_engine.games.prompts import (
    SCORER_NEXT_ACTION,
    build_scorer_prompt,
)
from loguru import logger


class ForesightGame(Game):
    """Foresight game: player interacts with NPC and makes predictions embedded in their actions."""

    GAME_NAME = "Foresight"
    GAME_DESCRIPTION = "Players are tasked with predicting the next action of a character."

    # This game required players to describe their PC action but also how they expect the NPC to respond for each turn, so we need to remove the validators that enforce that players only describe their own character's actions. Instead, we use a validator that required the PC action and optional NPC prediction.
    PLAYER_TURN_VALIDATORS = []

    DEFAULT_PCS_ALLOWED: CharacterFilter = get_character_filter("human-normative")

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for ForesightGame."""

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
        self._predictions: dict[str, Any] = {}
        self._score: dict[str, Any] = {}

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "ForesightGame":
        """Factory called by SessionManager."""
        scorer = kwargs.pop("scorer", None)
        overrides = cls.Overrides.model_validate(kwargs)
        engine = SimulatorClient(
            pc=pc,
            npc=npc,
            player_turn_validators=cls.PLAYER_TURN_VALIDATORS,
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
    def predictions(self) -> dict[str, Any]:
        """Return the current predictions."""
        return self._predictions

    @property
    def score(self) -> dict[str, Any]:
        """Return the current score."""
        return self._score

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
        """Score the final prediction, then exit."""
        await self._score_prediction()

        if self._show_final_score:
            yield GameEvent.now(type="info", content=format_score_markdown(self._score))

        self.exit("player finished")
        yield GameEvent.now(
            type="info",
            content=C.FINISH_CONTENT.format(finish_reason="player finished"),
            command_response=True,
        )

    async def _score_prediction(self) -> None:
        """Score the player's latest next-action prediction."""
        try:
            transcript = self.get_transcript().strip()
            if not transcript:
                raise ValueError("Foresight scoring requires a non-empty transcript.")

            guess = self._get_latest_prediction_guess(transcript)
            if not guess:
                raise ValueError("Foresight scoring requires a recorded prediction.")

            prompt = build_scorer_prompt(
                scoring_template=SCORER_NEXT_ACTION,
                npc=self._npc,
                transcript=transcript,
                guess=guess,
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
                "reasoning": "Final score could not be computed.",
            }

    def _get_latest_prediction_guess(self, transcript: str) -> str:
        """Return the latest prediction from stored state or transcript."""
        if self._predictions:
            latest_prediction = next(reversed(self._predictions.values()))
            guess = self._coerce_prediction_guess(latest_prediction)
            if guess:
                return guess

        for line in reversed(transcript.splitlines()):
            stripped_line = line.strip()
            if not stripped_line:
                continue

            _, _, content = stripped_line.partition(":")
            candidate = content.strip() if content else stripped_line
            if not candidate:
                continue

            if candidate.lower().startswith("/predict-next"):
                return candidate[len("/predict-next") :].strip()

            if re.search(r"\bpredict(?:ion|ed|s)?\b", candidate, flags=re.IGNORECASE):
                return candidate

        return ""

    def _coerce_prediction_guess(self, prediction: Any) -> str:
        """Extract a string prediction from common payload shapes."""
        if isinstance(prediction, str):
            return prediction.strip()

        if isinstance(prediction, dict):
            for key in ("guess", "prediction", "content", "text", "value"):
                value = prediction.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""
