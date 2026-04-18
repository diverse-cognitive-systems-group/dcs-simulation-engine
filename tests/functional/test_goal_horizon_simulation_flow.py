"""Functional tests for GoalHorizonGame's finish flow and scoring."""

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
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )


async def test_goal_horizon_full_finish_flow(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Goal Horizon should collect prediction then confidence before scoring and exiting."""
    session = await _make_session(async_mongo_provider)

    enter_events = await session.step_async("")
    assert [event["type"] for event in enter_events] == ["info", "ai"]

    turn_events = await session.step_async("I place an object nearby and observe.")
    assert [event["type"] for event in turn_events] == ["ai"]
    assert session.turns == 2

    finish_prompt = await session.step_async("/finish")
    assert [event["type"] for event in finish_prompt] == ["info"]
    assert "FW" in finish_prompt[0]["content"]
    assert "largest types of goals" in finish_prompt[0]["content"]
    assert not session.exited

    confidence_prompt = await session.step_async("It seems limited to local sensing and cautious movement.")
    assert [event["type"] for event in confidence_prompt] == ["info"]
    assert "confident" in confidence_prompt[0]["content"].lower()
    assert session.game.capability_prediction == "It seems limited to local sensing and cautious movement."
    assert not session.exited

    completion_events = await session.step_async("Fairly confident based on repeated avoidance behavior.")
    assert [event["type"] for event in completion_events] == ["info", "info"]
    assert "Tier" in completion_events[0]["content"]
    assert "Game finished" in completion_events[1]["content"]
    assert session.game.capability_prediction_confidence == "Fairly confident based on repeated avoidance behavior."
    assert session.game._score["score"] == 65
    assert session.exited


async def test_goal_horizon_help_and_abilities_hide_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Goal Horizon hides NPC details by default in help and abilities."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")

    help_events = await session.step_async("/help")
    abilities_events = await session.step_async("/abilities")

    assert [event["type"] for event in help_events] == ["info"]
    assert "FW" in help_events[0]["content"]
    assert "*Details hidden.*" in help_events[0]["content"]

    assert [event["type"] for event in abilities_events] == ["info"]
    assert "NA" in abilities_events[0]["content"]
    assert "FW" in abilities_events[0]["content"]
    assert "*Details hidden.*" in abilities_events[0]["content"]


async def test_goal_horizon_finish_flow_routes_follow_up_input(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """While in finish flow, user input should be treated as form answers rather than simulator turns."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("/finish")

    events = await session.step_async("Its goals seem bounded to immediate environmental regulation.")

    assert [event["type"] for event in events] == ["info"]
    assert session.turns == 1
    assert session.game.capability_prediction == "Its goals seem bounded to immediate environmental regulation."
    assert not session.exited


async def test_goal_horizon_scoring_falls_back_on_scorer_failure(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Goal Horizon should emit fallback score content if scoring fails."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("I observe its response to a new obstacle.")
    await session.step_async("/finish")
    await session.step_async("It can likely pursue only local bodily stability and simple avoidance.")

    async def _broken_score(*, prompt: str, transcript: str) -> ScorerResult:
        raise RuntimeError("scorer offline")

    session.game._scorer.score = _broken_score  # type: ignore[method-assign]

    completion_events = await session.step_async("Moderately confident.")

    assert [event["type"] for event in completion_events] == ["info", "info"]
    assert "Final score couldn't be computed." in completion_events[0]["content"]
    assert session.game._score["score"] is None
    assert session.exited
