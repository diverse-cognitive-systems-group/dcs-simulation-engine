"""Functional tests for ExploreGame's end-to-end session flow."""

from typing import Any

import pytest
from dcs_simulation_engine.core.constants import MODEL_PROVIDER_ERROR
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.errors import ModelProviderError
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.games.ai_client import SimulatorComponentResult, SimulatorTurnResult

pytestmark = [pytest.mark.functional, pytest.mark.anyio]


async def _make_session(async_mongo_provider: Any, *, source: str = "unknown") -> SessionManager:
    return await SessionManager.create_async(
        game="explore",
        provider=async_mongo_provider,
        source=source,
        pc_choice="NA",
        npc_choice="FW",
    )


def _failed_turn(message: str) -> SimulatorTurnResult:
    return SimulatorTurnResult(
        ok=False,
        error_message=message,
        updater_result=SimulatorComponentResult(
            name="updater",
            content="",
            ok=False,
            metadata={},
            raw_response='{"type":"error","content":"invalid"}',
        ),
    )


async def test_explore_full_session_flow(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """ExploreGame should remain playable from enter through finish."""
    session = await _make_session(async_mongo_provider)

    assert session is not None
    assert not session.exited
    assert session._events == []

    enter_events = await session.step_async("")
    assert [event["type"] for event in enter_events] == ["info", "ai"]
    assert session.turns == 1
    assert len(session._events) == 2

    first_turn = await session.step_async("I look around")
    assert [event["type"] for event in first_turn] == ["ai"]
    assert first_turn[0]["content"] == "The flatworm moves slowly across the surface."
    assert session.turns == 2

    help_events = await session.step_async("/help")
    assert [event["type"] for event in help_events] == ["info"]
    assert "NA" in help_events[0]["content"]
    assert "FW" in help_events[0]["content"]
    assert session.turns == 2
    assert not session.exited

    abilities_events = await session.step_async("/abilities")
    assert [event["type"] for event in abilities_events] == ["info"]
    assert "Abilities" in abilities_events[0]["content"]
    assert "NA" in abilities_events[0]["content"]
    assert "FW" in abilities_events[0]["content"]
    assert session.turns == 2
    assert not session.exited

    unknown_command_turn = await session.step_async("/unknown gesture")
    assert unknown_command_turn == []
    assert session.turns == 2
    assert not session.exited

    finish_events = await session.step_async("/finish")
    assert [event["type"] for event in finish_events] == ["info"]
    assert session.exited
    assert session.exit_reason == "player finished"


async def test_explore_opening_model_provider_error_is_terminal(
    patch_llm_client, _isolate_db_state, async_mongo_provider
):
    """Provider failures should surface as provider errors, not generic internal server errors."""
    _ = patch_llm_client
    session = await _make_session(async_mongo_provider)

    async def fail_chat(user_input: str | None):
        raise ModelProviderError(
            provider="openrouter",
            model="openai/gpt-5-mini",
            status_code=402,
            provider_code="402",
            provider_message="This request requires more credits.",
            user_message="Model provider error: OpenRouter needs more credits for openai/gpt-5-mini.",
            retryable=False,
        )

    session.game._engine.chat = fail_chat  # type: ignore[method-assign]

    events = await session.step_async("")

    assert [event["type"] for event in events] == ["info", "error"]
    assert events[1]["failure_type"] == MODEL_PROVIDER_ERROR
    assert events[1]["exit_reason"] == MODEL_PROVIDER_ERROR
    assert events[1]["provider"] == "openrouter"
    assert events[1]["provider_status_code"] == 402
    assert session.exited is True
    assert session.exit_reason == MODEL_PROVIDER_ERROR
    assert session.turns == 0


async def test_explore_opening_model_output_contract_error_is_terminal(
    patch_llm_client, _isolate_db_state, async_mongo_provider, monkeypatch: pytest.MonkeyPatch
):
    """Malformed opener output should retry once, then surface as a provider error."""
    _ = patch_llm_client
    session = await _make_session(async_mongo_provider)
    opener_calls = 0

    async def malformed_opener(messages, model):
        nonlocal opener_calls
        _ = messages, model
        opener_calls += 1
        return "not json"

    monkeypatch.setattr(ai_client, "_call_openrouter", malformed_opener)

    events = await session.step_async("")

    assert [event["type"] for event in events] == ["info", "error"]
    assert events[1]["failure_type"] == MODEL_PROVIDER_ERROR
    assert events[1]["exit_reason"] == MODEL_PROVIDER_ERROR
    assert events[1]["provider"] == "openrouter"
    assert events[1]["provider_code"] == "model_output_contract_error"
    assert session.exited is True
    assert session.exit_reason == MODEL_PROVIDER_ERROR
    assert session.turns == 0
    assert opener_calls == 2


async def test_explore_incorrect_input_flow(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """ExploreGame should reject overlong input and exit once retries are exhausted."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")

    session.game._max_input_length = 5
    overlong_events = await session.step_async("too long")

    assert [event["type"] for event in overlong_events] == ["error"]
    assert "maximum length of 5" in overlong_events[0]["content"]
    assert session.turns == 1
    assert not session.exited

    session.game._max_input_length = 350
    session.game._player_retry_budget = 2

    async def _always_fail(user_input: str) -> SimulatorTurnResult:
        return _failed_turn(f"Invalid action: {user_input}")

    session.game._engine.step = _always_fail  # type: ignore[method-assign]

    first_invalid = await session.step_async("bad move")

    assert [event["type"] for event in first_invalid] == ["error"]
    assert "That action was blocked: Invalid action: bad move" in first_invalid[0]["content"]
    assert "Failed attempts remaining: 1 attempt." in first_invalid[0]["content"]
    assert first_invalid[0]["failure_type"] == "player_turn_validation_failed"
    assert first_invalid[0]["retries_remaining"] == 1
    assert not session.exited
    assert session.turns == 1

    second_invalid = await session.step_async("bad move again")

    assert [event["type"] for event in second_invalid] == ["error"]
    assert second_invalid[0]["content"] == "Error: Too many failed attempts. Game over."
    assert second_invalid[0]["failure_type"] == "player_turn_validation_failed"
    assert second_invalid[0]["retries_remaining"] == 0
    assert second_invalid[0]["exit_reason"] == "player_validation_retry_exhausted"
    assert session.exited
    assert session.exit_reason == "player_validation_retry_exhausted"
    assert session.turns == 1


async def test_explore_post_exit_behavior(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """After finishing, SessionManager should return the ended-session message on later input."""
    session = await _make_session(async_mongo_provider)
    await session.step_async("")
    await session.step_async("I move closer")
    await session.step_async("/finish")

    ended_events = await session.step_async("I keep exploring")

    assert session.exited
    assert ended_events == [{"type": "info", "content": "Session has ended. (player finished)"}]


async def test_explore_transcript_filtering_end_to_end(patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Filtered transcript should include only opening and successful gameplay turns."""
    session = await _make_session(async_mongo_provider)

    await session.step_async("")
    await session.step_async("/help")

    session.game._max_input_length = 5
    await session.step_async("too long")
    session.game._max_input_length = 350

    original_step = session.game._engine.step

    async def _fail_once(_user_input: str) -> SimulatorTurnResult:
        return _failed_turn("That action is invalid.")

    session.game._engine.step = _fail_once  # type: ignore[method-assign]
    await session.step_async("bad")
    session.game._engine.step = original_step  # type: ignore[method-assign]

    await session.step_async("I wait")
    await session.step_async("/abilities")
    await session.step_async("/finish")

    transcript = session.game.get_transcript()

    assert "Opening scene:" in transcript
    assert "Player (NA): I wait" in transcript
    assert "Simulator: The flatworm moves slowly across the surface." in transcript
    assert "/help" not in transcript
    assert "/abilities" not in transcript
    assert "too long" not in transcript
    assert "bad" not in transcript
    assert "That action is invalid." not in transcript


@pytest.mark.parametrize("source", ["api", "gui"])
async def test_explore_source_players_can_play(source, patch_llm_client, _isolate_db_state, async_mongo_provider):
    """Explore remains playable for both API and GUI sourced sessions."""
    session = await _make_session(async_mongo_provider, source=source)

    enter_events = await session.step_async("")
    turn_events = await session.step_async("I look around")

    assert [event["type"] for event in enter_events] == ["info", "ai"]
    assert [event["type"] for event in turn_events] == ["ai"]
    assert session.turns == 2
