"""Basic E2E test for simulation flow with mocked LLMs.

This test validates the core simulation flow from initialization through
multiple conversation turns to saving, without requiring external API calls.
"""

import pytest

from dcs_simulation_engine.core.run_manager import RunManager


@pytest.mark.functional
def test_basic_ungated_simulation_10_turns(patch_llm_client, _isolate_db_state):
    """Test complete simulation flow: init -> 10 turns -> save.

    This test validates:
    1. RunManager initializes correctly from explore.yml game config
    2. ENTER lifecycle step returns welcome message
    3. Multiple user inputs get processed through the simulation graph
    4. LLM validator and updater nodes execute with mocked responses
    5. State accumulates conversation history correctly (2 messages per turn)
    6. Turn counting works correctly
    7. Exit transitions to EXIT lifecycle
    8. Run saves successfully to database

    Flow:
        Create RunManager -> Execute ENTER step -> Execute 10 user input steps
        -> Verify state at each step -> Exit -> Save -> Verify save succeeded

    Args:
        patch_llm_client: Fixture that patches ChatOpenRouter with mock LLM
        _isolate_db_state: Fixture that provides isolated mongomock database
    """
    # Initialize RunManager with explore game
    run = RunManager.create(
        game="explore", pc_choice="human-normative", npc_choice="flatworm"
    )

    # assert initial state
    assert run.state["lifecycle"] == "ENTER", "Initial lifecycle should be ENTER"
    assert len(run.state["history"]) == 0, "Initial history should be empty"

    # run the game
    enter_events = list(run.step(""))

    # verify there was an info message (usually a welcome)
    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    assert (
        run.state["lifecycle"] == "UPDATE"
    ), "After ENTER step, lifecycle should transition to UPDATE"

    # track how many messages were added during ENTER step
    enter_step_message_count = len(run.state["history"])
    assert enter_step_message_count == 2, "After ENTER, history should have 2 messages"
    assert run.turns == 1, "After ENTER, turns should be 1"
    
    # start executing user inputs
    user_inputs = [
        "I wave my hand",
        "I look around",
        "I move closer",
        "I observe the flatworm",
        "I stay still",
        "I make a sound",
        "I touch the surface",
        "I step back",
        "I wait",
        "I examine the environment",
    ]

    for idx, user_input in enumerate(user_inputs):
        turn_num = idx + 1

        # execute step with user input
        events = list(run.step(user_input))

        # verify events contain ai responses
        ai_events = [e for e in events if e.get("type") == "ai"]

        # for this test we should only have one ai response per user input
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"

        # TODO: Support more dynamic responses in the mock
        ai_response = ai_events[0] if ai_events else None
        assert ai_response["content"] == "The flatworm moves slowly across the surface."

        # Verify state updates
        # History should have: ENTER messages + (turn_num * 2 messages per turn)
        expected_history_length = enter_step_message_count + (turn_num * 2)
        actual_history_length = len(run.state["history"])
        assert (
            actual_history_length == expected_history_length
        ), f"Turn {turn_num}: History should have {expected_history_length} messages (got {actual_history_length})"

        # run.turns = len(history) // 2, includes ENTER messages
        expected_turn_count = (enter_step_message_count + turn_num * 2) // 2
        assert run.turns == expected_turn_count, (
            f"Turn {turn_num}: run.turns should be {expected_turn_count} "
            f"(got {run.turns})"
        )

    # Step 4: Verify final state after 10 turns
    # Total turns = (ENTER messages + 10 conversation turns * 2) // 2
    expected_final_turns = (enter_step_message_count + 10 * 2) // 2
    assert run.turns == expected_final_turns, (
        f"Should have completed {expected_final_turns} turns " f"(got {run.turns})"
    )

    assert (
        run.state["lifecycle"] == "UPDATE"
    ), "Should still be in UPDATE lifecycle before exit"


    # History = ENTER messages + 10 conversation turns × 2 messages
    expected_history_length = enter_step_message_count + 10 * 2
    assert len(run.state["history"]) == expected_history_length, (
        f"History should contain {expected_history_length} messages "
        f"(ENTER: {enter_step_message_count}, turns: 20)"
    )

    # Step 5: Exit the simulation
    run.exit(reason="test complete")

    assert (
        run.state["lifecycle"] == "EXIT"
    ), "After exit(), lifecycle should transition to EXIT"

    # Step 6: Save run to database
    saved = run.save()

    # run.save() returns the path to saved file, not True
    assert saved is not None, "run.save() should return a path on success"