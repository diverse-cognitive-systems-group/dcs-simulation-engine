"""Basic E2E test for simulation flow with mocked LLMs.

This test validates the core simulation flow from initialization through
multiple conversation turns to saving, without requiring external API calls.
"""

import pytest
from dcs_simulation_engine.core.session_manager import SessionManager


@pytest.mark.functional
def test_basic_ungated_simulation_10_turns(patch_llm_client, _isolate_db_state):
    """Test complete simulation flow: init -> 10 turns -> save.

    This test validates:
    1. SessionManager initializes correctly from explore.yaml game config
    2. ENTER step returns an info event (welcome message)
    3. Multiple user inputs each produce an AI response event
    4. Event history accumulates correctly
    5. Turn counting works correctly
    6. Exit marks the session as exited
    7. Session saves successfully to database

    Flow:
        Create SessionManager -> Execute ENTER step -> Execute 10 user input steps
        -> Verify events at each step -> Exit -> Verify exited -> Save
    """
    session = SessionManager.create(
        game="explore", pc_choice="human-normative", npc_choice="flatworm"
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"

    # Run the ENTER step (empty input)
    enter_events = list(session.step(""))

    # Verify there was an info message (welcome)
    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    # Verify at least one AI event came through
    ai_events = [e for e in enter_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "Expected AI response event in ENTER step"
    assert session.turns == 1, "After ENTER, turns should be 1"

    enter_event_count = len(session._events)
    assert enter_event_count >= 2, "After ENTER, at least 2 events should be recorded"

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
        prev_event_count = len(session._events)

        events = list(session.step(user_input))

        # Verify AI response event
        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"
        assert ai_events[0]["content"] == "The flatworm moves slowly across the surface."

        # Events should accumulate
        assert len(session._events) > prev_event_count, (
            f"Turn {turn_num}: _events should grow after each step"
        )

        # Turn count should increment
        assert session.turns == turn_num + 1, (
            f"Turn {turn_num}: session.turns should be {turn_num + 1} (got {session.turns})"
        )

    # Verify final turn count: 1 (ENTER) + 10 user turns
    assert session.turns == 11, f"Should have completed 11 turns (got {session.turns})"
    assert not session.exited, "Session should not be exited before explicit exit()"

    # Exit the session
    session.exit(reason="test complete")
    assert session.exited, "Session should be exited after exit()"
    assert session.exit_reason == "test complete"

    # Save (no-op if save_runs=False; explore.yaml has save_runs=True but no DB doc_id check)
    session.save()
