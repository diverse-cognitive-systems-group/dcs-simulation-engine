"""Unit tests for SimulatorClient behavior."""

import pytest
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.games.ai_client import SimulatorClient


@pytest.fixture
def pc() -> CharacterRecord:
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
async def test_simulator_client_runs_player_validators_before_updaters(monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord) -> None:
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
        scene_updater_name="default",
        character_updater_name="goal-aligned",
        player_validator_names=["valid-action"],
        simulator_validator_names=["invented-pc-action"],
    )

    valid, reply = await client.step("I wave")

    assert valid is True
    assert reply == "resolved"
    assert calls[0][1] == "system"
    assert "RULE: VALID-ACTION" in calls[0][2]
    assert len([call for call in calls if call[0] == 1]) == 2
    assert len([call for call in calls if call[0] == 1 and "invented" in call[2].lower()]) == 1
    assert len([call for call in calls if call[0] > 1 and "Goal Aligned Response" in call[2]]) >= 1


@pytest.mark.unit
@pytest.mark.anyio
async def test_simulator_client_uses_configured_prompt_names(monkeypatch: pytest.MonkeyPatch, pc: CharacterRecord, npc: CharacterRecord) -> None:
    async def fake_call(messages, model):
        if len(messages) == 1:
            return '{"type": "info", "content": "ok"}'
        return '{"type": "ai", "content": "scene"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    client = SimulatorClient(
        pc=pc,
        npc=npc,
        scene_updater_name="default",
        character_updater_name="ignore-predictions",
        player_validator_names=["valid-action"],
        simulator_validator_names=[],
    )

    await client.step("I wave and predict they will retreat")

    assert client._character_updater_name == "ignore-predictions"
    assert "IGNORE PREDICTIONS" in client._character_system_prompt
