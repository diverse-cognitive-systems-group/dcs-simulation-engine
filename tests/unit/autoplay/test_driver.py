"""Unit tests for the autoplay driver."""

import httpx
import pytest
from autoplay.driver import AutoplayHTTPStatusError, PlayerHarness
from autoplay.players import ScriptedPlayer

pytestmark = pytest.mark.unit


@pytest.mark.anyio
async def test_request_json_raises_structured_http_status_error() -> None:
    """HTTP API failures should be readable in autoplay output."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "OpenRouter is unavailable"}, request=request)

    harness = PlayerHarness(base_url="http://test", player=ScriptedPlayer())

    async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(AutoplayHTTPStatusError) as exc_info:
            await harness._request_json(client, "POST", "/api/run/sessions")

    exc = exc_info.value
    assert exc.method == "POST"
    assert exc.path == "/api/run/sessions"
    assert exc.status_code == 503
    assert exc.detail == "OpenRouter is unavailable"
    assert str(exc) == "HTTP 503 POST /api/run/sessions: OpenRouter is unavailable"
