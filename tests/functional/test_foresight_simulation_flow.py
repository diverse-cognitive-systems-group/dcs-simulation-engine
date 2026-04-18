"""Functional tests for ForesightGame's custom flow and scoring."""

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
        game="foresight",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )


async def test_foresight_full_custom_flow(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Foresight should support prediction-style turns and score immediately on finish."""
    session = await _make_session(async_mongo_provider)

    enter_events = await session.step_async("")
    assert [event["type"] for event in enter_events] == ["info", "ai"]
    assert session.turns == 1

    turn_events = await session.step_async("I wave my hand and predict they will wave back.")
    assert [event["type"] for event in turn_events] == ["ai"]
    assert "predict" not in turn_events[0]["content"].lower()
    assert session.turns == 2

    finish_events = await session.step_async("/finish")

    assert [event["type"] for event in finish_events] == ["info", "info"]
    assert "Tier" in finish_events[0]["content"]
    assert "Game finished" in finish_events[1]["content"]
    assert session.game.score["score"] == 65
    assert session.exited


async def test_foresight_help_and_abilities_hide_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Foresight hides NPC details by default in help and abilities content."""
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
    assert not session.exited


async def test_foresight_scoring_falls_back_on_scorer_failure(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Foresight should emit fallback score content if scoring fails."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("I step closer and predict FW will retreat.")

    async def _broken_score(*, prompt: str, transcript: str) -> ScorerResult:
        raise RuntimeError("scorer offline")

    session.game._scorer.score = _broken_score  # type: ignore[method-assign]

    finish_events = await session.step_async("/finish")

    assert [event["type"] for event in finish_events] == ["info", "info"]
    assert "Final score could not be computed." in finish_events[0]["content"]
    assert session.game.score["score"] is None
    assert session.exited


async def test_foresight_save_compatibility(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Foresight sessions should still support explicit exit and save compatibility."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("I stay still and predict FW will move closer.")

    await session.exit_async("test complete")
    session.save()

    assert session.exited
    assert session.exit_reason == "test complete"
