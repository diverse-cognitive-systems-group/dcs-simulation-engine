"""Drift checks for example results data versus current codebase definitions."""

import json
from pathlib import Path

import pytest
from bson import json_util
from dcs_simulation_engine.core.session_manager import SessionManager

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_RESULTS_DIR = REPO_ROOT / "tests" / "data" / "example_results"
SEED_CHARACTERS_PATH = REPO_ROOT / "database_seeds" / "dev" / "characters.json"


def _load_json(path: Path):
    """Load a standard JSON fixture."""
    return json.loads(path.read_text(encoding="utf-8"))


def _load_extended_json(path: Path):
    """Load MongoDB extended JSON fixture content."""
    return json_util.loads(path.read_text(encoding="utf-8"))


def _game_names_from_configs() -> set[str]:
    """Return the canonical game names from built-in game classes."""
    return {game_cls.GAME_NAME for game_cls in SessionManager._builtin_game_classes().values()}


def _character_index(characters: list[dict]) -> dict[str, dict]:
    """Index character fixtures by HID."""
    return {str(character["hid"]): character for character in characters if isinstance(character, dict) and character.get("hid")}


def test_example_results_stay_in_sync_with_current_codebase() -> None:
    """Fixture snapshots should stay aligned with current game definitions and dev seed characters."""
    failures: list[str] = []

    seed_characters = _load_json(SEED_CHARACTERS_PATH)
    seed_by_hid = _character_index(seed_characters)
    current_game_names = _game_names_from_configs()

    example_characters = _load_extended_json(EXAMPLE_RESULTS_DIR / "characters.json")
    example_characters_by_hid = _character_index(example_characters)
    example_sessions = _load_extended_json(EXAMPLE_RESULTS_DIR / "sessions.json")

    example_game_names = {
        str(session.get("game_name")).strip()
        for session in example_sessions
        if isinstance(session, dict) and isinstance(session.get("game_name"), str)
    }
    if example_game_names != current_game_names:
        failures.append(
            "example_results sessions use different game names than current configs: "
            f"example={sorted(example_game_names)} current={sorted(current_game_names)}"
        )

    if set(example_characters_by_hid) != set(seed_by_hid):
        missing_from_example = sorted(set(seed_by_hid) - set(example_characters_by_hid))
        extra_in_example = sorted(set(example_characters_by_hid) - set(seed_by_hid))
        failures.append(
            "example_results characters differ from database_seeds/dev/characters.json: "
            f"missing_from_example={missing_from_example} extra_in_example={extra_in_example}"
        )

    overlapping_hids = sorted(set(example_characters_by_hid) & set(seed_by_hid))
    drift_fields = ("short_description", "long_description", "abilities", "goals", "pc_eligible", "common_labels", "is_human")
    for hid in overlapping_hids:
        seed_character = seed_by_hid[hid]
        example_character = example_characters_by_hid[hid]
        mismatched_fields = [field for field in drift_fields if example_character.get(field) != seed_character.get(field)]
        if mismatched_fields:
            failures.append(f"example_results character {hid!r} drifted on fields {mismatched_fields}")

    if failures:
        pytest.fail("\n".join(failures))
