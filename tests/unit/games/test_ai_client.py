"""Unit tests for OpenRouter call behavior in ai_client."""

import asyncio
from typing import Any

import httpx
import pytest
from dcs_simulation_engine.errors import ModelOutputContractError, ModelProviderError
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.games.ai_client import ScorerClient, _extract_response_metadata


@pytest.mark.unit
def test_call_openrouter_returns_fake_response_without_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configured fake response should short-circuit before any HTTP client use."""
    fake_text = '{"type":"ai","content":"from fake"}'
    ai_client.set_fake_ai_response(fake_text)

    class ShouldNotConstruct:
        """Fails if AsyncClient is instantiated in fake-response mode."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("httpx.AsyncClient should not be constructed when fake response is set")

    monkeypatch.setattr(ai_client.httpx, "AsyncClient", ShouldNotConstruct)

    try:
        result = asyncio.run(ai_client._call_openrouter(messages=[{"role": "user", "content": "hi"}], model="x"))
        assert result == fake_text
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_call_openrouter_uses_http_when_fake_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When fake response is disabled, _call_openrouter should use HTTP response content."""
    ai_client.set_fake_ai_response(None)
    monkeypatch.setattr(ai_client, "_get_api_key", lambda: "test-key")

    state = {"post_called": False}

    class FakeResponse:
        """Minimal fake response for ai_client._call_openrouter."""

        is_error = False
        status_code = 200
        text = ""
        request = object()
        response = object()

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "real-http-result"}}]}

    class FakeAsyncClient:
        """Async context manager stub for httpx.AsyncClient."""

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
            state["post_called"] = True
            assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
            assert kwargs["json"]["model"] == "openai/gpt-5-mini"
            timeout = kwargs["timeout"]
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.connect == 10.0
            assert timeout.read == 300.0
            assert timeout.write == 30.0
            assert timeout.pool == 10.0
            return FakeResponse()

    monkeypatch.setattr(ai_client.httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        ai_client._call_openrouter(
            messages=[{"role": "system", "content": "go"}],
            model="openai/gpt-5-mini",
        )
    )

    assert state["post_called"] is True
    assert result == "real-http-result"


@pytest.mark.unit
def test_call_openrouter_timeout_allows_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter read timeout should be configurable for longer reasoning models."""
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "180")

    timeout = ai_client._openrouter_timeout()

    assert timeout.connect == 10.0
    assert timeout.read == 180.0
    assert timeout.write == 30.0
    assert timeout.pool == 10.0


@pytest.mark.unit
def test_call_openrouter_raises_sanitized_model_provider_error_for_402(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenRouter credit errors should become structured provider errors without leaking raw payload IDs."""
    ai_client.set_fake_ai_response(None)
    monkeypatch.setattr(ai_client, "_get_api_key", lambda: "test-key")

    class FakeResponse:
        is_error = True
        status_code = 402
        text = (
            '{"error":{"message":"This request requires more credits, or fewer max_tokens.",'
            '"code":402},"user_id":"user_should_not_leak"}'
        )
        request = object()

        def json(self) -> dict[str, Any]:
            return {
                "error": {
                    "message": "This request requires more credits, or fewer max_tokens.",
                    "code": 402,
                },
                "user_id": "user_should_not_leak",
            }

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(ai_client.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(ModelProviderError) as exc_info:
        asyncio.run(
            ai_client._call_openrouter(
                messages=[{"role": "system", "content": "go"}],
                model="openai/gpt-5-mini",
            )
        )

    exc = exc_info.value
    assert exc.provider == "openrouter"
    assert exc.model == "openai/gpt-5-mini"
    assert exc.status_code == 402
    assert exc.provider_code == "402"
    assert exc.retryable is False
    assert "OpenRouter needs more credits for openai/gpt-5-mini" in exc.user_message
    assert "user_should_not_leak" not in exc.user_message


@pytest.mark.unit
def test_call_openrouter_rejects_null_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Null provider content is a model-output contract failure, not a local AttributeError."""
    ai_client.set_fake_ai_response(None)
    monkeypatch.setattr(ai_client, "_get_api_key", lambda: "test-key")

    class FakeResponse:
        is_error = False
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": None}}]}

    class FakeAsyncClient:
        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setattr(ai_client.httpx, "AsyncClient", FakeAsyncClient)

    with pytest.raises(ModelOutputContractError) as exc_info:
        asyncio.run(
            ai_client._call_openrouter(
                messages=[{"role": "system", "content": "go"}],
                model="openai/gpt-5-mini",
            )
        )

    assert exc_info.value.component == "chat completion"
    assert exc_info.value.detail == "assistant message content must be a string"


@pytest.mark.unit
def test_validate_openrouter_configuration_raises_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Server startup should fail fast when OPENROUTER_API_KEY is missing."""
    ai_client.set_fake_ai_response(None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY is required"):
        ai_client.validate_openrouter_configuration()


@pytest.mark.unit
def test_validate_openrouter_configuration_allows_fake_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fake mode bypasses the OPENROUTER_API_KEY startup requirement."""
    ai_client.set_fake_ai_response('{"type":"ai","content":"fake"}')
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    try:
        ai_client.validate_openrouter_configuration()
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_openrouter_with_retry_succeeds_on_second_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry wrapper should recover from a transient failure on the first attempt."""
    calls = 0

    async def fake_call(messages, model):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("transient failure")
        return "ok"

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)
    result = await ai_client._call_openrouter_with_retry([], "model")
    assert result == "ok"
    assert calls == 2


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_openrouter_with_retry_raises_after_two_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry wrapper should convert exhausted transport failures into provider errors."""
    calls = 0

    async def fake_call(messages, model):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("persistent failure")

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)
    with pytest.raises(ModelProviderError) as exc_info:
        await ai_client._call_openrouter_with_retry([], "model")
    assert calls == 2
    assert exc_info.value.provider == "openrouter"
    assert exc_info.value.model == "model"
    assert exc_info.value.provider_code == "ConnectError"
    assert exc_info.value.provider_message == "persistent failure"


