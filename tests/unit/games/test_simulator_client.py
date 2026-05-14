"""Unit tests for SimulatorClient behavior."""

import asyncio

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.errors import ModelProviderError
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.games.ai_client import (
    INTERNAL_ERROR,
    PLAYER_TURN_VALIDATION_FAILED,
    SIMULATOR_TURN_VALIDATION_RETRY_EXHAUSTED,
    SimulatorClient,
)
from dcs_simulation_engine.games.prompts import VALID_NPC_ACTION, VALID_PC_ACTION


@pytest.fixture
def pc() -> CharacterRecord:
    """Return a representative player character for SimulatorClient tests."""
    return CharacterRecord(
        hid="PC",
        name="Player",
        short_description="Player short",
        data={
            "abilities": ["can move"],
            "long_description": "Player long",
            "scenarios": ["Room"],
        },
    )


@pytest.fixture
def npc() -> CharacterRecord:
    """Return a representative NPC for SimulatorClient tests."""
    return CharacterRecord(
        hid="NPC",
        name="NPC",
        short_description="NPC short",
        data={
            "abilities": ["can observe"],
            "long_description": "NPC long",
            "scenarios": ["Room"],
        },
    )


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_runs_player_validators_before_updaters(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """SimulatorClient should run player and simulator validators before updating the scene."""
    calls: list[tuple[int, str, str]] = []

    async def fake_call(messages, model):
        role = messages[0]["role"]
        calls.append((len(messages), role, messages[0]["content"]))
        if len(messages) == 1:
            return '{"pass": true}'
        return '{"type": "ai", "content": "resolved"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[VALID_NPC_ACTION],
    )

    result = await client.step("I wave")

    assert result.ok is True
    assert result.simulator_response == "resolved"
    assert len([call for call in calls if call[0] == 1]) == 2
    assert any("RULE: VALID-PC-ACTION" in call[2] for call in calls if call[0] == 1)
    assert any("RULE: VALID-NPC-ACTION" in call[2] for call in calls if call[0] == 1)
    assert any("Produce the next immediate simulator update." in call[2] for call in calls if call[0] > 1)


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_uses_configured_templates(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Configured updater templates should flow through to the OpenRouter prompt."""
    captured_system_prompts: list[str] = []

    async def fake_call(messages, model):
        captured_system_prompts.append(messages[0]["content"])
        if len(messages) == 1:
            return '{"pass": true}'
        return '{"type": "ai", "content": "scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    custom_updater = """CUSTOM UPDATER
Player: {player_action}
Transcript: {transcript}
"""

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        updater_template=custom_updater,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    await client.step("I wave and predict they will retreat")

    updater_prompts = [prompt for prompt in captured_system_prompts if "CUSTOM UPDATER" in prompt]
    assert updater_prompts
    assert "I wave and predict they will retreat" in updater_prompts[0]


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_classifies_player_validator_rejections(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Player validator rejections should be machine-readable as player-caused failures."""

    async def fake_call(messages, model):
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            return '{"pass": false, "reason": "That action exceeds the player character abilities."}'
        return '{"type": "ai", "content": "scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    result = await client.step("I teleport through the wall")

    assert result.ok is False
    assert result.failure_type == PLAYER_TURN_VALIDATION_FAILED
    assert result.error_message == "That action exceeds the player character abilities."


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_retries_once_then_returns_clean_error_after_double_simulator_validation_failure(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """A simulator validation failure should retry once, then surface the clean retry-exhausted message."""
    updater_calls = 0
    simulator_validator_calls = 0

    async def fake_call(messages, model):
        nonlocal updater_calls, simulator_validator_calls
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            prompt = messages[0]["content"]
            if "RULE: VALID-NPC-ACTION" in prompt:
                simulator_validator_calls += 1
                return '{"pass": false, "reason": "Simulator response violated the NPC action rule."}'
            return '{"pass": true, "reason": "ok"}'

        updater_calls += 1
        return '{"type": "ai", "content": "The flatworm teleports through the wall."}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[VALID_NPC_ACTION],
    )

    result = await client.step("I wave")

    assert result.ok is False
    assert result.error_message == "I couldn't produce a valid simulator response. Please retry your action."
    assert result.failure_type == SIMULATOR_TURN_VALIDATION_RETRY_EXHAUSTED
    assert updater_calls == 2
    assert simulator_validator_calls == 2
    assert result.updater_result is not None
    assert result.updater_result.retries_used == 1
    assert len(result.updater_result.validation_failures) == 1


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_surfaces_clean_error_when_player_validator_runtime_fails(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Validator runtime failures should produce the clean player-validation error contract."""

    async def fake_call(messages, model):
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            raise RuntimeError("validator offline")
        return '{"type": "ai", "content": "scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    result = await client.step("I wave")

    assert result.ok is False
    assert result.error_message == "The simulation engine hit an internal problem while validating the action."
    assert result.failure_type == INTERNAL_ERROR


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_surfaces_clean_error_when_updater_runtime_fails(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Updater runtime failures should not be retried as model-output contract failures."""
    updater_calls = 0

    async def fake_call(messages, model):
        nonlocal updater_calls
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            return '{"pass": true, "reason": "ok"}'
        updater_calls += 1
        raise RuntimeError("updater offline")

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    result = await client.step("I wave")

    assert result.ok is False
    assert result.error_message == "The simulation engine hit an internal problem while producing a simulator response."
    assert result.failure_type == INTERNAL_ERROR
    assert updater_calls == 1


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_retries_once_when_updater_output_contract_fails(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Malformed updater output should retry once before succeeding."""
    updater_calls = 0
    updater_messages: list[list[dict[str, str]]] = []

    async def fake_call(messages, model):
        nonlocal updater_calls
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            return '{"pass": true, "reason": "ok"}'
        updater_calls += 1
        updater_messages.append(messages)
        if updater_calls == 1:
            return "not json"
        return '{"type": "ai", "content": "scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    result = await client.step("I wave")

    assert result.ok is True
    assert updater_calls == 2
    assert any("previous updater response" in message["content"] for message in updater_messages[1])


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_surfaces_clean_error_when_updater_output_contract_fails_after_retry(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Malformed updater output should surface as provider failure after retry."""
    updater_calls = 0

    async def fake_call(messages, model):
        nonlocal updater_calls
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            return '{"pass": true}'
        updater_calls += 1
        return '{"type": "ai", "content": null}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    with pytest.raises(ModelProviderError) as excinfo:
        await client.step("I wave")

    assert excinfo.value.provider == "openrouter"
    assert excinfo.value.provider_code == "model_output_contract_error"
    assert "updater" in (excinfo.value.provider_message or "")
    assert updater_calls == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_surfaces_provider_error_when_validator_output_contract_fails_after_retry(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Malformed validator output should surface as provider failure after corrective retry."""
    validator_calls = 0

    async def fake_call(messages, model):
        nonlocal validator_calls
        _ = model
        if "RULE: VALID-PC-ACTION" in messages[0]["content"]:
            validator_calls += 1
            return "not json"
        return '{"type": "ai", "content": "scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[],
    )

    with pytest.raises(ModelProviderError) as excinfo:
        await client.step("I wave")

    assert excinfo.value.provider == "openrouter"
    assert excinfo.value.provider_code == "model_output_contract_error"
    assert "validator" in (excinfo.value.provider_message or "")
    assert validator_calls == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_updater_succeeds_after_one_simulator_validation_failure(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Updater should retry once on validator rejection and succeed if the retry passes."""
    validator_calls = 0

    async def fake_call(messages, model):
        nonlocal validator_calls
        _ = model
        if len(messages) == 1 and "RULE: VALID-NPC-ACTION" in messages[0]["content"]:
            validator_calls += 1
            if validator_calls == 1:
                return '{"pass": false, "reason": "bad npc action"}'
            return '{"pass": true}'
        if len(messages) == 1:
            return '{"pass": true}'
        return '{"type": "ai", "content": "corrected scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[VALID_NPC_ACTION],
    )

    result = await client.step("I wave")

    assert result.ok is True
    assert result.updater_result is not None
    assert result.updater_result.retries_used == 1
    assert validator_calls == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_validators_run_in_parallel_after_updater_and_fast_fail(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Simulator validators should run after updater generation, in parallel, with fast-fail cancellation."""
    slow_validator = "RULE: SLOW-SIM-VALIDATOR\nReturn pass slowly."
    fast_fail_validator = "RULE: FAST-FAIL-SIM-VALIDATOR\nReturn failure quickly."
    updater_completed = False
    slow_started = asyncio.Event()
    slow_cancelled = asyncio.Event()
    active_simulator_validators = 0
    max_active_simulator_validators = 0

    async def fake_call(messages, model):
        nonlocal active_simulator_validators, max_active_simulator_validators, updater_completed
        _ = model
        if len(messages) > 1:
            updater_completed = True
            return '{"type": "ai", "content": "scene"}'

        prompt = messages[0]["content"]
        if "RULE: SLOW-SIM-VALIDATOR" in prompt or "RULE: FAST-FAIL-SIM-VALIDATOR" in prompt:
            assert updater_completed is True
            active_simulator_validators += 1
            max_active_simulator_validators = max(max_active_simulator_validators, active_simulator_validators)
            try:
                if "RULE: SLOW-SIM-VALIDATOR" in prompt:
                    slow_started.set()
                    await asyncio.sleep(60)
                    return '{"pass": true}'
                await slow_started.wait()
                return '{"pass": false, "reason": "fast simulator failure"}'
            except asyncio.CancelledError:
                slow_cancelled.set()
                raise
            finally:
                active_simulator_validators -= 1

        return '{"pass": true}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        player_turn_validators=[VALID_PC_ACTION],
        simulator_turn_validators=[slow_validator, fast_fail_validator],
    )

    result = await client.step("I wave")

    assert result.ok is False
    assert result.failure_type == SIMULATOR_TURN_VALIDATION_RETRY_EXHAUSTED
    assert max_active_simulator_validators == 2
    assert slow_cancelled.is_set()
    assert result.updater_result is not None
    assert result.updater_result.validation_failures[0].message == "fast simulator failure"


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_excludes_prior_opening_scenes_from_later_openers(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Later opener prompts should tell the model not to reuse earlier scenes."""
    captured_prompts: list[str] = []
    responses = [
        '{"type": "ai", "content": "You enter a new space. In this space, a quiet lab bench waits."}',
        '{"type": "ai", "content": "You enter a new space. In this space, a crowded loading dock blocks the path."}',
    ]

    async def fake_call(messages, model):
        _ = model
        captured_prompts.append(messages[0]["content"])
        return responses.pop(0)

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(pc=pc, npc=npc)

    await client.chat(None)
    await client.chat(None)

    assert "Scene Exclusion Instructions" not in captured_prompts[0]
    assert "Scene Exclusion Instructions" in captured_prompts[1]
    assert "a quiet lab bench waits" in captured_prompts[1]
    assert client._opening_scenes == [
        "You enter a new space. In this space, a quiet lab bench waits.",
        "You enter a new space. In this space, a crowded loading dock blocks the path.",
    ]


@pytest.mark.unit
def test_simulator_client_state_round_trip_preserves_resume_context(pc: CharacterRecord, npc: CharacterRecord) -> None:
    """SimulatorClient should persist all mutable prompt context needed for resume."""
    client = SimulatorClient(pc=pc, npc=npc)
    client._history = ["Opening scene: A quiet room.", "Player (PC): I wave."]
    client._transcript_events = ["Opening scene: A quiet room.", "Player (PC): I wave.", "Simulator: The NPC nods."]
    client._opening_metadata = {"shared_goal": "Calmly solve the puzzle."}
    client._opening_scenes = ["A quiet room."]

    snapshot = client.export_state()

    restored = SimulatorClient(pc=pc, npc=npc)
    restored.import_state(snapshot)

    assert restored.export_state() == snapshot
    assert restored._history == client._history
    assert restored._transcript_events == client._transcript_events
    assert restored._opening_metadata == client._opening_metadata
    assert restored._opening_scenes == client._opening_scenes


@pytest.mark.unit
def test_simulator_client_import_state_derives_opening_scenes_from_legacy_history(
    pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Older snapshots without opening_scenes should still preserve scene avoidance after resume."""
    client = SimulatorClient(pc=pc, npc=npc)

    client.import_state(
        {
            "history": [
                "Opening scene: A quiet room.",
                "Player (PC): I wave.",
                "Simulator: The NPC nods.",
                "Opening scene: A busy hallway.",
            ],
            "transcript_events": [
                "Opening scene: A quiet room.",
                "Player (PC): I wave.",
                "Simulator: The NPC nods.",
                "Opening scene: A busy hallway.",
            ],
            "opening_metadata": {},
        }
    )

    assert client._opening_scenes == ["A quiet room.", "A busy hallway."]
