"""Tests for GameConfig."""

from types import SimpleNamespace

import pytest
from dcs_simulation_engine.core.game_config import (
    AccessSettings,
    GameConfig,
)


@pytest.mark.unit
def test_load_minimal_game_config(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load a minimal valid GameConfig from YAML."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert cfg.name == "Minimal Test Game Config"


@pytest.mark.unit
def test_default_is_player_allowed(
    game_config_minimal: SimpleNamespace,
    mongo_provider,
) -> None:
    """Default GameConfig allows any player including None."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert cfg.is_player_allowed(player_id=None, provider=mongo_provider) is True
    assert cfg.is_player_allowed(player_id="any-id", provider=mongo_provider) is True


@pytest.mark.unit
def test_default_get_valid_characters_returns_all(
    game_config_minimal: SimpleNamespace,
    mongo_provider,
) -> None:
    """GameConfig returns all characters for both PC and NPC."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    pcs, npcs = cfg.get_valid_characters(provider=mongo_provider)
    all_hids = {c.hid for c in mongo_provider.get_characters()}
    assert {hid for _, hid in pcs} == all_hids
    assert {hid for _, hid in npcs} == all_hids
    assert {label for label, _ in pcs} == all_hids
    assert {label for label, _ in npcs} == all_hids


@pytest.mark.unit
def test_consent_required_gate_uses_player_signature(
    game_config_minimal: SimpleNamespace,
    mongo_provider,
) -> None:
    """require_consent_signature gate allows only players with truthy signature."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    gated_cfg = cfg.model_copy(update={"access_settings": AccessSettings(require_consent_signature=True)})

    assert gated_cfg.is_player_allowed(player_id=None, provider=mongo_provider) is False

    player_no_sig, _ = mongo_provider.create_player(player_data={"email": "nosig@example.com"})
    assert gated_cfg.is_player_allowed(player_id=player_no_sig.id, provider=mongo_provider) is False

    player_with_sig, _ = mongo_provider.create_player(
        player_data={"email": "sig@example.com", "consent_signature": {"answer": ["signed"]}}
    )
    assert gated_cfg.is_player_allowed(player_id=player_with_sig.id, provider=mongo_provider) is True
