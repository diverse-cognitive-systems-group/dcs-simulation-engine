"""Base game config module."""

import importlib
from typing import Annotated, Any, Dict, List, Optional, Tuple

from dcs_simulation_engine.core.forms import ExperimentForm
from dcs_simulation_engine.dal.base import CharacterRecord, DataProvider
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.serde import SerdeMixin
from pydantic import BaseModel, ConfigDict, Field, constr

VersionStr = Annotated[
    str,
    constr(
        pattern=(
            r"^(0|[1-9]\d*)\."
            r"(0|[1-9]\d*)\."
            r"(0|[1-9]\d*)"
            r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
        )
    ),
]


class GameConfig(SerdeMixin, BaseModel):
    """Top-level configuration for the game."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    name: str
    description: str
    version: VersionStr
    authors: Optional[List[str]] = Field(default_factory=lambda: ["DCS"])
    stopping_conditions: Dict[str, Any] = Field(default_factory=dict)
    forms: List[ExperimentForm] = Field(default_factory=list)

    # Dotted import path to the game engine class, e.g.
    # "dcs_simulation_engine.games.explore.ExploreGame"
    game_class: str

    def get_game_class(self) -> Any:
        """Dynamically import and return the configured game class."""
        module_path, class_name = self.game_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        return getattr(module, class_name)

    def get_game_class_instance(self) -> Any:
        """Dynamically import and instantiate the game engine class."""
        return self.get_game_class()()

    @classmethod
    def load(cls, path: Any) -> "GameConfig":
        """Load a GameConfig from a YAML file."""
        return cls.from_yaml(path)

    def get_valid_characters(
        self,
        *,
        player_id: str | None = None,
        provider: DataProvider,
        pc_eligible_only: bool = False,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Return (valid_pcs, valid_npcs) as (display_string, hid) tuples."""
        _ = player_id, pc_eligible_only
        game_cls = self.get_game_class()
        pc_chars = game_cls.DEFAULT_PCS_FILTER.get_characters(provider=provider)
        npc_chars = game_cls.DEFAULT_NPCS_FILTER.get_characters(provider=provider)
        pc_choices = [(record.hid, record.hid) for record in pc_chars]
        npc_choices = [(record.hid, record.hid) for record in npc_chars]
        return pc_choices, npc_choices

    async def get_valid_characters_async(
        self,
        *,
        player_id: str | None = None,
        provider: Any,
        pc_eligible_only: bool = False,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Async-safe variant of get_valid_characters for async providers."""
        _ = player_id, pc_eligible_only
        chars = await maybe_await(provider.get_characters())
        character_provider = _StaticCharacterProvider(chars)
        game_cls = self.get_game_class()
        pc_chars = game_cls.DEFAULT_PCS_FILTER.get_characters(provider=character_provider)
        npc_chars = game_cls.DEFAULT_NPCS_FILTER.get_characters(provider=character_provider)
        pc_choices = [(record.hid, record.hid) for record in pc_chars]
        npc_choices = [(record.hid, record.hid) for record in npc_chars]
        return pc_choices, npc_choices


class _StaticCharacterProvider:
    """Small provider shim for applying sync character filters to async-loaded records."""

    def __init__(self, characters: Any) -> None:
        self._characters = list(characters)

    def get_characters(self) -> list[CharacterRecord]:
        return list(self._characters)
