"""Unit tests for gameplay websocket error helpers."""

import pytest
from dcs_simulation_engine.api.routers.play import _send_model_provider_error, _send_replay
from dcs_simulation_engine.dal.base import SessionEventRecord
from dcs_simulation_engine.errors import ModelProviderError

pytestmark = pytest.mark.unit


class _FakeWebSocket:
    def __init__(self) -> None:
        self.frames: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.frames.append(payload)


@pytest.mark.anyio
async def test_send_model_provider_error_frame_preserves_structured_metadata() -> None:
    """Escaped provider errors should be distinguishable from generic engine errors."""
    websocket = _FakeWebSocket()
    error = ModelProviderError(
        provider="openrouter",
        model="openai/gpt-5-mini",
        status_code=402,
        provider_code="402",
        provider_message="This request requires more credits.",
        user_message="Model provider error: OpenRouter needs more credits for openai/gpt-5-mini.",
        retryable=False,
    )

    await _send_model_provider_error(websocket, error)  # type: ignore[arg-type]

    assert websocket.frames == [
        {
            "type": "error",
            "detail": "Model provider error: OpenRouter needs more credits for openai/gpt-5-mini.",
            "failure_type": "model_provider_error",
            "provider": "openrouter",
            "provider_status_code": 402,
            "provider_code": "402",
        }
    ]


@pytest.mark.anyio
async def test_send_replay_preserves_error_metadata() -> None:
    """Replayed persisted errors should keep the same labels as live errors."""
    websocket = _FakeWebSocket()

    class Provider:
        def list_session_events(self, *, session_id: str):
            return [
                SessionEventRecord(
                    session_id=session_id,
                    seq=1,
                    event_id="event-1",
                    event_ts=None,
                    direction="outbound",
                    event_type="error",
                    event_source="system",
                    content="That action was blocked.",
                    data={
                        "failure_type": "player_turn_validation_failed",
                        "retries_remaining": 1,
                    },
                )
            ]

    await _send_replay(websocket, "session-1", Provider(), turns=1)  # type: ignore[arg-type]

    assert websocket.frames[1] == {
        "type": "replay_event",
        "session_id": "session-1",
        "event_type": "error",
        "content": "That action was blocked.",
        "event_id": "event-1",
        "role": "ai",
        "failure_type": "player_turn_validation_failed",
        "retries_remaining": 1,
        "provider": None,
        "provider_status_code": None,
        "provider_code": None,
    }
