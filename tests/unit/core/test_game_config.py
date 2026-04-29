"""Tests for GameConfig."""

from types import SimpleNamespace

import pytest
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.games.goal_horizon import GoalHorizonGame

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_load_minimal_game_config(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load a minimal valid GameConfig from YAML."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert cfg.name == "Minimal Test Game Config"


class _StaticCharacterProvider:
    def __init__(self, characters) -> None:
        self._characters = list(characters)

    def get_characters(self):
        return list(self._characters)


async def test_default_get_valid_characters_uses_game_class_filters(
    game_config_minimal: SimpleNamespace,
    async_mongo_provider,
) -> None:
    """GameConfig should use the configured game class filters."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    pcs, npcs = await cfg.get_valid_characters_async(provider=async_mongo_provider)
    all_hids = {c.hid for c in await async_mongo_provider.get_characters()}
    pc_eligible_hids = {c.hid for c in await async_mongo_provider.get_characters() if c.data.get("pc_eligible", False)}
    assert {hid for _, hid in pcs} == pc_eligible_hids
    assert {hid for _, hid in npcs} == all_hids
    assert {label for label, _ in pcs} == pc_eligible_hids
    assert {label for label, _ in npcs} == all_hids


async def test_goal_horizon_get_valid_characters_uses_default_player_filter(async_mongo_provider) -> None:
    """Goal Horizon choices should follow GoalHorizonGame.DEFAULT_PCS_FILTER."""
    cfg = GameConfig.from_game_class(GoalHorizonGame)
    characters = await async_mongo_provider.get_characters()
    expected = {
        c.hid
        for c in GoalHorizonGame.DEFAULT_PCS_FILTER.get_characters(
            provider=_StaticCharacterProvider(characters)
        )
    }

    sync_pcs, _sync_npcs = cfg.get_valid_characters(provider=_StaticCharacterProvider(characters))
    async_pcs, _async_npcs = await cfg.get_valid_characters_async(provider=async_mongo_provider)

    assert {hid for _, hid in sync_pcs} == expected
    assert {hid for _, hid in async_pcs} == expected
