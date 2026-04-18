"""Functional tests for InferIntentGame's finish flow and scoring."""

from typing import Any

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.games.ai_client import ScorerResult

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a consenting player for gated game access."""
    db = async_mongo_provider.get_db()
    db[MongoColumns.PLAYERS].insert_one(
        {
            "_id": TEST_PLAYER_ID,
            "consent_signature": {"answer": ["I confirm that the information I have provided is true..."]},
            "full_name": "Test Player",
            "email": "test@example.com",
        }
    )
    yield


async def _make_session(async_mongo_provider: Any) -> SessionManager:
    return await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )


async def test_infer_intent_full_finish_flow(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Infer Intent should collect inference then confidence before scoring and exiting."""
    session = await _make_session(async_mongo_provider)

    enter_events = await session.step_async("")
    assert [event["type"] for event in enter_events] == ["info", "ai"]

    turn_events = await session.step_async("I observe the creature carefully.")
    assert [event["type"] for event in turn_events] == ["ai"]
    assert session.turns == 2

    finish_prompt = await session.step_async("/finish")
    assert [event["type"] for event in finish_prompt] == ["info"]
    assert "goal or intention" in finish_prompt[0]["content"].lower()
    assert not session.exited

    inference_prompt = await session.step_async("The creature is trying to find safety.")
    assert [event["type"] for event in inference_prompt] == ["info"]
    assert "confident" in inference_prompt[0]["content"].lower()
    assert session.game.goal_inference == "The creature is trying to find safety."
    assert not session.exited

    completion_events = await session.step_async("Very confident because it repeatedly avoids bright areas.")
    assert [event["type"] for event in completion_events] == ["info", "info"]
    assert "Tier" in completion_events[0]["content"]
    assert "Game finished" in completion_events[1]["content"]
    assert session.game.goal_inference_confidence == "Very confident because it repeatedly avoids bright areas."
    assert session.game.score["score"] == 65
    assert session.exited


async def test_infer_intent_help_and_abilities_hide_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Infer Intent hides NPC details by default in help and abilities."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")

    help_events = await session.step_async("/help")
    abilities_events = await session.step_async("/abilities")

    assert [event["type"] for event in help_events] == ["info"]
    assert "FW" in help_events[0]["content"]
    assert "*NPC details are hidden.*" in help_events[0]["content"]

    assert [event["type"] for event in abilities_events] == ["info"]
    assert "NA" in abilities_events[0]["content"]
    assert "FW" in abilities_events[0]["content"]
    assert "*NPC details are hidden.*" in abilities_events[0]["content"]


async def test_infer_intent_finish_flow_routes_follow_up_input(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """While in finish flow, user input should be treated as form answers rather than simulator turns."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("/finish")

    events = await session.step_async("It wants to get away from the light.")

    assert [event["type"] for event in events] == ["info"]
    assert session.turns == 1
    assert session.game.goal_inference == "It wants to get away from the light."
    assert not session.exited


async def test_infer_intent_scoring_falls_back_on_scorer_failure(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Infer Intent should emit fallback score content if scoring fails."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("I wait and observe.")
    await session.step_async("/finish")
    await session.step_async("It wants to preserve its stability.")

    async def _broken_score(*, prompt: str, transcript: str) -> ScorerResult:
        raise RuntimeError("scorer offline")

    session.game._scorer.score = _broken_score  # type: ignore[method-assign]

    completion_events = await session.step_async("Moderately confident.")

    assert [event["type"] for event in completion_events] == ["info", "info"]
    assert "Final score couldn't be computed." in completion_events[0]["content"]
    assert session.game.score["score"] is None
    assert session.exited
