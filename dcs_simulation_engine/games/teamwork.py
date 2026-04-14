"""Teamwork game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import BaseGameOverrides, Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import EngineClient, UpdaterClient, ValidatorClient
from dcs_simulation_engine.games.const import Teamwork as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown
from dcs_simulation_engine.games.prompts import build_updater_prompt, build_validator_prompt


class TeamworkGame(Game):
    """Teamwork game: player collaborates with NPC toward a shared goal."""

    GAME_NAME = "Teamwork"
    GAME_DESCRIPTION = "Players are tasked with collaborating with another character to achieve a shared goal."

    DEFAULT_RETRY_BUDGET = 10
    DEFAULT_MAX_INPUT_LENGTH = 350

    class Overrides(BaseGameOverrides):
        """Run-config-overridable parameters for TeamworkGame."""

        player_retry_budget: int = 10

    def __init__(self, *, pc: CharacterRecord, npc: CharacterRecord, engine: Any, retry_budget: int, max_input_length: int) -> None:
        """Initialise with game-specific challenges state."""
        super().__init__(pc=pc, npc=npc, engine=engine, retry_budget=retry_budget, max_input_length=max_input_length)
        self._challenges = ""

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "TeamworkGame":
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
        )

    @property
    def finish_command(self) -> str:
        """``/finish`` starts the challenges collection flow."""
        return "finish"

    @property
    def challenges(self) -> str:
        """Player's reflection on challenges, or empty string."""
        return self._challenges

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
        """Ask the challenges reflection question before exiting."""
        self._in_finish_flow = True
        yield GameEvent.now(type="info", content=C.CHALLENGES_QUESTION, command_response=True)

    async def on_finish_input(self, user_input: str) -> AsyncIterator[GameEvent]:
        """Store challenges answer then exit."""
        self._challenges = user_input
        self._in_finish_flow = False
        self.exit("player finished")
        yield GameEvent.now(type="info", content=C.FINISH_CONTENT.format(finish_reason="player finished"))
