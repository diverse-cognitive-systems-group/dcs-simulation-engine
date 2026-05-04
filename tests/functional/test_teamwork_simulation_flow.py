"""Functional tests for TeamworkGame's shared-goal flow and scoring."""

from typing import Any

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.games.ai_client import ScorerResult

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_registered_player(_isolate_db_state, async_mongo_provider):
    """Seed a registered player for session persistence."""
    db = async_mongo_provider.get_db()
    db[MongoColumns.PLAYERS].insert_one(
        {
            "_id": TEST_PLAYER_ID,
            "full_name": "Test Player",
            "email": "test@example.com",
        }
    )
    yield


async def _make_session(async_mongo_provider: Any) -> SessionManager:
    return await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )


async def test_teamwork_full_shared_goal_flow(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Teamwork should capture opening metadata, then score after the reflection answer."""
    session = await _make_session(async_mongo_provider)

    enter_events = await session.step_async("")
    assert [event["type"] for event in enter_events] == ["info", "ai"]
    assert session.game.shared_goal == "to secure the exposed control box before the room fully floods"
    assert session.turns == 1

    help_events = await session.step_async("/help")
    assert [event["type"] for event in help_events] == ["info"]
    assert "to secure the exposed control box before the room fully floods" in help_events[0]["content"]

    turn_events = await session.step_async("I move toward the loose panel.")
    assert [event["type"] for event in turn_events] == ["ai"]
    assert session.turns == 2

    finish_prompt = await session.step_async("/finish")
    assert [event["type"] for event in finish_prompt] == ["info"]
    assert "challenging" in finish_prompt[0]["content"].lower()
    assert not session.exited

    completion_events = await session.step_async("Coordinating timing with FW was the hardest part.")
    assert [event["type"] for event in completion_events] == ["info", "info"]
    assert "Tier" in completion_events[0]["content"]
    assert "Game finished" in completion_events[1]["content"]
    assert session.game.challenges == "Coordinating timing with FW was the hardest part."
    assert session.game.score["score"] == 65
    assert session.exited


async def test_teamwork_help_and_abilities_show_npc_details_by_default(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Teamwork shows NPC details by default rather than hiding them."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")

    help_events = await session.step_async("/help")
    abilities_events = await session.step_async("/abilities")

    assert [event["type"] for event in help_events] == ["info"]
    assert "FW" in help_events[0]["content"]
    assert "*Details hidden.*" not in help_events[0]["content"]

    assert [event["type"] for event in abilities_events] == ["info"]
    assert "NA" in abilities_events[0]["content"]
    assert "FW" in abilities_events[0]["content"]
    assert "*Details hidden.*" not in abilities_events[0]["content"]


async def test_teamwork_finish_flow_routes_follow_up_input(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """While in finish flow, user input should be treated as the reflection answer rather than a simulator turn."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("/finish")

    async def _ok_score(*, prompt: str, transcript: str) -> ScorerResult:
        return ScorerResult(evaluation={"tier": 2, "score": 65, "reasoning": "Partial match."}, raw_json="{}")

    session.game._scorer.score = _ok_score  # type: ignore[method-assign]
    events = await session.step_async("Communication was challenging but manageable.")

    assert [event["type"] for event in events] == ["info", "info"]
    assert session.turns == 1
    assert session.game.challenges == "Communication was challenging but manageable."
    assert session.exited


async def test_teamwork_scoring_falls_back_on_scorer_failure(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Teamwork should emit fallback score content if scoring fails."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("I point toward the control box.")
    await session.step_async("/finish")

    async def _broken_score(*, prompt: str, transcript: str) -> ScorerResult:
        raise RuntimeError("scorer offline")

    session.game._scorer.score = _broken_score  # type: ignore[method-assign]

    completion_events = await session.step_async("Synchronizing movement with FW was difficult.")

    assert [event["type"] for event in completion_events] == ["info", "info"]
    assert "Final score couldn't be computed." in completion_events[0]["content"]
    assert session.game.score["score"] is None
    assert session.exited
