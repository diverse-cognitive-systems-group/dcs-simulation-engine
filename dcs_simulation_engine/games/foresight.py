"""Foresight game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import EngineClient, UpdaterClient, ValidatorClient
from dcs_simulation_engine.games.const import Foresight as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown
from dcs_simulation_engine.games.prompts import build_updater_prompt, build_validator_prompt


class ForesightGame(Game):
    """Foresight game: player interacts with NPC and makes predictions embedded in their actions."""

    GAME_NAME = "Foresight"
    GAME_DESCRIPTION = "Players are tasked with predicting the next action of a character."

    DEFAULT_RETRY_BUDGET = 10
    DEFAULT_MAX_INPUT_LENGTH = 350

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for ForesightGame."""

        player_retry_budget: int = 10
        max_predictions: int = 3
        min_predictions: int = 1

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "ForesightGame":
        """Factory called by SessionManager."""
        overrides = cls.Overrides.model_validate(kwargs)
        engine = EngineClient(
            updater=UpdaterClient(system_prompt=build_updater_prompt(pc, npc, additional_rules=C.ADDITIONAL_UPDATER_RULES)),
            validator=ValidatorClient(
                system_prompt_template=build_validator_prompt(pc, npc, additional_rules=C.ADDITIONAL_VALIDATOR_RULES)
            ),
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
        """``/finish`` ends the game."""
        return "finish"

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
        )

    async def on_finish(self) -> AsyncIterator[GameEvent]:
        """Exit immediately and emit a closing message."""
        self.exit("player finished")
        yield GameEvent.now(
            type="info",
            content=C.FINISH_CONTENT.format(finish_reason="player finished"),
            command_response=True,
        )
