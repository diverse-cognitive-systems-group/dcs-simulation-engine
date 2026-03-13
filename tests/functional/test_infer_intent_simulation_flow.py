"""Functional tests for infer-intent game simulation flow with mocked LLMs.

This test suite validates the infer-intent game's unique mechanics:
1. PC is fixed to human-normative, NPC excludes human-normative
2. /guess command triggers a 2-step completion form (goal inference + feedback)
3. /help and /abilities command handlers
4. Goal-aligned NPC responses
5. Completion form collects goal_inference and other_feedback, then scores and exits

Tests use mocked LLMs to avoid external API dependencies.
"""

import asyncio

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import (
    SessionManager,
)
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)

# Test player ID for infer-intent tests (requires consent)
TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, mongo_provider):
    """Seed a player with consent signature for infer-intent game access."""
    db = mongo_provider.get_db()
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


@pytest.mark.functional
def test_infer_intent_initialization(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test infer-intent game initializes correctly with SessionManager."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


@pytest.mark.functional
def test_infer_intent_enter_welcome_message(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test ENTER step produces welcome message and AI opening."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    enter_events = list(session.step(""))

    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    assert not session.exited, "Session should not be exited after ENTER"


@pytest.mark.functional
def test_infer_intent_guess_command(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test /guess command triggers goal-inference question."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    list(session.step(""))
    list(session.step("I look around"))

    guess_events = list(session.step("/guess"))

    info_events = [e for e in guess_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event asking for goal inference"

    # Session should NOT exit yet — awaiting goal inference answer
    assert not session.exited, "Session should not exit after /guess"


@pytest.mark.functional
def test_infer_intent_help_command(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test /help command returns game instructions."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    list(session.step(""))

    help_events = list(session.step("/help"))

    info_events = [e for e in help_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /help command"
    assert not session.exited, "Session should remain active after /help"


@pytest.mark.functional
def test_infer_intent_abilities_command(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test /abilities command returns character abilities."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    list(session.step(""))

    abilities_events = list(session.step("/abilities"))

    info_events = [e for e in abilities_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /abilities command"
    assert not session.exited, "Session should remain active after /abilities"


@pytest.mark.functional
def test_infer_intent_simulation_turns(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test multi-turn simulation accumulates events correctly."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    list(session.step(""))
    turns_after_enter = session.turns

    for idx, user_input in enumerate(INFER_INTENT_TEST_INPUTS):
        turn_num = idx + 1
        prev_event_count = len(session._events)

        events = list(session.step(user_input))

        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"

        assert len(session._events) > prev_event_count, f"Turn {turn_num}: _events should grow after each step"

    assert not session.exited, "Session should still be active"
    assert session.turns == turns_after_enter + len(INFER_INTENT_TEST_INPUTS)


@pytest.mark.functional
def test_infer_intent_completion_form(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test 2-step completion form: /guess -> goal inference -> other feedback -> exit."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    list(session.step(""))
    list(session.step("I observe the creature"))

    # Step 1: /guess triggers goal inference question
    guess_events = list(session.step("/guess"))
    assert any(e["type"] == "info" for e in guess_events), "Expected info event from /guess"
    assert not session.exited

    # Step 2: provide goal inference — triggers other feedback question
    inference_events = list(session.step("The creature is trying to find food."))
    assert any(e["type"] == "info" for e in inference_events), "Expected follow-up question"
    assert not session.exited, "Session should not exit after first answer"
    assert session.game.goal_inference == "The creature is trying to find food."

    # Step 3: provide other feedback — scores and exits
    feedback_events = list(session.step("Interesting behavior overall."))
    assert any(e["type"] == "info" for e in feedback_events), "Expected completion confirmation"
    assert session.exited, "Session should exit after second answer"
    assert session.game.other_feedback == "Interesting behavior overall."
    assert session.game.evaluation != {}, "Evaluation should be populated after scoring"


@pytest.mark.functional
def test_infer_intent_exit_and_save(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test infer-intent game sessions can be exited and saved."""
    session = asyncio.run(
        SessionManager.create_async(
            game="Infer Intent",
            provider=mongo_provider,
            pc_choice="human-normative",
            npc_choice="flatworm",
            player_id=str(TEST_PLAYER_ID),
        )
    )

    list(session.step(""))
    list(session.step("I wave my hand"))
    list(session.step("I look around"))

    session.exit(reason="test complete")
    assert session.exited, "Session should be exited after exit()"

    # save() is called internally by exit(); calling again is a no-op
    session.save()
