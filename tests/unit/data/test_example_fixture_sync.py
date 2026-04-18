"""Drift checks for example fixture data versus current codebase definitions."""

import json
from pathlib import Path

import pytest
import yaml
from bson import json_util
from dcs_simulation_engine.games.prompts import (
    DEFAULT_PLAYER_TURN_VALIDATORS,
    DEFAULT_SIMULATOR_TURN_VALIDATORS,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_RESULTS_DIR = REPO_ROOT / "tests" / "data" / "example_results"
SEED_CHARACTERS_PATH = REPO_ROOT / "database_seeds" / "dev" / "characters.json"
DEFAULT_VALIDATOR_CASES_PATH = REPO_ROOT / "tests" / "data" / "default_validator_cases.json"
GAMES_DIR = REPO_ROOT / "games"


def _load_json(path: Path):
    """Load a standard JSON fixture."""
    return json.loads(path.read_text(encoding="utf-8"))


def _load_extended_json(path: Path):
    """Load MongoDB extended JSON fixture content."""
    return json_util.loads(path.read_text(encoding="utf-8"))


def _rule_name(template: str) -> str:
    """Extract the rule identifier from a validator template."""
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith("RULE:"):
            return stripped.removeprefix("RULE:").strip().split(" — ", 1)[0]
    raise AssertionError("Validator template is missing a RULE header.")


def _game_names_from_configs() -> set[str]:
    """Return the canonical game names from repo-level YAML configs."""
    names: set[str] = set()
    for path in sorted(GAMES_DIR.glob("*.y*ml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw_name = doc.get("name")
        if isinstance(raw_name, str) and raw_name.strip():
            names.add(raw_name.strip())
    return names


def _character_index(characters: list[dict]) -> dict[str, dict]:
    """Index character fixtures by HID."""
    return {str(character["hid"]): character for character in characters if isinstance(character, dict) and character.get("hid")}


@pytest.mark.xfail(
    strict=False, reason="Example results and validator fixtures currently drift from live game configs and dev seed characters."
)
def test_example_results_and_validator_cases_stay_in_sync_with_current_codebase() -> None:
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

    validator_cases = _load_json(DEFAULT_VALIDATOR_CASES_PATH)
    current_ensembles = {
        "DEFAULT_PLAYER_TURN_VALIDATORS": {_rule_name(template) for template in DEFAULT_PLAYER_TURN_VALIDATORS},
        "DEFAULT_SIMULATOR_TURN_VALIDATORS": {_rule_name(template) for template in DEFAULT_SIMULATOR_TURN_VALIDATORS},
    }

    for section_name in ("player_turn_cases", "simulator_turn_cases"):
        for case in validator_cases.get(section_name, []):
            case_id = case.get("id", "<missing-id>")
            ensemble_name = case.get("ensemble")
            if ensemble_name not in current_ensembles:
                failures.append(f"validator case {case_id!r} references unknown ensemble {ensemble_name!r}")
                continue

            expected_rule_names = current_ensembles[ensemble_name]
            referenced_rule_names = set(case.get("expected_failed_validators", [])) | set(case.get("expected_passed_validators", []))
            if referenced_rule_names - expected_rule_names:
                failures.append(
                    f"validator case {case_id!r} references validators not in {ensemble_name}: "
                    f"{sorted(referenced_rule_names - expected_rule_names)}"
                )

            if referenced_rule_names != expected_rule_names:
                failures.append(
                    f"validator case {case_id!r} does not account for the full {ensemble_name} set: "
                    f"referenced={sorted(referenced_rule_names)} expected={sorted(expected_rule_names)}"
                )

            for role_key in ("pc", "npc"):
                character_snapshot = case.get(role_key, {})
                hid = character_snapshot.get("hid")
                if hid not in seed_by_hid:
                    failures.append(f"validator case {case_id!r} references unknown {role_key} hid {hid!r}")
                    continue

                seed_character = seed_by_hid[hid]
                if character_snapshot.get("short_description") != seed_character.get("short_description"):
                    failures.append(f"validator case {case_id!r} has stale {role_key}.short_description for hid {hid!r}")

                snapshot_data = character_snapshot.get("data", {})
                for field in ("long_description", "abilities", "goals"):
                    if snapshot_data.get(field) != seed_character.get(field):
                        failures.append(f"validator case {case_id!r} has stale {role_key}.data.{field} for hid {hid!r}")

    if failures:
        pytest.fail("\n".join(failures))
