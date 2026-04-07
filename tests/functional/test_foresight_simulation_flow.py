"""Functional tests for foresight game simulation flow with mocked LLMs.

This test suite validates the foresight game's unique mechanics:
1. Prediction parsing - validator allows predictions embedded in user input
2. Prediction ignoring - updater processes only the action, not the prediction
3. /finish command ends the game
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

pytestmark = [pytest.mark.functional, pytest.mark.anyio]

# Test player ID for foresight tests (requires consent)
TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a player with consent signature for foresight game access."""
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


async def test_foresight_initialization(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test foresight game initializes correctly with SessionManager."""
    session = await SessionManager.create_async(
        game="foresight",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


async def test_foresight_enter_welcome_message(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test ENTER step produces welcome message and AI opening."""
    session = await SessionManager.create_async(
        game="foresight",
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

    assert session.turns == 1, "After ENTER, turns should be 1"


async def test_foresight_simulation_10_turns(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test multi-turn simulation with prediction-containing inputs."""
    session = await SessionManager.create_async(
        game="foresight",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    turns_after_enter = session.turns
    turn_limit = int(str(session.stopping_conditions["turns"][0]).lstrip("<>=!"))
    active_user_turns = max(0, turn_limit - turns_after_enter)

    for idx, user_input in enumerate(FORESIGHT_TEST_INPUTS[:active_user_turns]):
        turn_num = idx + 1
        events = await session.step_async(user_input)

        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event (validator should accept prediction syntax)"

        assert "predict" not in ai_events[0]["content"].lower(), f"Turn {turn_num}: Updater response should not acknowledge predictions"

        assert session.turns == turns_after_enter + turn_num, (
            f"Turn {turn_num}: turns should be {turns_after_enter + turn_num} (got {session.turns})"
        )

    assert session.turns == turn_limit, f"Session should reach the configured turn cap of {turn_limit}"
    assert not session.exited, "Session should stay open until the next input observes the stopping condition"


async def test_foresight_finish_command_exits_game(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /finish command ends the game."""
    session = await SessionManager.create_async(
        game="foresight",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I wave my hand")

    finish_events = await session.step_async("/finish")

    info_events = [e for e in finish_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected an info event from /finish"
    assert session.exited, "Session should be exited after /finish"


async def test_foresight_run_save(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test foresight game sessions can be saved to database."""
    session = await SessionManager.create_async(
        game="foresight",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I wave my hand and predict they will respond")
    await session.step_async("I look around")
    await session.step_async("I observe the flatworm")

    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"

    session.save()


async def test_help_hides_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help shows NPC hid but does not reveal NPC description."""
    session = await SessionManager.create_async(
        game="foresight",
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
    assert "FW" in content, "NPC hid should appear in /help"
    assert "details hidden" in content.lower(), "Expected NPC details to be hidden in /help — '(*details hidden*)' not found"


async def test_abilities_hides_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /abilities shows PC abilities but hides all NPC details."""
    session = await SessionManager.create_async(
        game="foresight",
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
    assert "NPC details are hidden" in content, "Expected '*NPC details are hidden.*' in /abilities NPC section"


async def test_default_post_play_form_present(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Foresight ends with FINISH_CONTENT after /finish — no post-play questions."""
    session = await SessionManager.create_async(
        game="foresight",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")
    await session.step_async("I observe the flatworm")

    finish_events = await session.step_async("/finish")
    info_events = [e for e in finish_events if e.get("type") == "info"]
    assert any("Game finished" in e["content"] for e in info_events), (
        f"Expected 'Game finished' in /finish response: {[e['content'] for e in info_events]}"
    )
    assert session.exited, "Session should be exited after /finish"


@pytest.mark.skip(reason="pending evaluation fixes")
async def test_per_turn_evaluation(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Evaluation should run after each turn and results displayed to player."""
    ...


@pytest.mark.skip(reason="pending evaluation fixes")
async def test_player_triggered_evals_disabled_by_default(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Player-triggered evaluations should be disabled by default."""
    ...


@pytest.mark.skip(reason="pending evaluation fixes")
async def test_evaluation_shown_at_end(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Evaluation results should be shown to the player after game completion."""
    ...


@pytest.mark.skip(reason="pending run config refactoring")
async def test_overrides_work(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """All documented run config overrides should apply to Foresight."""
    ...
