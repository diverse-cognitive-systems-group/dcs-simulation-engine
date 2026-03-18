"""Tests for GameConfig."""

from types import SimpleNamespace

import pytest
from dcs_simulation_engine.core.game_config import GameConfig

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_load_minimal_game_config(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load a minimal valid GameConfig from YAML."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert cfg.name == "Minimal Test Game Config"


async def test_default_get_valid_characters_returns_all(
    game_config_minimal: SimpleNamespace,
    async_mongo_provider,
) -> None:
    """GameConfig returns all characters for both PC and NPC."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    pcs, npcs = await cfg.get_valid_characters_async(provider=async_mongo_provider)
    all_hids = {c.hid for c in await async_mongo_provider.get_characters()}
    assert {hid for _, hid in pcs} == all_hids
    assert {hid for _, hid in npcs} == all_hids
    assert {label for label, _ in pcs} == all_hids
    assert {label for label, _ in npcs} == all_hids