@pytest.mark.unit
@pytest.mark.anyio
async def test_call_openrouter_with_retry_does_not_retry_nonretryable_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider/account errors such as 402 should surface immediately."""
    calls = 0

    async def fake_call(messages, model):
        nonlocal calls
        calls += 1
        raise ModelProviderError(
            provider="openrouter",
            model=model,
            status_code=402,
            provider_code="402",
            provider_message="This request requires more credits.",
            user_message="Model provider error: OpenRouter needs more credits.",
            retryable=False,
        )

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)
    with pytest.raises(ModelProviderError):
        await ai_client._call_openrouter_with_retry([], "model")
    assert calls == 1


@pytest.mark.unit
@pytest.mark.anyio
async def test_scorer_retries_once_when_output_contract_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed scorer output should get one corrective retry before succeeding."""
    calls: list[list[dict[str, str]]] = []

    async def fake_call(messages, model):
        _ = model
        calls.append(messages)
        if len(calls) == 1:
            return None
        return '{"tier": 2, "score": 75, "reasoning": "clear"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    result = await ScorerClient(model="test-model").score(prompt="Score this", transcript="Transcript")

    assert result.evaluation == {"tier": 2, "score": 75, "reasoning": "clear"}
    assert len(calls) == 2
    assert "previous scorer response" in calls[1][0]["content"]


@pytest.mark.unit
@pytest.mark.anyio
async def test_scorer_surfaces_provider_error_when_output_contract_fails_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated malformed scorer output should become a diagnostic provider error."""

    async def fake_call(messages, model):
        _ = messages, model
        return '{"tier": null, "score": 75, "reasoning": "clear"}'

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    with pytest.raises(ModelProviderError) as exc_info:
        await ScorerClient(model="test-model").score(prompt="Score this", transcript="Transcript")

    assert exc_info.value.provider == "openrouter"
    assert exc_info.value.provider_code == "model_output_contract_error"
    assert exc_info.value.provider_message == "scorer: Invalid inference evaluation payload: {'tier': None, 'score': 75, 'reasoning': 'clear'}"


@pytest.mark.unit
@pytest.mark.anyio
async def test_scorer_surfaces_provider_error_when_invalid_json_after_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated invalid scorer JSON should become a diagnostic provider error."""
    calls = 0

    async def fake_call(messages, model):
        nonlocal calls
        _ = messages, model
        calls += 1
        return "not json"

    monkeypatch.setattr(ai_client, "_call_openrouter", fake_call)

    with pytest.raises(ModelProviderError) as exc_info:
        await ScorerClient(model="test-model").score(prompt="Score this", transcript="Transcript")

    assert calls == 2
    assert exc_info.value.provider == "openrouter"
    assert exc_info.value.provider_code == "model_output_contract_error"
    assert exc_info.value.provider_message == "scorer: response was not valid JSON"


@pytest.mark.unit
def test_extract_response_metadata_prefers_metadata_object() -> None:
    """Metadata payload should win over legacy duplicated top-level keys."""
    payload = {"type": "ai", "content": "scene", "metadata": {"shared_goal": "to repair the door"}, "shared_goal": "legacy"}

    assert _extract_response_metadata(payload) == {"shared_goal": "to repair the door"}


@pytest.mark.unit
def test_extract_response_metadata_falls_back_to_extra_top_level_keys() -> None:
    """Extra top-level keys should be treated as metadata when no object is present."""
    payload = {"type": "ai", "content": "scene", "shared_goal": "to repair the door"}

    assert _extract_response_metadata(payload) == {"shared_goal": "to repair the door"}
