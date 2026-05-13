"""Unit tests for gameplay websocket error helpers."""

import pytest
from dcs_simulation_engine.api.routers.play import _send_model_provider_error
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
