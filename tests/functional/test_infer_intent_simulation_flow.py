"""Functional tests for infer-intent game simulation flow with mocked LLMs.

This test suite validates the infer-intent game's unique mechanics:
1. PC is fixed to NA, NPC excludes NA
2. /predict-intent command triggers a 2-step completion form (goal inference + feedback)
3. /help command handler
4. Goal-aligned NPC responses
5. Completion form collects goal_inference and other_feedback, then exits

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
    """Seed a player with consent signature for infer-intent game access."""
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


INFER_INTENT_TEST_INPUTS = [
    "I look at the creature",
    "I wave my hand",
    "I move closer to observe",
    "I make a gentle sound",
    "I stay still and watch",
]


async def test_infer_intent_initialization(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test infer-intent game initializes correctly with SessionManager."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


async def test_infer_intent_enter_welcome_message(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test ENTER step produces welcome message and AI opening."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    enter_events = await session.step_async("")

    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    assert not session.exited, "Session should not be exited after ENTER"


async def test_infer_intent_predict_intent_command(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /predict-intent command triggers goal-inference question."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I look around")

    guess_events = await session.step_async("/predict-intent")

    info_events = [e for e in guess_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event asking for goal inference"
    assert not session.exited, "Session should not exit after /predict-intent"


async def test_infer_intent_help_command(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help command returns game instructions."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")

    help_events = await session.step_async("/help")

    info_events = [e for e in help_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /help command"
    assert not session.exited, "Session should remain active after /help"


async def test_infer_intent_simulation_turns(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test multi-turn simulation accumulates events correctly."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    turns_after_enter = session.turns

    for idx, user_input in enumerate(INFER_INTENT_TEST_INPUTS):
        turn_num = idx + 1
        prev_event_count = len(session._events)

        events = await session.step_async(user_input)

        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"

        assert len(session._events) > prev_event_count, f"Turn {turn_num}: _events should grow after each step"

    assert not session.exited, "Session should still be active"
    assert session.turns == turns_after_enter + len(INFER_INTENT_TEST_INPUTS)


async def test_infer_intent_completion_form(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test 2-step completion form: /predict-intent -> goal inference -> other feedback -> exit."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I observe the creature")

    guess_events = await session.step_async("/predict-intent")
    assert any(e["type"] == "info" for e in guess_events), "Expected info event from /predict-intent"
    assert not session.exited

    inference_events = await session.step_async("The creature is trying to find food.")
    assert any(e["type"] == "info" for e in inference_events), "Expected follow-up question"
    assert not session.exited, "Session should not exit after first answer"
    assert session.game.goal_inference == "The creature is trying to find food."

    feedback_events = await session.step_async("Interesting behavior overall.")
    assert any(e["type"] == "info" for e in feedback_events), "Expected completion confirmation"
    assert session.exited, "Session should exit after second answer"
    assert session.game.other_feedback == "Interesting behavior overall."
    assert session.game.evaluation == {}, "Evaluation should not be populated during gameplay"


async def test_infer_intent_exit_and_save(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test infer-intent game sessions can be exited and saved."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I wave my hand")
    await session.step_async("I look around")

    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"

    session.save()
