"""Schema tests for simulator-turn validator cases."""

import json
from pathlib import Path
from typing import Any

import pytest
from dcs_simulation_engine.games.prompts import DEFAULT_SIMULATOR_TURN_VALIDATORS

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_CHARACTERS_PATH = REPO_ROOT / "database_seeds" / "dev" / "characters.json"
SIMULATOR_CASES_PATH = REPO_ROOT / "tests" / "data" / "simulator_turn_validator_cases.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _rule_name(template: str) -> str:
    for line in template.splitlines():
        stripped = line.strip()
        if stripped.startswith("RULE:"):
            return stripped.removeprefix("RULE:").strip().split(" — ", 1)[0]
    raise AssertionError("Validator template is missing a RULE header.")


def _character_index(characters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(character["hid"]): character for character in characters if isinstance(character, dict) and character.get("hid")}


def test_simulator_turn_validator_dataset_has_required_structure() -> None:
    """Simulator-turn validator dataset should match the current fixture schema."""
    dataset = _load_json(SIMULATOR_CASES_PATH)
    seed_by_hid = _character_index(_load_json(SEED_CHARACTERS_PATH))

    metadata = dataset.get("metadata", {})
    required_metadata_keys = {
        "dataset_name",
        "dataset_version",
        "owner",
        "validator_ensemble",
        "purpose",
        "scope",
        "coverage",
        "character_selection",
        "notes",
    }
    assert required_metadata_keys <= set(metadata), f"{SIMULATOR_CASES_PATH.name} missing metadata keys"
    assert metadata.get("dataset_name") == "simulator_turn_validator_cases"
    assert metadata.get("validator_ensemble") == "DEFAULT_SIMULATOR_TURN_VALIDATORS"
    assert isinstance(metadata.get("character_selection", {}).get("sampled_pc_hids"), list)
    assert metadata.get("scope", {}).get("out_of_scope"), "dataset should declare explicit non-goals"

    cases = dataset.get("cases", [])
    assert isinstance(cases, list) and cases, f"{SIMULATOR_CASES_PATH.name} should contain cases"

    required_case_fields = {
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
        "rationale",
    }
    expected_rules = {_rule_name(template) for template in DEFAULT_SIMULATOR_TURN_VALIDATORS}

    adversarial_case_count = 0
    extraordinary_case_count = 0

    for case in cases:
        assert required_case_fields <= set(case), f"{SIMULATOR_CASES_PATH.name} case {case.get('id')} is missing required fields"
        assert isinstance(case["expected_ensemble_pass"], bool)
        assert isinstance(case["expected_failed_validators"], list)
        assert isinstance(case["expected_passed_validators"], list)

        referenced_rules = set(case["expected_failed_validators"]) | set(case["expected_passed_validators"])
        assert referenced_rules == expected_rules, f"{SIMULATOR_CASES_PATH.name} case {case['id']} does not account for full ensemble"

        assert case["pc_hid"] in seed_by_hid, f"Unknown pc_hid in {SIMULATOR_CASES_PATH.name}: {case['pc_hid']}"
        assert case["npc_hid"] in seed_by_hid, f"Unknown npc_hid in {SIMULATOR_CASES_PATH.name}: {case['npc_hid']}"
        assert seed_by_hid[case["pc_hid"]].get("pc_eligible", False), f"pc_hid {case['pc_hid']} must be pc_eligible"

        tags = set(case.get("tags", []))
        if "adversarial" in tags or "prompt_injection" in tags or "meta" in tags:
            adversarial_case_count += 1
        if "extraordinary" in tags or "extraordinary_pc" in tags:
            extraordinary_case_count += 1

    assert adversarial_case_count >= 2, f"{SIMULATOR_CASES_PATH.name} should include multiple adversarial/tricky cases"
    assert extraordinary_case_count >= 1, f"{SIMULATOR_CASES_PATH.name} should include extraordinary ability coverage"
