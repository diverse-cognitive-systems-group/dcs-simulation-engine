"""Base game config module."""

import importlib
from typing import Annotated, Any, Dict, List, Optional, Tuple

from dcs_simulation_engine.dal.base import DataProvider
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

    # Dotted import path to the game engine class, e.g.
    # "dcs_simulation_engine.games.explore.ExploreGame"
    game_class: str

    def get_game_class_instance(self) -> Any:
        """Dynamically import and instantiate the game engine class."""
        module_path, class_name = self.game_class.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        return cls()

    @classmethod
    def load(cls, path: Any) -> "GameConfig":
        """Load a GameConfig from a YAML file."""
        return cls.from_yaml(path)

    def get_valid_characters(
        self,
        *,
        player_id: str | None = None,
        provider: DataProvider,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Return (valid_pcs, valid_npcs) as (display_string, hid) tuples."""
        # Character filtering and display formatting are disabled globally.
        _ = player_id
        all_chars = list(provider.get_characters())  # type: ignore[arg-type]
        choices = [(record.hid, record.hid) for record in all_chars]
        return list(choices), list(choices)

    async def get_valid_characters_async(
        self,
        *,
        player_id: str | None = None,
        provider: Any,
    ) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        """Async-safe variant of get_valid_characters for async providers."""
        _ = player_id
        chars = await maybe_await(provider.get_characters())
        all_chars = list(chars)
        choices = [(record.hid, record.hid) for record in all_chars]
        return list(choices), list(choices)
