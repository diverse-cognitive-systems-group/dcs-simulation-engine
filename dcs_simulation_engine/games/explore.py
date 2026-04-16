"""Explore game."""

from typing import Any, AsyncIterator

from dcs_simulation_engine.core.game import Game, GameEvent
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import SimulatorClient
from dcs_simulation_engine.games.const import Explore as C
from dcs_simulation_engine.games.markdown_helpers import format_abilities_markdown


class ExploreGame(Game):
    """Free-form exploration game: player describes actions, NPC reacts, no predefined goals."""

    GAME_NAME = "Explore"
    GAME_DESCRIPTION = "Players are given no tasks -- an open-ended playground."

    class Overrides(Game.Overrides):
        """Run-config-overridable parameters for ExploreGame."""

        pass  # no additional overrides

    @classmethod
    def create_from_context(cls, pc: CharacterRecord, npc: CharacterRecord, **kwargs: Any) -> "ExploreGame":
        """Factory called by SessionManager."""
        overrides = cls.Overrides.model_validate(kwargs)
        engine = SimulatorClient(pc=pc, npc=npc)
        return cls(
            pc=pc,
            npc=npc,
            engine=engine,
            **cls.build_base_init_kwargs(overrides),
        )

    def get_help_content(self) -> str:
        """Return the /help message content."""
        return C.HELP_CONTENT.format(
            pc_hid=self._pc.hid,
            pc_short_description=self._pc.short_description,
            npc_hid=self._npc.hid,
            npc_short_description=self._npc.short_description,
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
        """Exit immediately and emit a closing message."""
        self.exit("player finished")
        yield GameEvent.now(
            type="info",
            content=C.FINISH_CONTENT.format(finish_reason="player finished"),
            command_response=True,
        )
