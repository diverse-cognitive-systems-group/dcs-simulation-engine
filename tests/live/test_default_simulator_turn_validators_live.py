"""Live OpenRouter smoke tests for default simulator-turn validator cases."""

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import SimulatorClient
from dcs_simulation_engine.games.prompts import DEFAULT_SIMULATOR_TURN_VALIDATORS

if not os.getenv("OPENROUTER_API_KEY", "").strip():
    pytest.skip(
        "live OpenRouter credentials not configured; skipping simulator-turn live validator tests",
        allow_module_level=True,
    )

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CHARACTERS_PATH = REPO_ROOT / "database_seeds" / "dev" / "characters.json"
SIMULATOR_CASES_PATH = REPO_ROOT / "tests" / "data" / "validators" / "default_simulator_turn_validator_cases.json"
PLAYER_TURN_RE = re.compile(r"^(?P<context>.*)Player \((?P<pc_hid>[^)]+)\): (?P<action>.*)$", re.DOTALL)


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


def _to_character_record(character: dict[str, Any]) -> CharacterRecord:
    return CharacterRecord(
        hid=str(character["hid"]),
        name=str(character.get("name") or character["hid"]),
        short_description=str(character.get("short_description") or character["hid"]),
        data=dict(character),
    )


def _failure_rule_name(validator_name: str) -> str:
    return validator_name.split(" — ", 1)[0].strip()


def _simulator_cases() -> list[dict[str, Any]]:
    dataset = _load_json(SIMULATOR_CASES_PATH)
    metadata = dataset.get("metadata", {})
    assert metadata.get("model_key") == "DEFAULT_SIMULATOR_TURN_VALIDATORS"
    cases = dataset.get("cases", [])
    assert isinstance(cases, list)
    return cases


def _split_transcript(transcript: str) -> tuple[str, str, str]:
    match = PLAYER_TURN_RE.match(transcript)
    assert match is not None, "simulator validator transcript must include a Player (...) action"
    context = match.group("context").rstrip()
    pc_hid = match.group("pc_hid").strip()
    action = match.group("action").strip()
    return context, pc_hid, action


@pytest.mark.anyio
@pytest.mark.parametrize("case", _simulator_cases(), ids=lambda case: str(case["id"]))
async def test_default_simulator_turn_validators_live(case: dict[str, Any]) -> None:
    """Run the real default simulator-turn validator ensemble against each fixture case."""
    seed_by_hid = _character_index(_load_json(SEED_CHARACTERS_PATH))
    pc = _to_character_record(seed_by_hid[case["pc_hid"]])
    npc = _to_character_record(seed_by_hid[case["npc_hid"]])
    transcript_context, transcript_pc_hid, player_action = _split_transcript(str(case["transcript"]))

    assert transcript_pc_hid == str(case["pc_hid"])

    client = SimulatorClient(pc=pc, npc=npc, player_turn_validators=[])
    client._transcript_events = [transcript_context]
    client._opening_metadata = {"shared_goal": str(case["game_objective"])}

    failures = await client._validate_simulator_response(
        user_input=player_action,
        simulator_response=str(case["simulator_response"]),
    )

    actual_failed = {_failure_rule_name(failure.validator_name) for failure in failures}
    expected_failed = set(case["expected_failed_validators"])
    expected_passed = set(case["expected_passed_validators"])
    actual_passed = {_rule_name(template) for template in DEFAULT_SIMULATOR_TURN_VALIDATORS} - actual_failed

    assert (not actual_failed) == case["expected_ensemble_pass"]
    assert actual_failed == expected_failed
    assert actual_passed == expected_passed
