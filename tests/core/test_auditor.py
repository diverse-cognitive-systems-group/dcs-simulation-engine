"""Tests for the NPC response auditor."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.core.simulation_graph.constants import (
    AUDITOR_NAME,
    MAX_AUDITOR_RETRIES,
    UPDATER_NAME,
    VALIDATOR_NAME,
)
from dcs_simulation_engine.core.simulation_graph.state import make_state
from langchain_core.messages import AIMessage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_runtime(
    *,
    updater_responses: list[str] | None = None,
    auditor_responses: list[str] | None = None,
) -> Any:
    """Build a minimal mock runtime with LLM models that return scripted responses.

    Each model tracks its own call index so responses can differ across retries.
    """

    call_counts: dict[str, int] = {}

    def _make_model(name: str, responses: list[str]) -> MagicMock:
        model = MagicMock()
        call_counts[name] = 0

        def invoke(input: Any, **kwargs: Any) -> AIMessage:
            idx = call_counts[name]
            text = responses[idx % len(responses)]
            call_counts[name] += 1
            return AIMessage(content=text)

        model.invoke = invoke
        return model

    if updater_responses is None:
        updater_responses = ['{"type": "ai", "content": "The creature moves slowly."}']
    if auditor_responses is None:
        auditor_responses = ['{"type": "pass", "content": "Valid response"}']

    models = {
        UPDATER_NAME: _make_model(UPDATER_NAME, updater_responses),
        AUDITOR_NAME: _make_model(AUDITOR_NAME, auditor_responses),
        VALIDATOR_NAME: _make_model(VALIDATOR_NAME, ['{"type": "info", "content": "Valid action"}']),
    }

    runtime = MagicMock()
    runtime.call_counts = call_counts
    runtime.context = {
        "pc": {
            "short_description": "A sighted human",
            "_short_description": "human",
            "long_description": "A typical human.",
            "abilities": {
                "Sensory / Perceptual": ["Can detect light, color, shape, and motion through vision."],
                "Action / Motor": ["Can walk, grasp, and speak."],
            },
        },
        "npc": {
            "short_description": "A blind human",
            "_short_description": "blind-human",
            "long_description": "A human who cannot see.",
            "abilities": {
                "Sensory / Perceptual": [
                    "Can detect pitch, volume, and direction of sound through hearing.",
                    "Cannot detect light, color, shape, or motion through vision.",
                ],
                "Action / Motor": ["Can walk, grasp, and speak."],
            },
        },
        "models": models,
        "additional_validator_rules": "",
        "additional_updater_rules": "",
        "additional_auditor_rules": "",
    }
    return runtime


def _make_state_with_input(content: str = "I wave my hand") -> dict:
    """Create a state dict with user input set."""
    state = make_state()
    state["user_input"] = {"type": "user", "content": content}
    state["lifecycle"] = "UPDATE"
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_auditor_passes_valid_response():
    """When auditor returns 'pass', updater response passes through unchanged."""
    from dcs_simulation_engine.core.simulation_graph.subgraph import updater

    state = _make_state_with_input("I tap the table")
    runtime = _make_mock_runtime(
        updater_responses=['{"type": "ai", "content": "The creature hears the tapping and turns toward the sound."}'],
        auditor_responses=['{"type": "pass", "content": "Valid response"}'],
    )

    result = updater(state, runtime)

    assert "updater_response" in result
    assert result["updater_response"]["type"] == "ai"
    assert "tapping" in result["updater_response"]["content"]
    assert result["auditor_response"]["type"] == "pass"


@pytest.mark.unit
def test_auditor_rejects_then_retry_succeeds():
    """When auditor rejects the first response, updater retries and succeeds."""
    from dcs_simulation_engine.core.simulation_graph.subgraph import updater

    state = _make_state_with_input("I wave my hand silently")
    runtime = _make_mock_runtime(
        updater_responses=[
            # First attempt: NPC "sees" the wave (violation for blind NPC)
            '{"type": "ai", "content": "The creature sees your wave and waves back."}',
            # Second attempt: NPC behaves correctly
            '{"type": "ai", "content": "The creature continues feeling along the wall, unaware of your gesture."}',
        ],
        auditor_responses=[
            # First audit: rejects
            '{"type": "error", "content": "Ability violation: NPC cannot see but responded to a visual stimulus."}',
            # Second audit: passes
            '{"type": "pass", "content": "Valid response"}',
        ],
    )

    result = updater(state, runtime)

    assert result["updater_response"]["type"] == "ai"
    assert "feeling along the wall" in result["updater_response"]["content"]
    assert result["auditor_response"]["type"] == "pass"

    # Verify the updater model was called twice (initial + retry)
    assert runtime.call_counts[UPDATER_NAME] == 2
    assert runtime.call_counts[AUDITOR_NAME] == 2


@pytest.mark.unit
def test_auditor_retry_budget_exhausted():
    """When all retry attempts fail auditing, the last response passes through."""
    from dcs_simulation_engine.core.simulation_graph.subgraph import updater

    state = _make_state_with_input("I wave my hand silently")
    runtime = _make_mock_runtime(
        updater_responses=[
            '{"type": "ai", "content": "The creature sees your wave."}',
            '{"type": "ai", "content": "The creature looks at you."}',
        ],
        auditor_responses=[
            '{"type": "error", "content": "Ability violation: NPC cannot see."}',
            '{"type": "error", "content": "Ability violation: NPC cannot look."}',
        ],
    )

    result = updater(state, runtime)

    # Last response passes through despite violations
    assert result["updater_response"]["type"] == "ai"
    assert result["auditor_response"]["type"] == "error"

    # Verify retry count matches MAX_AUDITOR_RETRIES
    assert runtime.call_counts[UPDATER_NAME] == MAX_AUDITOR_RETRIES
    assert runtime.call_counts[AUDITOR_NAME] == MAX_AUDITOR_RETRIES


@pytest.mark.unit
def test_auditor_skipped_on_updater_error():
    """When the updater itself returns an error, the auditor is not called."""
    from dcs_simulation_engine.core.simulation_graph.subgraph import updater

    state = _make_state_with_input("I wave")
    runtime = _make_mock_runtime(
        updater_responses=['{"type": "error", "content": "LLM failed to generate response."}'],
        auditor_responses=['{"type": "pass", "content": "Valid response"}'],
    )

    result = updater(state, runtime)

    assert result["updater_response"]["type"] == "error"
    # Auditor model should never be called
    assert runtime.call_counts[AUDITOR_NAME] == 0


@pytest.mark.unit
def test_auditor_response_in_state():
    """The auditor_response field should be present in the state after updater runs."""
    state = make_state()
    assert "auditor_response" in state
    assert state["auditor_response"] is None


@pytest.mark.unit
def test_max_auditor_retries_is_positive():
    """Sanity check that MAX_AUDITOR_RETRIES is a reasonable positive integer."""
    assert MAX_AUDITOR_RETRIES >= 1
    assert MAX_AUDITOR_RETRIES <= 5
