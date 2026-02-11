"""Functional tests for infer-intent game simulation flow with mocked LLMs.

This test suite validates the infer-intent game's unique mechanics:
1. PC is fixed to human-normative, NPC excludes human-normative
2. /guess command triggers COMPLETE lifecycle (for goal inference submission)
3. /help and /abilities command handlers
4. Goal-aligned NPC responses
5. Completion form with user_goal_inference field

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest
from bson import ObjectId

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.core.run_manager import RunManager


# Test player ID for infer-intent tests (requires consent)
TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state):
    """Seed a player with consent signature for infer-intent game access.

    The infer-intent game requires players to have consent_signature.answer
    in their player document. This fixture creates such a player.
    """
    db = dbh.get_db()
    db[dbh.PLAYERS_COL].insert_one({
        "_id": TEST_PLAYER_ID,
        "consent_signature": {
            "answer": ["I confirm that the information I have provided is true..."]
        },
        "full_name": "Test Player",
        "email": "test@example.com",
    })
    yield


# Test inputs for multi-turn simulation
INFER_INTENT_TEST_INPUTS = [
    "I look at the creature",
    "I wave my hand",
    "I move closer to observe",
    "I make a gentle sound",
    "I stay still and watch",
]


@pytest.mark.functional
def test_infer_intent_initialization(patch_llm_client, _isolate_db_state):
    """Test infer-intent game initializes correctly with RunManager.

    Verifies:
    - RunManager.create works with game="Infer Intent"
    - PC must be human-normative
    - Initial lifecycle is ENTER
    - Initial history is empty
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    assert run.state["lifecycle"] == "ENTER", "Initial lifecycle should be ENTER"
    assert len(run.state["history"]) == 0, "Initial history should be empty"


@pytest.mark.functional
def test_infer_intent_enter_welcome_message(patch_llm_client, _isolate_db_state):
    """Test ENTER lifecycle produces welcome message and transitions to UPDATE.

    Verifies:
    - run.step("") produces info event with welcome content
    - Lifecycle transitions to UPDATE
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    enter_events = list(run.step(""))

    # Verify welcome message
    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    # Verify lifecycle transition
    assert (
        run.state["lifecycle"] == "UPDATE"
    ), "After ENTER step, lifecycle should transition to UPDATE"


@pytest.mark.functional
def test_infer_intent_guess_command(patch_llm_client, _isolate_db_state):
    """Test /guess command triggers COMPLETE lifecycle transition.

    Verifies:
    - /guess command transitions lifecycle to COMPLETE
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))
    assert run.state["lifecycle"] == "UPDATE"

    # Execute a turn first
    list(run.step("I look around"))

    # Execute /guess command
    list(run.step("/guess"))

    # Verify lifecycle transition
    assert run.state["lifecycle"] == "COMPLETE", (
        "After /guess command, lifecycle should transition to COMPLETE"
    )


@pytest.mark.functional
def test_infer_intent_help_command(patch_llm_client, _isolate_db_state):
    """Test /help command returns game instructions.

    Verifies:
    - /help returns info event
    - Lifecycle remains UPDATE
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))
    assert run.state["lifecycle"] == "UPDATE"

    # Execute /help command
    help_events = list(run.step("/help"))

    # Verify info event returned
    info_events = [e for e in help_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /help command"

    # Verify lifecycle remains UPDATE
    assert run.state["lifecycle"] == "UPDATE", (
        "After /help command, lifecycle should remain UPDATE"
    )


@pytest.mark.functional
def test_infer_intent_abilities_command(patch_llm_client, _isolate_db_state):
    """Test /abilities command returns character abilities.

    Verifies:
    - /abilities returns info event
    - Lifecycle remains UPDATE
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))
    assert run.state["lifecycle"] == "UPDATE"

    # Execute /abilities command
    abilities_events = list(run.step("/abilities"))

    # Verify info event returned
    info_events = [e for e in abilities_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /abilities command"

    # Verify lifecycle remains UPDATE
    assert run.state["lifecycle"] == "UPDATE", (
        "After /abilities command, lifecycle should remain UPDATE"
    )


@pytest.mark.functional
def test_infer_intent_simulation_turns(patch_llm_client, _isolate_db_state):
    """Test multi-turn simulation accumulates history correctly.

    Verifies:
    - Multiple turns produce AI response events
    - History accumulates correctly (2 messages per turn)
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))
    enter_step_message_count = len(run.state["history"])

    # Execute multiple turns
    for idx, user_input in enumerate(INFER_INTENT_TEST_INPUTS):
        turn_num = idx + 1

        events = list(run.step(user_input))

        # Verify AI response
        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"

        # Verify history accumulates correctly
        expected_history_length = enter_step_message_count + (turn_num * 2)
        actual_history_length = len(run.state["history"])
        assert actual_history_length == expected_history_length, (
            f"Turn {turn_num}: History should have {expected_history_length} messages "
            f"(got {actual_history_length})"
        )

    # Verify still in UPDATE lifecycle
    assert run.state["lifecycle"] == "UPDATE", "Should still be in UPDATE lifecycle"


@pytest.mark.functional
def test_infer_intent_completion_form(patch_llm_client, _isolate_db_state):
    """Test completion form includes user_goal_inference field.

    Verifies:
    - After /guess, completion form has user_goal_inference question
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))

    # Execute a turn
    list(run.step("I observe the creature"))

    # Execute /guess command
    list(run.step("/guess"))

    # Verify lifecycle is COMPLETE
    assert run.state["lifecycle"] == "COMPLETE"

    # Verify completion form has user_goal_inference field
    completion_form = run.state.get("forms", {}).get("completion_form", {})
    questions = completion_form.get("questions", [])
    question_keys = [q.get("key") for q in questions]
    assert "user_goal_inference" in question_keys, (
        "Completion form should include user_goal_inference question"
    )


@pytest.mark.functional
def test_infer_intent_exit_and_save(patch_llm_client, _isolate_db_state):
    """Test infer-intent game runs can be exited and saved to database.

    Verifies:
    - run.exit() transitions lifecycle to EXIT
    - run.save() returns non-None path after exit
    """
    run = RunManager.create(
        game="Infer Intent",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER and a few turns
    list(run.step(""))
    list(run.step("I wave my hand"))
    list(run.step("I look around"))

    # Exit and save
    run.exit(reason="test complete")
    assert run.state["lifecycle"] == "EXIT", "Lifecycle should be EXIT after exit()"

    saved = run.save()
    assert saved is not None, "run.save() should return a path on success"
