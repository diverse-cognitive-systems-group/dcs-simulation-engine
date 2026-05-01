"""Base game config module."""

import importlib
from typing import Annotated, Any, Dict, List, Optional, Tuple

from dcs_simulation_engine.core.forms import Form
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
    forms: List[Form] = Field(default_factory=list)
    overrides: Dict[str, Any] = Field(default_factory=dict)

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
    def from_game_class(cls, game_cls: Any, *, overrides: dict[str, Any] | None = None) -> "GameConfig":
        """Build a GameConfig from a concrete Game class and optional run overrides."""
        raw_overrides = dict(overrides or {})
        parsed_overrides = game_cls.parse_overrides(raw_overrides)
        max_turns = parsed_overrides.max_turns if parsed_overrides.max_turns is not None else game_cls.DEFAULT_MAX_TURNS
        max_playtime = (
            parsed_overrides.max_playtime if parsed_overrides.max_playtime is not None else game_cls.DEFAULT_MAX_PLAYTIME
        )
        return cls(
            name=game_cls.GAME_NAME,
            description=game_cls.GAME_DESCRIPTION,
            version="1.0.0",
            authors=["DCS"],
            stopping_conditions={
                "runtime_seconds": [f">={max_playtime}"],
                "turns": [f">={max_turns}"],
            },
            game_class=f"{game_cls.__module__}.{game_cls.__name__}",
            overrides=raw_overrides,
        )

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
        overrides = game_cls.parse_overrides(self.overrides)
        filters = game_cls.build_base_init_kwargs(overrides)
        pc_filter = filters["pcs_allowed"]
        npc_filter = filters["npcs_allowed"]
        pc_chars = pc_filter.get_characters(provider=provider)
        npc_chars = npc_filter.get_characters(provider=provider)
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
        overrides = game_cls.parse_overrides(self.overrides)
        filters = game_cls.build_base_init_kwargs(overrides)
        pc_filter = filters["pcs_allowed"]
        npc_filter = filters["npcs_allowed"]
        pc_chars = pc_filter.get_characters(provider=character_provider)
        npc_chars = npc_filter.get_characters(provider=character_provider)
        pc_choices = [(record.hid, record.hid) for record in pc_chars]
        npc_choices = [(record.hid, record.hid) for record in npc_chars]
        return pc_choices, npc_choices


class _StaticCharacterProvider:
    """Small provider shim for applying sync character filters to async-loaded records."""

    def __init__(self, characters: Any) -> None:
        self._characters = list(characters)

    def get_characters(self) -> list[CharacterRecord]:
        return list(self._characters)
