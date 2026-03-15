"""Tests for GameConfig."""

from types import SimpleNamespace

import pytest
from dcs_simulation_engine.core.game_config import (
    AccessSettings,
    GameConfig,
)

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_load_minimal_game_config(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load a minimal valid GameConfig from YAML."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert cfg.name == "Minimal Test Game Config"


async def test_default_is_player_allowed(
    game_config_minimal: SimpleNamespace,
    async_mongo_provider,
) -> None:
    """Default GameConfig allows any player including None."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert await cfg.is_player_allowed_async(player_id=None, provider=async_mongo_provider) is True
    assert await cfg.is_player_allowed_async(player_id="any-id", provider=async_mongo_provider) is True


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


async def test_consent_required_gate_uses_player_signature(
    game_config_minimal: SimpleNamespace,
    async_mongo_provider,
) -> None:
    """require_consent_signature gate allows only players with truthy signature."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    gated_cfg = cfg.model_copy(update={"access_settings": AccessSettings(require_consent_signature=True)})

    assert await gated_cfg.is_player_allowed_async(player_id=None, provider=async_mongo_provider) is False

    player_no_sig, _ = await async_mongo_provider.create_player(player_data={"email": "nosig@example.com"})
    assert await gated_cfg.is_player_allowed_async(player_id=player_no_sig.id, provider=async_mongo_provider) is False

    player_with_sig, _ = await async_mongo_provider.create_player(
        player_data={"email": "sig@example.com", "consent_signature": {"answer": ["signed"]}}
    )
    assert await gated_cfg.is_player_allowed_async(player_id=player_with_sig.id, provider=async_mongo_provider) is True
