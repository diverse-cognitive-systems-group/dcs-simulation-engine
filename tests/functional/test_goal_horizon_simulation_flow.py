"""Functional tests for goal-horizon game simulation flow with mocked LLMs.

This test suite validates the goal-horizon game's mechanics:
1. Consent-required player access
2. Standard enter/turn flow
3. /predict-capabilities ends the game with a final answer
4. Session persistence

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import (
    SessionManager,
)
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a player with consent signature for goal-horizon game access."""
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


async def test_goal_horizon_initialization(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test goal-horizon game initializes correctly with SessionManager."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


async def test_goal_horizon_enter_step(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test enter step produces events and session state is valid."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    events = await session.step_async("")

    assert len(events) > 0, "ENTER step should produce events"
    assert session._events is not None, "Session events should exist after step"


async def test_goal_horizon_predict_capabilities_completion(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /predict-capabilities collects capability answer then confidence before exiting."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    command_events = await session.step_async("/predict-capabilities")
    assert any(e["type"] == "info" for e in command_events), "Expected info prompt from /predict-capabilities"
    assert not session.exited

    answer_events = await session.step_async("It seems limited to local sensing and cautious movement.")
    assert any(e["type"] == "info" for e in answer_events), "Expected confidence question"
    assert not session.exited, "Session should not exit until confidence is submitted"
    assert session.game.capability_prediction == "It seems limited to local sensing and cautious movement."

    confidence_events = await session.step_async("Fairly confident based on its repeated avoidance behavior.")
    assert any(e["type"] == "info" for e in confidence_events), "Expected completion confirmation"
    assert session.exited, "Session should exit after confidence is submitted"
    assert session.game.capability_prediction_confidence == "Fairly confident based on its repeated avoidance behavior."


async def test_goal_horizon_exit_and_save(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test goal-horizon game sessions can be exited and saved."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")

    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"
    assert session.exit_reason == "test complete"

    session.save()


async def test_help_hides_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help shows NPC hid but does not reveal NPC description."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")

    help_events = await session.step_async("/help")

    info_events = [e for e in help_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /help"

    content = " ".join(e["content"] for e in info_events)
    assert "FW" in content, "NPC hid should appear in /help"
    assert "details hidden" in content.lower(), "Expected NPC details to be hidden in /help — '(*details hidden*)' not found"


async def test_abilities_hides_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /abilities shows PC abilities but hides all NPC details."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")

    abilities_events = await session.step_async("/abilities")

    info_events = [e for e in abilities_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /abilities"

    content = " ".join(e["content"] for e in info_events)
    assert "NA" in content, "PC hid should appear in /abilities"
    assert "FW" in content, "NPC hid should appear in /abilities"
    assert "NPC details are hidden" in content, "Expected '*NPC details are hidden.*' in /abilities NPC section"


async def test_capability_prediction_question_contains_npc_hid(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test the /predict-capabilities prompt renders the NPC hid correctly.

    The GoalHorizon.CAPABILITY_PREDICTION_QUESTION template includes {npc_hid}.
    This confirms that variable is rendered — 'FW' appears in the prompt,
    not a raw '{npc_hid}' bracket.
    """
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")

    command_events = await session.step_async("/predict-capabilities")

    info_events = [e for e in command_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info prompt from /predict-capabilities"

    content = " ".join(e["content"] for e in info_events)
    assert "FW" in content, f"NPC hid 'FW' should appear in /predict-capabilities question (template rendering check). Got: {content}"
    assert "{" not in content, f"Unrendered template bracket in /predict-capabilities question: {content}"


async def test_default_post_play_form_present(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Goal Horizon post-play: /predict-capabilities → answer → confidence → FINISH_CONTENT."""
    session = await SessionManager.create_async(
        game="Goal Horizon",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")

    predict_events = await session.step_async("/predict-capabilities")
    assert any(e["type"] == "info" for e in predict_events), "Expected capability prediction question"
    assert not session.exited

    answer_events = await session.step_async("Limited to local sensing and cautious movement.")
    assert any(e["type"] == "info" for e in answer_events), "Expected confidence question"
    assert not session.exited

    confidence_events = await session.step_async("Fairly confident based on observation.")
    info_events = [e for e in confidence_events if e.get("type") == "info"]
    assert any("Game finished" in e["content"] for e in info_events), (
        f"Expected 'Game finished' after confidence answer: {[e['content'] for e in info_events]}"
    )
    assert session.exited


@pytest.mark.skip(reason="pending evaluation fixes")
async def test_evaluation_shown_at_end(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Evaluation results should be shown to the player after game completion."""
    ...


@pytest.mark.skip(reason="pending run config refactoring")
async def test_overrides_work(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """All documented run config overrides should apply to Goal Horizon."""
    ...
