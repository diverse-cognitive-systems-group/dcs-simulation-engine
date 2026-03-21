"""Unit tests for Infer Intent evaluation reconstruction helpers."""

from datetime import datetime, timezone

import pytest
from dcs_simulation_engine.api.infer_intent_evaluation import (
    InferIntentEvaluationUnavailableError,
    extract_infer_intent_scoring_inputs,
)
from dcs_simulation_engine.dal.base import SessionEventRecord
from dcs_simulation_engine.dal.mongo.const import MongoColumns


def _event(
    *,
    seq: int,
    direction: str,
    event_type: str,
    event_source: str,
    content: str,
    data: dict | None = None,
) -> SessionEventRecord:
    return SessionEventRecord(
        session_id="session-1",
        seq=seq,
        event_id=f"evt-{seq}",
        event_ts=datetime.now(timezone.utc),
        direction=direction,
        event_type=event_type,
        event_source=event_source,
        content=content,
        data=data or {MongoColumns.VISIBLE_TO_USER: True},
    )


@pytest.mark.unit
def test_extract_infer_intent_scoring_inputs_uses_only_gameplay_before_guess() -> None:
    """Transcript reconstruction ignores commands, hidden events, and post-guess feedback."""
    events = [
        _event(
            seq=9,
            direction="internal",
            event_type="llm_eval",
            event_source="system",
            content='{"tier": 3, "score": 92, "reasoning": "cached"}',
            data={MongoColumns.VISIBLE_TO_USER: False},
        ),
        _event(
            seq=4,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="It glides toward the crumb.",
        ),
        _event(
            seq=1,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="A pale creature presses into the shade.",
        ),
        _event(
            seq=6,
            direction="outbound",
            event_type="command",
            event_source="system",
            content="What do you think the NPC's goal or intention was?",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "guess"},
        ),
        _event(
            seq=3,
            direction="outbound",
            event_type="command",
            event_source="system",
            content="Help text",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "help"},
        ),
        _event(
            seq=2,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="I place a crumb nearby.",
        ),
        _event(
            seq=5,
            direction="inbound",
            event_type="command",
            event_source="user",
            content="/guess",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "guess"},
        ),
        _event(
            seq=7,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="It is trying to find food while staying safe.",
        ),
        _event(
            seq=8,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="No additional feedback.",
        ),
    ]

    transcript, guess = extract_infer_intent_scoring_inputs(events)

    assert transcript == "\n".join(
        [
            "NPC: A pale creature presses into the shade.",
            "Player: I place a crumb nearby.",
            "NPC: It glides toward the crumb.",
        ]
    )
    assert guess == "It is trying to find food while staying safe."


@pytest.mark.unit
def test_extract_infer_intent_scoring_inputs_requires_saved_guess_command() -> None:
    """A completed evaluation cannot be reconstructed without the saved /guess command."""
    events = [
        _event(
            seq=1,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="The creature remains motionless.",
        ),
        _event(
            seq=2,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="I wait and observe.",
        ),
    ]

    with pytest.raises(InferIntentEvaluationUnavailableError, match="no guess was saved"):
        extract_infer_intent_scoring_inputs(events)
