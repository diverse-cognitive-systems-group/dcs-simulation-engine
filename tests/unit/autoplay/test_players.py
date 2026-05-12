"""Unit tests for autoplay player adapters."""

import json

import pytest
from autoplay import MODEL_PLAYER_SYSTEM_PROMPT, OpenRouterPlayer, PlayerContext, PlayerTurn
from autoplay import players as players_module
from loguru import logger

pytestmark = pytest.mark.unit


class _FakeResponse:
    def raise_for_status(self) -> None:
        """Pretend the provider accepted the request."""

    def json(self) -> dict:
        """Return one model choice."""
        return {"choices": [{"message": {"content": "I inspect the room."}}]}


class _FakeAsyncClient:
    requests: list[dict] = []

    def __init__(self, *, timeout=None) -> None:
        """Capture the timeout for parity with httpx.AsyncClient."""
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict, json: dict):
        self.requests.append({"url": url, "headers": headers, "json": json, "timeout": self.timeout})
        return _FakeResponse()


@pytest.mark.anyio
async def test_openrouter_prompt_includes_visible_opening_context_and_is_logged(monkeypatch) -> None:
    """OpenRouter prompt payloads should include visible game context and be logged."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    _FakeAsyncClient.requests = []
    monkeypatch.setattr(players_module.httpx, "AsyncClient", _FakeAsyncClient)
    log_messages: list[str] = []
    sink_id = logger.add(log_messages.append, level="INFO", format="{message}")
    player = OpenRouterPlayer(model_id="openai/test-model", timeout=3.0)
    context = PlayerContext(
        run_name="run",
        player_id="player-1",
        model_id=player.model_id,
        assignment={"game_name": "Explore"},
        session_id="session-1",
        session_meta={},
        turns=1,
        history=(
            PlayerTurn(role="server", event_type="info", content="Use /help to see available commands."),
            PlayerTurn(role="simulator", event_type="ai", content="You enter a quiet room."),
        ),
    )

    try:
        response = await player.next_input(context)
    finally:
        logger.remove(sink_id)

    assert response == "I inspect the room."
    assert len(_FakeAsyncClient.requests) == 1
    payload = _FakeAsyncClient.requests[0]["json"]
    assert payload["model"] == "openai/test-model"
    assert payload["messages"][0] == {"role": "system", "content": MODEL_PLAYER_SYSTEM_PROMPT}
    assert "Use /help to see available commands." in payload["messages"][1]["content"]
    assert "You enter a quiet room." in payload["messages"][1]["content"]

    prompt_messages = [message for message in log_messages if "openrouter_prompt" in message]
    assert prompt_messages
    logged = json.loads(prompt_messages[0].partition("openrouter_prompt ")[2])
    assert logged["payload"] == payload
    assert logged["session_id"] == "session-1"
