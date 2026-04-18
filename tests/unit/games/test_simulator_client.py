"""Unit tests for SimulatorClient behavior."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.games.ai_client import SimulatorClient
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
            return '{"type": "info", "content": "ok"}'
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
            return '{"type": "info", "content": "ok"}'
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
    assert result.error_message == "I couldn't validate your action just now (validator offline). Please try again."


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_surfaces_clean_error_when_updater_runtime_fails_without_retry(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Updater runtime failures should surface the clean simulator-turn error without retrying."""
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
    assert result.error_message == "I couldn't produce a simulator response just now (updater offline). Please try again."
    assert updater_calls == 1


@pytest.mark.xfail(strict=False, reason="SimulatorClient retries simulator validation failures, not updater LLM/runtime failures.")
@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_retries_once_when_updater_llm_call_fails(
    monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord
) -> None:
    """Desired future behavior: retry one updater LLM failure before surfacing the clean error."""
    updater_calls = 0

    async def fake_call(messages, model):
        nonlocal updater_calls
        _ = model
        if len(messages) == 1 and messages[0]["role"] == "system":
            return '{"pass": true, "reason": "ok"}'
        updater_calls += 1
        if updater_calls == 1:
            raise RuntimeError("transient updater failure")
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
