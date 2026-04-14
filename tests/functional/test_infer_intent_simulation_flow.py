"""Functional tests for infer-intent game simulation flow with mocked LLMs.

This test suite validates the infer-intent game's unique mechanics:
1. PC is fixed to NA, NPC excludes NA
2. /predict-intent command triggers a 2-step completion form (goal inference + feedback)
3. /help command handler
4. Goal-aligned NPC responses
5. Completion form collects goal_inference and other_feedback, then exits

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

TEST_PLAYER_ID = ObjectId()


@pytest.fixture(autouse=True)
def seed_consenting_player(_isolate_db_state, async_mongo_provider):
    """Seed a player with consent signature for infer-intent game access."""
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


INFER_INTENT_TEST_INPUTS = [
    "I look at the creature",
    "I wave my hand",
    "I move closer to observe",
    "I make a gentle sound",
    "I stay still and watch",
]


async def test_infer_intent_initialization(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test infer-intent game initializes correctly with SessionManager."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    assert not session.exited, "Session should not be exited initially"
    assert session._events == [], "Initial events should be empty"


async def test_infer_intent_enter_welcome_message(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test ENTER step produces welcome message and AI opening."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    enter_events = await session.step_async("")

    info_events = [e for e in enter_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected welcome message with type 'info'"

    assert not session.exited, "Session should not be exited after ENTER"


async def test_infer_intent_predict_intent_command(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /predict-intent command triggers goal-inference question."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I look around")

    guess_events = await session.step_async("/predict-intent")

    info_events = [e for e in guess_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event asking for goal inference"
    assert not session.exited, "Session should not exit after /predict-intent"


async def test_infer_intent_help_command(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help command returns game instructions."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")

    help_events = await session.step_async("/help")

    info_events = [e for e in help_events if e.get("type") == "info"]
    assert len(info_events) > 0, "Expected info event from /help command"
    assert not session.exited, "Session should remain active after /help"


async def test_infer_intent_simulation_turns(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test multi-turn simulation accumulates events correctly."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    turns_after_enter = session.turns

    for idx, user_input in enumerate(INFER_INTENT_TEST_INPUTS):
        turn_num = idx + 1
        prev_event_count = len(session._events)

        events = await session.step_async(user_input)

        ai_events = [e for e in events if e.get("type") == "ai"]
        assert len(ai_events) > 0, f"Turn {turn_num}: Expected AI response event"

        assert len(session._events) > prev_event_count, f"Turn {turn_num}: _events should grow after each step"

    assert not session.exited, "Session should still be active"
    assert session.turns == turns_after_enter + len(INFER_INTENT_TEST_INPUTS)


async def test_infer_intent_completion_form(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test 2-step completion form: /predict-intent -> goal inference -> other feedback -> exit."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I observe the creature")

    guess_events = await session.step_async("/predict-intent")
    assert any(e["type"] == "info" for e in guess_events), "Expected info event from /predict-intent"
    assert not session.exited

    inference_events = await session.step_async("The creature is trying to find food.")
    assert any(e["type"] == "info" for e in inference_events), "Expected follow-up question"
    assert not session.exited, "Session should not exit after first answer"
    assert session.game.goal_inference == "The creature is trying to find food."

    confidence_events = await session.step_async("Interesting behavior overall.")
    assert any(e["type"] == "info" for e in confidence_events), "Expected completion confirmation"
    assert session.exited, "Session should exit after second answer"
    assert session.game.goal_inference_confidence == "Interesting behavior overall."
    assert session.game.evaluation == {}, "Evaluation should not be populated during gameplay"


async def test_infer_intent_exit_and_save(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test infer-intent game sessions can be exited and saved."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )

    await session.step_async("")
    await session.step_async("I wave my hand")
    await session.step_async("I look around")

    await session.exit_async("test complete")
    assert session.exited, "Session should be exited after exit()"

    session.save()


async def test_help_hides_npc_details(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test /help shows NPC hid but does not reveal NPC description."""
    session = await SessionManager.create_async(
        game="Infer Intent",
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
        game="Infer Intent",
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


async def test_additional_updater_rule_present_in_prompt(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Test that the 'Goal Aligned Response' updater rule appears in the system prompt."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")  # ENTER initialises the updater

    assert "Goal Aligned Response" in session.game._engine._updater._system_prompt, (
        "Expected 'Goal Aligned Response' rule in InferIntent updater system prompt"
    )


async def test_default_post_play_form_present(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Infer Intent post-play: /predict-intent → goal answer → confidence → FINISH_CONTENT."""
    session = await SessionManager.create_async(
        game="Infer Intent",
        provider=async_mongo_provider,
        pc_choice="NA",
        npc_choice="FW",
        player_id=str(TEST_PLAYER_ID),
    )
    await session.step_async("")
    await session.step_async("I observe the creature")

    predict_events = await session.step_async("/predict-intent")
    assert any(e["type"] == "info" for e in predict_events), "Expected goal inference question"
    assert not session.exited

    goal_events = await session.step_async("The creature is seeking food.")
    assert any(e["type"] == "info" for e in goal_events), "Expected confidence question"
    assert not session.exited

    confidence_events = await session.step_async("Very confident.")
    info_events = [e for e in confidence_events if e.get("type") == "info"]
    assert any("Game finished" in e["content"] for e in info_events), (
        f"Expected 'Game finished' after confidence answer: {[e['content'] for e in info_events]}"
    )
    assert session.exited


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
    """All documented run config overrides should apply to Infer Intent."""
    ...
