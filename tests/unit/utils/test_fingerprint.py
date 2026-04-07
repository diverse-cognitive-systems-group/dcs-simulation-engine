"""Unit tests for utils/fingerprint.py."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import DEFAULT_MODEL
from dcs_simulation_engine.games.prompts import UPDATER_SYSTEM_TEMPLATE
from dcs_simulation_engine.utils.fingerprint import compute_character_evaluation_fingerprint


def _make_character(**overrides) -> CharacterRecord:
    defaults = dict(
        hid="TEST",
        name="Test Character",
        short_description="A test character.",
        data={"abilities": ["can walk"], "long_description": "A plain test character."},
    )
    defaults.update(overrides)
    return CharacterRecord(**defaults)


@pytest.mark.unit
def test_fingerprint_returns_64_char_hex():
    """SHA-256 produces a 64-character lowercase hex digest."""
    fp = compute_character_evaluation_fingerprint(_make_character())
    assert isinstance(fp, str)
    assert len(fp) == 64
    assert fp == fp.lower()
    assert all(c in "0123456789abcdef" for c in fp)


@pytest.mark.unit
def test_fingerprint_is_deterministic():
    """Same inputs always produce the same fingerprint."""
    character = _make_character()
    assert compute_character_evaluation_fingerprint(character) == compute_character_evaluation_fingerprint(character)


@pytest.mark.unit
def test_fingerprint_uses_current_defaults():
    """Calling with defaults matches explicit current model and template."""
    character = _make_character()
    implicit = compute_character_evaluation_fingerprint(character)
    explicit = compute_character_evaluation_fingerprint(character, DEFAULT_MODEL, UPDATER_SYSTEM_TEMPLATE)
    assert implicit == explicit


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [
        ("hid", "OTHER"),
        ("name", "Different Name"),
        ("short_description", "A different short description."),
        ("data", {"abilities": ["can fly"], "long_description": "Completely different."}),
    ],
)
def test_fingerprint_changes_when_character_field_changes(field: str, value):
    """Changing any CharacterRecord field produces a different fingerprint."""
    base = _make_character()
    modified = _make_character(**{field: value})
    assert compute_character_evaluation_fingerprint(base) != compute_character_evaluation_fingerprint(modified)


@pytest.mark.unit
def test_fingerprint_changes_when_model_changes():
    """A different model string produces a different fingerprint."""
    character = _make_character()
    fp1 = compute_character_evaluation_fingerprint(character, model="openai/gpt-4o")
    fp2 = compute_character_evaluation_fingerprint(character, model="openai/gpt-5-mini")
    assert fp1 != fp2


@pytest.mark.unit
def test_fingerprint_changes_when_template_changes():
    """A different updater system prompt template produces a different fingerprint."""
    character = _make_character()
    fp1 = compute_character_evaluation_fingerprint(character, updater_system_prompt_template="Template A.")
    fp2 = compute_character_evaluation_fingerprint(character, updater_system_prompt_template="Template B.")
    assert fp1 != fp2
