"""Live OpenRouter tests for goal-inference scorer cases."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import ScorerClient
from dcs_simulation_engine.games.prompts import SCORER_GOAL_INFERENCE, build_scorer_prompt

if not os.getenv("OPENROUTER_API_KEY", "").strip():
    pytest.skip(
        "live OpenRouter credentials not configured; skipping goal-inference scorer live tests",
        allow_module_level=True,
    )

pytestmark = pytest.mark.live

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CHARACTERS_PATH = REPO_ROOT / "database_seeds" / "dev" / "characters.json"
CASES_PATH = REPO_ROOT / "tests" / "data" / "scorers" / "scorer_goal_inference_cases.json"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _character_index(characters: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(character["hid"]): character for character in characters if isinstance(character, dict) and character.get("hid")}


def _to_character_record(character: dict[str, Any]) -> CharacterRecord:
    return CharacterRecord(
        hid=str(character["hid"]),
        name=str(character.get("name") or character["hid"]),
        short_description=str(character.get("short_description") or character["hid"]),
        data=dict(character),
    )


def _cases() -> list[dict[str, Any]]:
    dataset = _load_json(CASES_PATH)
    metadata = dataset.get("metadata", {})
    assert metadata.get("model_key") == "SCORER_GOAL_INFERENCE"
    cases = dataset.get("cases", [])
    assert isinstance(cases, list)
    return cases


def _assert_expected_value(actual: int, expected: int | str, *, result: Any) -> None:
    message = f"expected {expected!r}, got {actual!r}; LLM returned: {result.evaluation!r}; raw JSON: {result.raw_json}"
    if isinstance(expected, int):
        assert actual == expected, message
        return

    for raw_constraint in expected.split(","):
        constraint = raw_constraint.strip()
        if constraint.startswith(">="):
            assert actual >= int(constraint.removeprefix(">=")), message
        elif constraint.startswith("<="):
            assert actual <= int(constraint.removeprefix("<=")), message
        elif constraint.startswith(">"):
            assert actual > int(constraint.removeprefix(">")), message
        elif constraint.startswith("<"):
            assert actual < int(constraint.removeprefix("<")), message
        else:
            assert actual == int(constraint), message


@pytest.mark.anyio
@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["id"]))
async def test_scorer_goal_inference_live(case: dict[str, Any]) -> None:
    """Run the real goal-inference scorer against each fixture case."""
    seed_by_hid = _character_index(_load_json(SEED_CHARACTERS_PATH))
    npc = _to_character_record(seed_by_hid[case["npc_hid"]])
    transcript = str(case["transcript"])
    prompt = build_scorer_prompt(
        scoring_template=SCORER_GOAL_INFERENCE,
        npc=npc,
        transcript=transcript,
        guess=str(case["guess"]),
    )

    result = await ScorerClient().score(prompt=prompt, transcript=transcript)

    _assert_expected_value(result.evaluation["tier"], case["expected_tier"], result=result)
    _assert_expected_value(result.evaluation["score"], case["expected_score"], result=result)
