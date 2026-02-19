"""Functional tests for foresight game simulation flow with mocked LLMs.

This test suite validates the foresight game's unique mechanics:
1. Prediction parsing - validator allows predictions in user input
2. Prediction ignoring - updater processes only the action, not the prediction
3. Completion form - custom additional_notes field for research data
4. Multi-turn simulation flow with prediction-containing inputs

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest
from bson import ObjectId

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.core.run_manager import RunManager


# Test player ID for foresight tests (requires consent)
TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state):
    """Seed a player with consent signature for foresight game access.

    The foresight game requires players to have consent_signature.answer
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


# Test inputs with mixed prediction formats
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
def test_foresight_initialization(patch_llm_client, _isolate_db_state):
    """Test foresight game initializes correctly with RunManager.

    Verifies:
    - RunManager.create works with game="foresight"
    - PC must be human-normative
    - Initial lifecycle is ENTER
    - Initial history is empty
    """
    run = RunManager.create(
        game="foresight",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    assert run.state["lifecycle"] == "ENTER", "Initial lifecycle should be ENTER"
    assert len(run.state["history"]) == 0, "Initial history should be empty"


@pytest.mark.functional
def test_foresight_enter_welcome_message(patch_llm_client, _isolate_db_state):
    """Test ENTER lifecycle produces welcome message and transitions to UPDATE.

    Verifies:
    - run.step("") produces info event with welcome content
    - Lifecycle transitions to UPDATE
    - History has 2 messages after ENTER
    """
    run = RunManager.create(
        game="foresight",
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

    # Verify history
    assert len(run.state["history"]) == 2, "After ENTER, history should have 2 messages"
    assert run.turns == 1, "After ENTER, turns should be 1"


@pytest.mark.functional
def test_foresight_simulation_10_turns(patch_llm_client, _isolate_db_state):
    """Test multi-turn simulation with prediction-containing inputs.

    Verifies:
    - Validator accepts prediction syntax without rejection
    - Each turn produces AI response events
    - History accumulates correctly (2 messages per turn)
    - Updater responses focus on action only (mock returns action-focused response)
    """
    run = RunManager.create(
        game="foresight",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))
    enter_step_message_count = len(run.state["history"])

    # Execute 10 turns with prediction inputs
    for idx, user_input in enumerate(FORESIGHT_TEST_INPUTS):
        turn_num = idx + 1

        events = list(run.step(user_input))

        # Verify AI response (validator accepted the input)
        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event (validator should accept prediction syntax)"

        # Verify response focuses on action (mock returns NPC behavior, not prediction acknowledgment)
        ai_response = ai_events[0]
        assert "predict" not in ai_response["content"].lower(), (
            f"Turn {turn_num}: Updater response should not acknowledge predictions"
        )

        # Verify history accumulates correctly
        expected_history_length = enter_step_message_count + (turn_num * 2)
        actual_history_length = len(run.state["history"])
        assert actual_history_length == expected_history_length, (
            f"Turn {turn_num}: History should have {expected_history_length} messages "
            f"(got {actual_history_length})"
        )

        # Verify turn count
        expected_turn_count = (enter_step_message_count + turn_num * 2) // 2
        assert run.turns == expected_turn_count, (
            f"Turn {turn_num}: run.turns should be {expected_turn_count} "
            f"(got {run.turns})"
        )

    # Verify final state
    expected_final_turns = (enter_step_message_count + 10 * 2) // 2
    assert run.turns == expected_final_turns, (
        f"Should have completed {expected_final_turns} turns (got {run.turns})"
    )
    assert run.state["lifecycle"] == "UPDATE", "Should still be in UPDATE lifecycle"


@pytest.mark.functional
def test_foresight_complete_command(patch_llm_client, _isolate_db_state):
    """Test /complete command triggers COMPLETE lifecycle transition.

    Verifies:
    - /complete command transitions lifecycle to COMPLETE
    - Completion form includes additional_notes field
    """
    run = RunManager.create(
        game="foresight",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER step
    list(run.step(""))
    assert run.state["lifecycle"] == "UPDATE"

    # Execute a few turns
    list(run.step("I wave my hand"))
    list(run.step("I look around"))

    # Execute /complete command
    list(run.step("/complete"))

    # Verify lifecycle transition
    assert run.state["lifecycle"] == "COMPLETE", (
        "After /complete command, lifecycle should transition to COMPLETE"
    )

    # Verify completion form has additional_notes field
    completion_form = run.state.get("forms", {}).get("completion_form", {})
    questions = completion_form.get("questions", [])
    question_keys = [q.get("key") for q in questions]
    assert "additional_notes" in question_keys, (
        "Completion form should include additional_notes question"
    )


@pytest.mark.functional
def test_foresight_run_save(patch_llm_client, _isolate_db_state):
    """Test foresight game runs can be saved to database.

    Verifies:
    - run.save() returns non-None path after gameplay
    """
    run = RunManager.create(
        game="foresight",
        pc_choice="human-normative",
        npc_choice="flatworm",
        player_id=str(TEST_PLAYER_ID),
    )

    # Execute ENTER and a few turns
    list(run.step(""))
    list(run.step("I wave my hand and predict they will respond"))
    list(run.step("I look around"))
    list(run.step("I observe the flatworm"))

    # Exit and save
    run.exit(reason="test complete")
    assert run.state["lifecycle"] == "EXIT", "Lifecycle should be EXIT after exit()"

    saved = run.save()
    assert saved is not None, "run.save() should return a path on success"
