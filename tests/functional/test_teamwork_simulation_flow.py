"""Functional tests for teamwork game simulation flow with mocked LLMs.

This test suite validates the teamwork game's mechanics:
1. Standard enter/turn flow
2. /help and /abilities commands (NPC details hidden)
3. /finish triggers challenges question, then exits on answer
4. Session persistence
5. Post-play form present in game config

Tests use mocked LLMs to avoid external API dependencies.
"""

import pytest
from bson import ObjectId
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a player with consent signature for teamwork game access."""
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


async def test_teamwork_initialization(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test teamwork game initializes correctly with SessionManager."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


async def test_teamwork_enter_step(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test ENTER step produces welcome info event and AI opening turn."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    enter_events = await session.step_async("")

    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    ai_events = [e for e in enter_events if e.get("type") == "ai"]
    assert len(ai_events) > 0, "Expected AI opening response after welcome"

    assert session.game.shared_goal == "to secure the exposed control box before the room fully floods"

    assert session.turns == 1, "After ENTER, turns should be 1"
    assert not session.exited, "Session should not be exited after ENTER"


async def test_help_command(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help returns an info event and keeps session active."""
    session = await SessionManager.create_async(
        game="teamwork",
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
    assert "to secure the exposed control box before the room fully floods" in content
    assert not session.exited, "Session should remain active after /help"


async def test_abilities_command(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /abilities shows PC details and hides NPC details."""
    session = await SessionManager.create_async(
        game="teamwork",
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
    assert "NPC details are hidden" not in content, "NPC details should be shown in /abilities by default"
    assert not session.exited, "Session should remain active after /abilities"


async def test_finish_command_triggers_challenges_question(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /finish prompts for challenges reflection before ending the game."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I wave at the FW")

    finish_events = await session.step_async("/finish")

    info_events = [e for e in finish_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /finish"

    content = " ".join(e["content"] for e in info_events)
    assert "challenging" in content.lower(), f"Expected challenges question after /finish — 'challenging' not found in: {content}"
    assert not session.exited, "Session should not exit until challenges answer is submitted"


async def test_finish_command_exits_after_challenges_answer(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test submitting challenges answer after /finish exits the game and saves answer."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I observe the FW")
    await session.step_async("/finish")

    challenges_answer = "Communication was challenging; coordination was easier."
    completion_events = await session.step_async(challenges_answer)

    info_events = [e for e in completion_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected confirmation info event after challenges answer"
    assert session.exited, "Session should be exited after challenges answer"
    assert session.game.challenges == challenges_answer, "Expected game.challenges to equal the submitted answer"


async def test_simulation_turns(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test multi-turn simulation accumulates events and increments turn counter."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    turns_after_enter = session.turns

    user_inputs = [
        "I approach the FW",
        "I wait and observe",
        "I move in the same direction",
        "I make a gentle sound",
        "I stay still",
    ]

    for idx, user_input in enumerate(user_inputs):
        turn_num = idx + 1
        prev_event_count = len(session._events)

        events = await session.step_async(user_input)

        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"

        assert len(session._events) > prev_event_count, f"Turn {turn_num}: events should accumulate"
        assert session.turns == turns_after_enter + turn_num, (
            f"Turn {turn_num}: expected turns={turns_after_enter + turn_num}, got {session.turns}"
        )

    assert not session.exited, "Session should still be active after normal turns"


async def test_exit_and_save(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test teamwork sessions can be exited and saved."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I wave my hand")

    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"
    assert session.exit_reason == "test complete"

    session.save()


async def test_default_post_play_form_present(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Teamwork post-play: /finish → challenges question → answer → FINISH_CONTENT."""
    session = await SessionManager.create_async(
        game="teamwork",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")
    await session.step_async("I observe the FW")

    finish_events = await session.step_async("/finish")
    assert any(e["type"] == "info" for e in finish_events), "Expected challenges question after /finish"
    assert not session.exited

    completion_events = await session.step_async("Communication was most challenging.")
    info_events = [e for e in completion_events if e.get("type") == "info"]
    assert any("Game finished" in e["content"] for e in info_events), (
        f"Expected 'Game finished' after challenges answer: {[e['content'] for e in info_events]}"
    )
    assert session.exited


@pytest.mark.skip(reason="pending run config refactoring")
async def test_overrides_work(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """All documented run config overrides should apply to the teamwork game."""
    ...
