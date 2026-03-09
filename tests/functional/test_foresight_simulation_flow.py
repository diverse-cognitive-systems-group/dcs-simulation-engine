"""Functional tests for foresight game simulation flow with mocked LLMs.

This test suite validates the foresight game's unique mechanics:
1. Prediction parsing - validator allows predictions in user input
2. Prediction ignoring - updater processes only the action, not the prediction
3. Completion notes - /complete triggers a question, next input is collected
4. Multi-turn simulation flow with prediction-containing inputs

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

# Test player ID for foresight tests (requires consent)
TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, mongo_provider):
    """Seed a player with consent signature for foresight game access."""
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


FORESIGHT_TEST_INPUTS = [
    "I wave my hand and predict they will wave back",
    "I look around",
    "I move closer. I predict the flatworm will retreat.",
    "I observe the flatworm",
    "I stay still and predict they will move toward me",
    "I make a sound",
    "I touch the surface. I predict the flatworm will curl up.",
    "I step back",
    "I wait and predict they will explore",
    "I examine the environment",
]


@pytest.mark.functional
def test_foresight_initialization(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test foresight game initializes correctly with SessionManager."""
    session = SessionManager.create(
        game="foresight",
        provider=mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


@pytest.mark.functional
def test_foresight_enter_welcome_message(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test ENTER step produces welcome message and AI opening."""
    session = SessionManager.create(
        game="foresight",
        provider=mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    enter_events = list(session.step(""))

    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    ai_events = [e for e in enter_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "Expected AI opening response after welcome"

    assert session.turns == 1, "After ENTER, turns should be 1"


@pytest.mark.functional
def test_foresight_simulation_10_turns(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test multi-turn simulation with prediction-containing inputs."""
    session = SessionManager.create(
        game="foresight",
        provider=mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    list(session.step(""))
    turns_after_enter = session.turns

    for idx, user_input in enumerate(FORESIGHT_TEST_INPUTS):
        turn_num = idx + 1
        events = list(session.step(user_input))

        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, (
            f"Turn {turn_num}: Expected AI response event (validator should accept prediction syntax)"
        )

        assert "predict" not in ai_events[0]["content"].lower(), (
            f"Turn {turn_num}: Updater response should not acknowledge predictions"
        )

        assert session.turns == turns_after_enter + turn_num, (
            f"Turn {turn_num}: turns should be {turns_after_enter + turn_num} (got {session.turns})"
        )

    assert not session.exited, "Session should still be active after 10 turns"


@pytest.mark.functional
def test_foresight_complete_command(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test /complete command triggers completion-notes question."""
    session = SessionManager.create(
        game="foresight",
        provider=mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    list(session.step(""))
    list(session.step("I wave my hand"))
    list(session.step("I look around"))

    complete_events = list(session.step("/complete"))

    # /complete should yield an info event asking for notes
    info_events = [e for e in complete_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected an info event asking for completion notes"
    assert "prediction" in info_events[0]["content"].lower() or "notes" in info_events[0]["content"].lower(), (
        "Completion question should ask about predictions or notes"
    )

    # Session should NOT be exited yet — waiting for the answer
    assert not session.exited, "Session should not exit until completion notes are provided"


@pytest.mark.functional
def test_foresight_completion_notes_collected(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test that the answer after /complete is collected and game exits."""
    session = SessionManager.create(
        game="foresight",
        provider=mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    list(session.step(""))
    list(session.step("I wave my hand"))
    list(session.step("/complete"))

    # Provide the completion notes
    notes_events = list(session.step("My notes about my predictions."))

    info_events = [e for e in notes_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected confirmation info event after notes submitted"

    # Game should exit after notes collected
    assert session.exited, "Session should be exited after completion notes provided"
    assert session.game.completion_notes == "My notes about my predictions."


@pytest.mark.functional
def test_foresight_run_save(patch_llm_client, _isolate_db_state, mongo_provider):
    """Test foresight game sessions can be saved to database."""
    session = SessionManager.create(
        game="foresight",
        provider=mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    list(session.step(""))
    list(session.step("I wave my hand and predict they will respond"))
    list(session.step("I look around"))
    list(session.step("I observe the flatworm"))

    session.exit(reason="test complete")
    assert session.exited, "Session should be exited after exit()"

    # save() is called by exit(); calling again is a no-op (idempotent)
    session.save()
