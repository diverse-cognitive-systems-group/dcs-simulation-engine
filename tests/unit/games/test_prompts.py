"""Unit tests for named prompt registries and strict rendering."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.prompts import (
    CHARACTER_UPDATER_PROMPTS,
    PLAYER_VALIDATOR_PROMPTS,
    SCENE_UPDATER_PROMPTS,
    SIMULATOR_VALIDATOR_PROMPTS,
    build_character_updater_prompt,
    build_player_validator_prompt,
    build_scene_setup_prompt,
)


@pytest.fixture
def character_pair() -> tuple[CharacterRecord, CharacterRecord]:
    pc = CharacterRecord(
        hid="PC",
        name="Player",
        short_description="Player short",
        data={
            "abilities": ["can move"],
            "long_description": "Player long",
            "scenarios": ["Room"],
        },
    )
    npc = CharacterRecord(
        hid="NPC",
        name="NPC",
        short_description="NPC short",
        data={
            "abilities": ["can observe"],
            "long_description": "NPC long",
            "scenarios": ["Room"],
        },
    )
    return pc, npc


@pytest.mark.unit
def test_prompt_registries_expose_named_options() -> None:
    assert "default" in SCENE_UPDATER_PROMPTS
    assert "default" in CHARACTER_UPDATER_PROMPTS
    assert "valid-action" in PLAYER_VALIDATOR_PROMPTS
    assert "invented-pc-action" in SIMULATOR_VALIDATOR_PROMPTS


@pytest.mark.unit
def test_build_scene_setup_prompt_raises_for_missing_required_string(character_pair) -> None:
    pc, npc = character_pair
    broken_pc = pc._replace(data={"abilities": ["can move"], "long_description": "", "scenarios": ["Room"]})
    with pytest.raises(ValueError, match="pc_long_description"):
        build_scene_setup_prompt(broken_pc, npc, "default")


@pytest.mark.unit
def test_build_player_validator_prompt_raises_for_unknown_name(character_pair) -> None:
    pc, npc = character_pair
    with pytest.raises(ValueError, match="Unknown prompt name"):
        build_player_validator_prompt(pc, npc, "not-a-real-validator", user_input="I wave")


@pytest.mark.unit
def test_build_character_updater_prompt_includes_named_variant_rules(character_pair) -> None:
    pc, npc = character_pair
    prompt = build_character_updater_prompt(pc, npc, "goal-aligned", user_input="I wave")
    assert "Goal Aligned Response" in prompt
