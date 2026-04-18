"""Unit tests for prompt templates and rendering helpers."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.prompts import (
    DEFAULT_PLAYER_TURN_VALIDATORS,
    DEFAULT_SIMULATOR_TURN_VALIDATORS,
    OPENER,
    OPENER_WITH_SHARED_GOAL,
    UPDATER,
    VALID_GAME_ALIGNMENT,
    VALID_NPC_ACTION,
    VALID_PC_ABILITY,
    VALID_PC_ACTION,
    build_opener_prompt,
    build_player_validator_prompt,
    build_simulator_validator_prompt,
    build_updater_prompt,
)


@pytest.fixture
def character_pair() -> tuple[CharacterRecord, CharacterRecord]:
    """Return a PC/NPC pair with enough context to render prompt templates."""
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
def test_prompt_templates_and_default_validator_sets_exist() -> None:
    """Default prompt constants and validator lists should stay wired together."""
    assert "Describe ONLY the initial, observable environment." in OPENER
    assert "generate a shared goal" in OPENER_WITH_SHARED_GOAL
    assert "Produce the next immediate simulator update." in UPDATER
    assert VALID_PC_ACTION in DEFAULT_PLAYER_TURN_VALIDATORS
    assert VALID_NPC_ACTION in DEFAULT_SIMULATOR_TURN_VALIDATORS


@pytest.mark.unit
def test_build_opener_prompt_renders_character_context(character_pair) -> None:
    """Opener prompt should include both character roles and long descriptions."""
    pc, npc = character_pair
    prompt = build_opener_prompt(pc, npc)
    assert "PC (Player Character)" in prompt
    assert "NPC (Simulated Character)" in prompt
    assert "Player long" in prompt
    assert "NPC long" in prompt


@pytest.mark.unit
def test_build_updater_prompt_renders_runtime_fields(character_pair) -> None:
    """Updater prompt should interpolate the live objective, transcript, and action."""
    pc, npc = character_pair
    prompt = build_updater_prompt(
        pc,
        npc,
        game_objective="Keep the room safe.",
        transcript="Opening scene: The room is quiet.",
        player_action="I wave",
    )
    assert "Keep the room safe." in prompt
    assert "Opening scene: The room is quiet." in prompt
    assert "I wave" in prompt


@pytest.mark.unit
def test_build_player_validator_prompt_renders_validator_template(character_pair) -> None:
    """Player validator prompt should include the selected rule and current turn context."""
    pc, npc = character_pair
    prompt = build_player_validator_prompt(
        pc,
        npc,
        player_action="I wave",
        transcript="Opening scene: A hallway.",
        validator_template=VALID_PC_ABILITY,
    )
    assert "RULE: VALID-PC-ABILITY" in prompt
    assert "I wave" in prompt
    assert "Opening scene: A hallway." in prompt


@pytest.mark.unit
def test_build_simulator_validator_prompt_renders_simulator_response_context(character_pair) -> None:
    """Simulator validator prompt should include the rule, response, and objective."""
    pc, npc = character_pair
    prompt = build_simulator_validator_prompt(
        pc,
        npc,
        simulator_response="NPC steps back.",
        transcript="Player (PC): I wave",
        game_objective="Learn what NPC wants.",
        validator_template=VALID_GAME_ALIGNMENT,
    )
    assert "RULE: VALID-GAME-ALIGNMENT" in prompt
    assert "NPC steps back." in prompt
    assert "Learn what NPC wants." in prompt
