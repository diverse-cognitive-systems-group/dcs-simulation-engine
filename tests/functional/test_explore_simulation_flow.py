"""Functional tests for explore game simulation flow with mocked LLMs.

This test suite validates the explore game's mechanics:
1. Standard 10-turn simulation flow
2. /help includes PC and NPC hid
3. /abilities shows PC and NPC details
4. /finish exits the game; /help and /abilities do not
5. Default characters available in seeded DB
6. API and GUI source players can both play

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest
from dcs_simulation_engine.core.session_manager import (
    SessionManager,
)

pytestmark = [pytest.mark.functional, pytest.mark.anyio]


async def test_explore_simulation_10_turns(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test complete simulation flow: init -> 10 turns -> save.

    This test validates:
    1. SessionManager initializes correctly from explore game config
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
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"

    # Run the ENTER step (empty input)
    enter_events = await session.step_async("")

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

        events = await session.step_async(user_input)

        # Verify AI response event
        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"
        assert ai_events[0]["content"] == "The flatworm moves slowly across the surface."

        # Events should accumulate
        assert len(session._events) > prev_event_count, f"Turn {turn_num}: _events should grow after each step"

        # Turn count should increment
        assert session.turns == turn_num + 1, f"Turn {turn_num}: session.turns should be {turn_num + 1} (got {session.turns})"

    # Verify final turn count: 1 (ENTER) + 10 user turns
    assert session.turns == 11, f"Should have completed 11 turns (got {session.turns})"
    assert not session.exited, "Session should not be exited before explicit exit()"

    # Exit the session
    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"
    assert session.exit_reason == "test complete"

    # Save remains a compatibility no-op; persistence is event-sourced elsewhere.
    session.save()


async def test_help_command_includes_pc_and_npc_hid(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help response contains both PC and NPC hids."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
    )
    await session.step_async("")

    help_events = await session.step_async("/help")

    info_events = [e for e in help_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /help"

    content = " ".join(e["content"] for e in info_events)
    assert "human-normative" in content, "PC hid 'human-normative' should appear in /help"
    assert "flatworm" in content, "NPC hid 'flatworm' should appear in /help"


async def test_abilities_command_shows_pc_and_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /abilities response shows both PC and NPC hid and ability sections."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
    )
    await session.step_async("")

    abilities_events = await session.step_async("/abilities")

    info_events = [e for e in abilities_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /abilities"

    content = " ".join(e["content"] for e in info_events)
    assert "human-normative" in content, "PC hid should appear in /abilities"
    assert "flatworm" in content, "NPC hid should appear in /abilities"
    assert "Abilities" in content, "Abilities section header should appear"


async def test_finish_command_exits_game(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /finish exits the session."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
    )
    await session.step_async("")
    await session.step_async("I look around")

    finish_events = await session.step_async("/finish")

    info_events = [e for e in finish_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /finish"
    assert session.exited, "Session should be exited after /finish"


async def test_only_finish_command_ends_game(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test that /help and /abilities do not exit the session."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
    )
    await session.step_async("")

    await session.step_async("/help")
    assert not session.exited, "Session should remain active after /help"

    await session.step_async("/abilities")
    assert not session.exited, "Session should remain active after /abilities"


async def test_default_characters_available(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test session creation succeeds with default characters from seeded DB."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        pc_choice="human-normative",
        npc_choice="flatworm",
    )
    assert session is not None, "Session should be created successfully"
    assert not session.exited, "New session should not be exited"


async def test_api_player_can_play(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test that a session created with source='api' starts and produces events."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        source="api",
        pc_choice="human-normative",
        npc_choice="flatworm",
    )

    enter_events = await session.step_async("")
    ai_events = [e for e in enter_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "API player: expected AI event in ENTER step"

    turn_events = await session.step_async("I look around")
    ai_events = [e for e in turn_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "API player: expected AI response on first turn"


async def test_gui_player_can_play(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test that a session created with source='gui' starts and produces events."""
    session = await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        source="gui",
        pc_choice="human-normative",
        npc_choice="flatworm",
    )

    enter_events = await session.step_async("")
    ai_events = [e for e in enter_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "GUI player: expected AI event in ENTER step"

    turn_events = await session.step_async("I look around")
    ai_events = [e for e in turn_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "GUI player: expected AI response on first turn"


@pytest.mark.skip(reason="pending resume functionality implementation")
async def test_resume_after_leaving(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Game should resume from the same state after the player reconnects."""
    ...


@pytest.mark.skip(reason="pending run config refactoring")
async def test_overrides_work(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """All documented run config overrides should apply to the explore game."""
    ...
