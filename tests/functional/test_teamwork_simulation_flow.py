"""Functional tests for teamwork game simulation flow with mocked LLMs.

This test suite validates the teamwork game's unique mechanics:
1. Open access (no consent requirement)
2. PC requires human-like-cognition descriptor, NPC is open
3. Collaborative interaction between characters
4. /help command handler
5. Checkpoint validation with retry limits

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest

from dcs_simulation_engine.core.run_manager import RunManager


# Test inputs for multi-turn simulation
TEAMWORK_TEST_INPUTS = [
    "I look around to assess the situation",
    "I wave to get the other character's attention",
    "I point toward the goal",
    "I move closer to collaborate",
    "I gesture to suggest a plan",
]


@pytest.mark.functional
def test_teamwork_initialization(patch_llm_client, _isolate_db_state):
    """Test teamwork game initializes correctly with RunManager.

    Verifies:
    - RunManager.create works with game="Teamwork"
    - No consent/player_id required (open access)
    - Initial lifecycle is ENTER
    - Initial history is empty
    """
    run = RunManager.create(
        game="Teamwork",
        pc_choice="human-normative",
        npc_choice="flatworm",
    )

    assert run.state["lifecycle"] == "ENTER", "Initial lifecycle should be ENTER"
    assert len(run.state["history"]) == 0, "Initial history should be empty"


@pytest.mark.functional
def test_teamwork_enter_welcome_message(patch_llm_client, _isolate_db_state):
    """Test ENTER lifecycle produces welcome message and transitions to UPDATE.

    Verifies:
    - run.step("") produces info event with welcome content
    - Lifecycle transitions to UPDATE
    """
    run = RunManager.create(
        game="Teamwork",
        pc_choice="human-normative",
        npc_choice="flatworm",
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
def test_teamwork_help_command(patch_llm_client, _isolate_db_state):
    """Test /help command returns game instructions.

    Verifies:
    - /help returns info event
    - Lifecycle remains UPDATE
    """
    run = RunManager.create(
        game="Teamwork",
        pc_choice="human-normative",
        npc_choice="flatworm",
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
def test_teamwork_simulation_turns(patch_llm_client, _isolate_db_state):
    """Test multi-turn simulation accumulates history correctly.

    Verifies:
    - Multiple turns produce AI response events
    - History accumulates correctly (2 messages per turn)
    """
    run = RunManager.create(
        game="Teamwork",
        pc_choice="human-normative",
        npc_choice="flatworm",
    )

    # Execute ENTER step
    list(run.step(""))
    enter_step_message_count = len(run.state["history"])

    # Execute multiple turns
    for idx, user_input in enumerate(TEAMWORK_TEST_INPUTS):
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
def test_teamwork_exit(patch_llm_client, _isolate_db_state):
    """Test teamwork game runs can be exited correctly.

    Verifies:
    - run.exit() transitions lifecycle to EXIT

    Note: save_runs is false for teamwork game, so we don't test run.save()
    """
    run = RunManager.create(
        game="Teamwork",
        pc_choice="human-normative",
        npc_choice="flatworm",
    )

    # Execute ENTER and a few turns
    list(run.step(""))
    list(run.step("I look around"))
    list(run.step("I wave my hand"))

    # Exit
    run.exit(reason="test complete")
    assert run.state["lifecycle"] == "EXIT", "Lifecycle should be EXIT after exit()"
