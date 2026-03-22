"""Unit tests for OpenRouter call behavior in ai_client."""

import asyncio
from typing import Any

import pytest
from dcs_simulation_engine.games import ai_client


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


# ── AtomicValidator tests ─────────────────────────────────────────────


@pytest.mark.unit
def test_atomic_validator_pass() -> None:
    """AtomicValidator returns (True, '') when LLM responds with pass: true."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.AtomicValidator(system_prompt="Check something.")
        passed, reason = asyncio.run(v.validate("some text"))
        assert passed is True
        assert reason == ""
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_atomic_validator_fail() -> None:
    """AtomicValidator returns (False, reason) when LLM responds with pass: false."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "not allowed"}')
    try:
        v = ai_client.AtomicValidator(system_prompt="Check something.")
        passed, reason = asyncio.run(v.validate("some text"))
        assert passed is False
        assert reason == "not allowed"
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_atomic_validator_string_true() -> None:
    """AtomicValidator handles stringified boolean 'true'."""
    ai_client.set_fake_ai_response('{"pass": "true"}')
    try:
        v = ai_client.AtomicValidator(system_prompt="Check something.")
        passed, _reason = asyncio.run(v.validate("some text"))
        assert passed is True
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_atomic_validator_malformed_json() -> None:
    """AtomicValidator defaults to (False, '') on unparseable LLM response."""
    ai_client.set_fake_ai_response("not json at all")
    try:
        v = ai_client.AtomicValidator(system_prompt="Check something.")
        passed, _reason = asyncio.run(v.validate("some text"))
        assert passed is False
    finally:
        ai_client.set_fake_ai_response(None)


# ── RolePlayingLLMValidator tests ────────────────────────────────────


@pytest.mark.unit
def test_roleplaying_validator_schema_pass() -> None:
    """VALID-SCHEMA passes for well-formed updater JSON."""
    result = ai_client.RolePlayingLLMValidator._check_schema('{"type": "ai", "content": "hello"}')
    assert result.passed is True
    assert result.rule == "VALID-SCHEMA"


@pytest.mark.unit
def test_roleplaying_validator_schema_fail_not_json() -> None:
    """VALID-SCHEMA fails for non-JSON text."""
    result = ai_client.RolePlayingLLMValidator._check_schema("not json")
    assert result.passed is False
    assert "not valid JSON" in result.reason


@pytest.mark.unit
def test_roleplaying_validator_schema_fail_wrong_keys() -> None:
    """VALID-SCHEMA fails when required keys are missing."""
    result = ai_client.RolePlayingLLMValidator._check_schema('{"foo": "bar"}')
    assert result.passed is False
    assert "type" in result.reason or "content" in result.reason


@pytest.mark.unit
def test_roleplaying_validator_schema_fail_extra_keys() -> None:
    """VALID-SCHEMA fails when extra keys are present."""
    result = ai_client.RolePlayingLLMValidator._check_schema(
        '{"type": "ai", "content": "hello", "extra": 1}'
    )
    assert result.passed is False
    assert "Extra keys" in result.reason


@pytest.mark.unit
def test_roleplaying_validator_all_pass() -> None:
    """RolePlayingLLMValidator reports passed=True when all rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.RolePlayingLLMValidator.create()
        result = asyncio.run(v.validate('{"type": "ai", "content": "The door creaks open."}'))
        assert result.passed is True
        assert len(result.failed) == 0
        assert len(result.results) == 12  # 1 schema + 11 LLM
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_roleplaying_validator_schema_fail_propagates() -> None:
    """RolePlayingLLMValidator reports passed=False when schema check fails."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.RolePlayingLLMValidator.create()
        result = asyncio.run(v.validate("not valid json at all"))
        assert result.passed is False
        failed_rules = [r.rule for r in result.failed]
        assert "VALID-SCHEMA" in failed_rules
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_roleplaying_validator_llm_fail_propagates() -> None:
    """RolePlayingLLMValidator reports failures from LLM-based validators."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "invented action"}')
    try:
        v = ai_client.RolePlayingLLMValidator.create()
        result = asyncio.run(v.validate('{"type": "ai", "content": "You step back."}'))
        assert result.passed is False
        # Schema passes but all 11 LLM rules fail
        schema_results = [r for r in result.results if r.rule == "VALID-SCHEMA"]
        assert schema_results[0].passed is True
        assert len(result.failed) == 11
    finally:
        ai_client.set_fake_ai_response(None)
