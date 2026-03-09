"""Tests for GameConfig."""

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict

import pytest
from dcs_simulation_engine.core.game_config import (
    AccessSettings,
    CharacterSelection,
    CharacterSelector,
    GameConfig,
)
from mongomock import ObjectId


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
    """Default GameConfig returns all characters for both PC and NPC."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    pcs, npcs = cfg.get_valid_characters(provider=mongo_provider)
    pc_hids = [hid for _, hid in pcs]
    npc_hids = [hid for _, hid in npcs]
    assert len(pc_hids) > 0
    assert set(pc_hids) == set(npc_hids)


@pytest.mark.unit
def test_get_valid_characters_with_declarative_selection(
    game_config_minimal: SimpleNamespace,
    mongo_provider,
) -> None:
    """Declarative selection policies can constrain PC/NPC pools."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    selected_cfg = cfg.model_copy(
        update={
            "character_selection": CharacterSelection(
                pc=CharacterSelector(include_hids=["human-normative"]),
                npc=CharacterSelector(exclude_hids=["human-normative"]),
            )
        }
    )
    pcs, npcs = selected_cfg.get_valid_characters(provider=mongo_provider)
    pc_hids = [hid for _, hid in pcs]
    npc_hids = [hid for _, hid in npcs]

    assert pc_hids == ["human-normative"]
    assert "human-normative" not in npc_hids
    assert len(npc_hids) > 0


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


@pytest.mark.unit
def test_seen_npc_filter_uses_normalized_npc_hid_from_provider(
    game_config_minimal: SimpleNamespace,
    mongo_provider,
) -> None:
    """Declarative seen-NPC filter relies on DAL-provided normalized npc_hid."""
    db = mongo_provider.get_db()

    player_data: Dict[str, Any] = {"email": "alice@example.com"}
    player_record, _ = mongo_provider.create_player(player_data=player_data, issue_access_key=True)
    player_id = player_record.id

    db.runs.insert_one(
        {
            "player_id": ObjectId(player_id),
            "game_config": {"name": "Test Game"},
            "context": {"npc": {"hid": "flatworm"}},
            "created_at": datetime.now(timezone.utc),
        }
    )

    cfg = GameConfig.from_yaml(game_config_minimal.path)
    seen_filtered_cfg = cfg.model_copy(
        update={
            "character_selection": CharacterSelection(
                pc=CharacterSelector(),
                npc=CharacterSelector(exclude_seen_for_game="Test Game"),
            )
        }
    )

    _, npcs = seen_filtered_cfg.get_valid_characters(player_id=player_id, provider=mongo_provider)
    npc_hids = [hid for _, hid in npcs]
    assert "flatworm" not in npc_hids
