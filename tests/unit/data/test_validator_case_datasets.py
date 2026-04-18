"""Validation tests for split player/simulator validator case datasets."""

import json
from pathlib import Path
from typing import Any

import pytest
from dcs_simulation_engine.games.prompts import (
    DEFAULT_PLAYER_TURN_VALIDATORS,
    DEFAULT_SIMULATOR_TURN_VALIDATORS,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_CHARACTERS_PATH = REPO_ROOT / "database_seeds" / "dev" / "characters.json"
PLAYER_CASES_PATH = REPO_ROOT / "tests" / "data" / "player_validator_cases.json"
SIMULATOR_CASES_PATH = REPO_ROOT / "tests" / "data" / "simulator_validator_cases.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rule_name(template: str) -> str:
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith("RULE:"):
            return stripped.removeprefix("RULE:").strip().split()[0]
    raise AssertionError("Validator template is missing a RULE header.")


def _character_index(characters: list[dict]) -> dict[str, dict]:
    return {str(character["hid"]): character for character in characters if isinstance(character, dict) and character.get("hid")}


@pytest.mark.parametrize(
    ("dataset_path", "ensemble_name", "required_case_fields", "required_metadata_keys"),
    [
        (
            PLAYER_CASES_PATH,
            "DEFAULT_PLAYER_TURN_VALIDATORS",
            {
                "id",
                "description",
                "pc_hid",
                "npc_hid",
                "transcript",
                "player_action",
                "expected_ensemble_pass",
                "expected_failed_validators",
                "expected_passed_validators",
            },
            {"dataset_name", "dataset_version", "validator_ensemble", "purpose", "scope", "coverage", "character_selection"},
        ),
        (
            SIMULATOR_CASES_PATH,
            "DEFAULT_SIMULATOR_TURN_VALIDATORS",
            {
                "id",
                "description",
                "pc_hid",
                "npc_hid",
                "transcript",
                "game_objective",
                "simulator_response",
                "expected_ensemble_pass",
                "expected_failed_validators",
                "expected_passed_validators",
            },
            {"dataset_name", "dataset_version", "validator_ensemble", "purpose", "scope", "coverage", "character_selection"},
        ),
    ],
)
def test_validator_case_datasets_have_required_structure_and_coverage(
    dataset_path: Path,
    ensemble_name: str,
    required_case_fields: set[str],
    required_metadata_keys: set[str],
) -> None:
    """Ensure split validator datasets keep required schema, ensemble completeness, and coverage intent."""
    dataset = _load_json(dataset_path)
    seed_by_hid = _character_index(_load_json(SEED_CHARACTERS_PATH))

    metadata = dataset.get("metadata", {})
    assert required_metadata_keys <= set(metadata), f"{dataset_path.name} missing metadata keys"
    assert metadata.get("validator_ensemble") == ensemble_name
    assert isinstance(metadata.get("character_selection", {}).get("sampled_pc_hids"), list)
    assert metadata.get("scope", {}).get("out_of_scope"), "dataset should declare explicit non-goals"

    cases = dataset.get("cases", [])
    assert isinstance(cases, list) and cases, f"{dataset_path.name} should contain cases"

    expected_rules = {
        "DEFAULT_PLAYER_TURN_VALIDATORS": {_rule_name(template) for template in DEFAULT_PLAYER_TURN_VALIDATORS},
        "DEFAULT_SIMULATOR_TURN_VALIDATORS": {_rule_name(template) for template in DEFAULT_SIMULATOR_TURN_VALIDATORS},
    }[ensemble_name]

    adversarial_case_count = 0
    extraordinary_case_count = 0

    for case in cases:
        assert required_case_fields <= set(case), f"{dataset_path.name} case {case.get('id')} is missing required fields"
        assert isinstance(case["expected_ensemble_pass"], bool)
        assert isinstance(case["expected_failed_validators"], list)
        assert isinstance(case["expected_passed_validators"], list)

        referenced_rules = set(case["expected_failed_validators"]) | set(case["expected_passed_validators"])
        assert referenced_rules == expected_rules, f"{dataset_path.name} case {case['id']} does not account for full ensemble"

        assert case["pc_hid"] in seed_by_hid, f"Unknown pc_hid in {dataset_path.name}: {case['pc_hid']}"
        assert case["npc_hid"] in seed_by_hid, f"Unknown npc_hid in {dataset_path.name}: {case['npc_hid']}"
        assert seed_by_hid[case["pc_hid"]].get("pc_eligible", False), f"pc_hid {case['pc_hid']} must be pc_eligible"

        tags = set(case.get("tags", []))
        if "adversarial" in tags or "prompt_injection" in tags or "meta" in tags:
            adversarial_case_count += 1
        if "extraordinary" in tags or "extraordinary_pc" in tags:
            extraordinary_case_count += 1

    assert adversarial_case_count >= 2, f"{dataset_path.name} should include multiple adversarial/tricky cases"
    assert extraordinary_case_count >= 1, f"{dataset_path.name} should include extraordinary ability coverage"


def test_player_dataset_samples_multiple_pc_eligible_characters() -> None:
    """Player dataset should cover multiple distinct pc_eligible character profiles."""
    dataset = _load_json(PLAYER_CASES_PATH)
    sampled_hids = {case["pc_hid"] for case in dataset.get("cases", [])}
    assert len(sampled_hids) >= 4, "player validator cases should include multiple distinct pc_eligible characters"
