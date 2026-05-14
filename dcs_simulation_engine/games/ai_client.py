"""Async AI client."""
# ruff: noqa: E501  — prompt strings are intentionally long prose

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, NamedTuple

import httpx
from dcs_simulation_engine.core.constants import (
    INTERNAL_ERROR,
    OPENROUTER_BASE_URL,
    PLAYER_TURN_VALIDATION_FAILED,
    SIMULATOR_TURN_VALIDATION_RETRY_EXHAUSTED,
)
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.errors import ModelOutputContractError, ModelProviderError
from dcs_simulation_engine.games.const import (
    DEFAULT_MODEL,
    DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS,
    DEFAULT_OPENROUTER_TIMEOUT_SECONDS,
    DEFAULT_RAW_RESPONSE_LOG_CHARS,
    MODEL_OUTPUT_PROVIDER_CODE,
    OPENROUTER_PROVIDER,
)
from dcs_simulation_engine.games.prompts import (
    DEFAULT_PLAYER_TURN_VALIDATORS,
    DEFAULT_SIMULATOR_TURN_VALIDATORS,
    OPENER,
    UPDATER,
    build_opener_prompt,
    build_player_validator_prompt,
    build_simulator_validator_prompt,
    build_updater_prompt,
)
from loguru import logger

if TYPE_CHECKING:
    from dcs_simulation_engine.core.session_event_recorder import ValidationEventRecorder

_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"
_FAKE_AI_RESPONSE: str | None = None


def set_fake_ai_response(value: str | None) -> None:
    """Set a process-local override returned by _call_openrouter when configured."""
    global _FAKE_AI_RESPONSE
    _FAKE_AI_RESPONSE = value


def validate_openrouter_configuration() -> None:
    """Validate runtime configuration needed for live OpenRouter requests."""
    if _FAKE_AI_RESPONSE is not None:
        return

    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required to start the server. Set it in the environment, or use --fake-ai-response for local mock mode."
        )


def _get_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is missing.")
    return key


def _openrouter_timeout() -> httpx.Timeout:
    """Return the OpenRouter timeout, allowing long non-streaming reasoning calls."""
    timeout_seconds = float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", DEFAULT_OPENROUTER_TIMEOUT_SECONDS))
    return httpx.Timeout(
        connect=10.0,
        read=timeout_seconds,
        write=30.0,
        pool=10.0,
    )


def _provider_display_name(provider: str) -> str:
    if provider == OPENROUTER_PROVIDER:
        return "OpenRouter"
    return provider.title()


def _clean_provider_message(message: Any) -> str:
    return " ".join(str(message or "").split())


def _raw_response_log_limit() -> int:
    """Return the maximum raw model response chars to persist in diagnostics."""
    raw_value = os.getenv("DCS_MODEL_RAW_RESPONSE_LOG_CHARS", "").strip()
    if not raw_value:
        return DEFAULT_RAW_RESPONSE_LOG_CHARS
    try:
        return max(0, int(raw_value))
    except ValueError:
        return DEFAULT_RAW_RESPONSE_LOG_CHARS


def _raw_response_detail(raw_response: str | None) -> dict[str, Any]:
    """Return raw response diagnostics without letting one log row grow unbounded."""
    raw = raw_response or ""
    limit = _raw_response_log_limit()
    return {
        "raw_response": raw[:limit],
        "raw_response_chars": len(raw),
        "raw_response_truncated": len(raw) > limit,
        "raw_response_log_limit": limit,
    }


def _model_response_summary(raw_response: str | None) -> dict[str, Any]:
    """Extract searchable metadata from common model response payloads."""
    if not raw_response:
        return {"raw_response_format": "empty"}
    try:
        payload = json.loads(raw_response)
    except json.JSONDecodeError:
        return {"raw_response_format": "text"}
    if not isinstance(payload, dict):
        return {"raw_response_format": type(payload).__name__}

    summary: dict[str, Any] = {
        "raw_response_format": "json",
        "response_id": payload.get("id"),
        "object": payload.get("object"),
        "created": payload.get("created"),
        "model": payload.get("model"),
        "provider": payload.get("provider"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "service_tier": payload.get("service_tier"),
    }
    if "usage" in payload:
        summary["usage"] = payload.get("usage")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        summary["choices_count"] = len(choices) if isinstance(choices, list) else 0
        return summary

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        summary["first_choice_type"] = type(first_choice).__name__
        return summary

    summary.update(
        {
            "choices_count": len(choices),
            "choice_index": first_choice.get("index"),
            "finish_reason": first_choice.get("finish_reason"),
            "native_finish_reason": first_choice.get("native_finish_reason"),
        }
    )
    message = first_choice.get("message")
    if not isinstance(message, dict):
        summary["message_type"] = type(message).__name__
        return summary

    content = message.get("content")
    reasoning = message.get("reasoning")
    reasoning_details = message.get("reasoning_details")
    summary.update(
        {
            "message_role": message.get("role"),
            "message_content_type": type(content).__name__,
            "message_content_is_null": content is None,
            "message_content_chars": len(content) if isinstance(content, str) else None,
            "message_refusal_is_null": message.get("refusal") is None,
            "message_has_reasoning": reasoning is not None,
            "message_reasoning_chars": len(reasoning) if isinstance(reasoning, str) else None,
            "message_reasoning_details_count": len(reasoning_details) if isinstance(reasoning_details, list) else None,
        }
    )
    if isinstance(reasoning_details, list):
        summary["message_reasoning_detail_types"] = [
            item.get("type") if isinstance(item, dict) else type(item).__name__ for item in reasoning_details[:10]
        ]
    return summary


def _contract_failure_detail(
    exc: ModelOutputContractError,
    *,
    operation: str,
    attempt: int,
    will_retry: bool,
) -> dict[str, Any]:
    """Build structured diagnostics for persisted model-output contract logs."""
    detail = {
        "operation": operation,
        "component": exc.component,
        "model": exc.model,
        "contract_detail": exc.detail,
        "attempt": attempt,
        "will_retry": will_retry,
        "retry_exhausted": not will_retry,
        "model_response": _model_response_summary(exc.raw_response),
    }
    detail.update(_raw_response_detail(exc.raw_response))
    return detail


def _log_model_output_contract_failure(
    exc: ModelOutputContractError,
    *,
    operation: str,
    attempt: int,
    will_retry: bool,
) -> None:
    """Persist a concise contract failure message with full structured diagnostics."""
    detail = _contract_failure_detail(exc, operation=operation, attempt=attempt, will_retry=will_retry)
    model_response = detail["model_response"]
    log = logger.bind(detail=detail, throttle=False)
    message = (
        "Model output contract failed: operation={} component={} model={} attempt={} "
        "will_retry={} detail={} response_id={} finish_reason={} native_finish_reason={}"
    )
    args = (
        operation,
        exc.component,
        exc.model,
        attempt,
        will_retry,
        exc.detail,
        model_response.get("response_id"),
        model_response.get("finish_reason"),
        model_response.get("native_finish_reason"),
    )
    if will_retry:
        log.warning(message, *args)
    else:
        log.error(message, *args)


def _model_output_provider_error(
    exc: ModelOutputContractError,
    *,
    operation: str = "model_output",
    attempt: int = 2,
) -> ModelProviderError:
    """Convert exhausted model-output contract failures into provider-level failures."""
    provider_message = f"{exc.component}: {exc.detail}"
    _log_model_output_contract_failure(
        exc,
        operation=operation,
        attempt=attempt,
        will_retry=False,
    )
    return ModelProviderError(
        provider=OPENROUTER_PROVIDER,
        model=exc.model,
        provider_code=MODEL_OUTPUT_PROVIDER_CODE,
        provider_message=provider_message,
        user_message=(
            f"Model provider error: {_provider_display_name(OPENROUTER_PROVIDER)} returned unusable output "
            f"for {exc.model}. The game host needs to check this out before you can continue."
        ),
        retryable=False,
    )


def _contract_retry_instruction(component: str, exc: ModelOutputContractError) -> str:
    """Build corrective feedback for one model-output contract retry."""
    if component == "validator":
        schema = '{"pass": true} or {"pass": false, "reason": "<brief explanation>"}'
    elif component == "scorer":
        schema = '{"tier": <int 0-3>, "score": <int 0-100>, "reasoning": "<non-empty string>"}'
    else:
        schema = '{"type": "ai", "content": "<non-empty string>", "metadata": {}}'
    return (
        f"Your previous {component} response did not match the required output contract: {exc.detail}.\n"
        f"Return ONLY valid JSON matching this schema: {schema}\n"
        "Do not include Markdown fences, prose outside JSON, null content, or missing required fields."
    )


def _provider_error_from_response(response: httpx.Response, model: str) -> ModelProviderError:
    provider_message = ""
    provider_code: str | None = None
    try:
        payload = response.json()
    except Exception:
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            provider_message = _clean_provider_message(error.get("message"))
            code = error.get("code")
            provider_code = str(code) if code is not None else None
        else:
            provider_message = _clean_provider_message(payload.get("message") or payload.get("detail"))

    status_code = int(response.status_code)
    if not provider_message:
        provider_message = _clean_provider_message(getattr(response, "reason_phrase", "")) or f"HTTP {status_code}"

    retryable = status_code in {408, 429} or status_code >= 500
    error = ModelProviderError(
        provider=OPENROUTER_PROVIDER,
        model=model,
        status_code=status_code,
        provider_code=provider_code,
        provider_message=provider_message,
        retryable=retryable,
    )
    logger.error(
        "LLM provider error: provider={} model={} status={} code={} message={}",
        error.provider,
        error.model,
        error.status_code,
        error.provider_code,
        error.provider_message,
    )
    return error


def _provider_error_from_http_error(exc: httpx.HTTPError, model: str) -> ModelProviderError:
    """Convert transport-level provider failures into structured provider errors."""
    provider_message = _clean_provider_message(str(exc)) or exc.__class__.__name__
    error = ModelProviderError(
        provider=OPENROUTER_PROVIDER,
        model=model,
        provider_code=exc.__class__.__name__,
        provider_message=provider_message,
        retryable=False,
    )
    logger.error(
        "LLM provider transport error: provider={} model={} code={} message={}",
        error.provider,
        error.model,
        error.provider_code,
        error.provider_message,
    )
    return error


async def _call_openrouter(messages: list[dict[str, str]], model: str) -> str:
    """Send a chat completions request and return the assistant's reply text."""
    if _FAKE_AI_RESPONSE is not None:
        return _FAKE_AI_RESPONSE

    api_key = _get_api_key()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages, "max_completion_tokens": DEFAULT_OPENROUTER_MAX_COMPLETION_TOKENS},
            timeout=_openrouter_timeout(),
        )
        if response.is_error:
            raise _provider_error_from_response(response, model)
    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise ModelOutputContractError(
            component="chat completion",
            model=model,
            detail=f"provider response was not valid JSON ({exc})",
            raw_response=response.text,
        ) from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelOutputContractError(
            component="chat completion",
            model=model,
            detail=f"provider response did not include assistant message content ({exc})",
            raw_response=json.dumps(data, default=str),
        ) from exc
    if not isinstance(content, str):
        raise ModelOutputContractError(
            component="chat completion",
            model=model,
            detail="assistant message content must be a string",
            raw_response=json.dumps(data, default=str),
        )
    return content


def _should_retry_llm_error(exc: Exception) -> bool:
    if isinstance(exc, ModelProviderError):
        return exc.retryable
    return isinstance(exc, httpx.HTTPError)


async def _call_openrouter_with_retry(messages: list[dict[str, str]], model: str) -> str:
    """Call _call_openrouter with 1 automatic retry on transient failure."""
    try:
        return await _call_openrouter(messages, model)
    except Exception as exc:
        if not _should_retry_llm_error(exc):
            raise
        logger.warning("LLM call failed for model {}; retrying once. Error: {}", model, exc)
        try:
            return await _call_openrouter(messages, model)
        except httpx.HTTPError as retry_exc:
            raise _provider_error_from_http_error(retry_exc, model) from retry_exc


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse a JSON response from the LLM, stripping markdown code fences if present."""
    text = _strip_json_fences(raw)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse LLM response as JSON: {exc}\nRaw: {raw!r}")
        return {"type": "error", "content": raw}


def _strip_json_fences(raw: str) -> str:
    """Return raw JSON text with optional markdown fences removed."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    return text


def _extract_response_metadata(parsed: dict[str, Any]) -> dict[str, Any]:
    """Return normalized metadata from a simulator payload.

    The preferred response shape puts optional structured data under a
    dedicated ``metadata`` object. For backwards compatibility, if that key is
    absent, any additional top-level keys are treated as metadata.
    """
    metadata = parsed.get("metadata")
    if isinstance(metadata, dict):
        return metadata

    reserved_keys = {"type", "content", "metadata"}
    extras = {key: value for key, value in parsed.items() if key not in reserved_keys}
    return extras if extras else {}


def _normalize_evaluation(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the scorer payload into a stable dict shape."""
    try:
        tier = int(parsed["tier"])
        score = int(parsed["score"])
        reasoning = str(parsed["reasoning"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid inference evaluation payload: {parsed!r}") from exc

    if tier < 0 or tier > 3:
        raise ValueError(f"Evaluation tier must be between 0 and 3; got {tier!r}")
    if score < 0 or score > 100:
        raise ValueError(f"Evaluation score must be between 0 and 100; got {score!r}")
    if not reasoning.strip():
        raise ValueError("Evaluation reasoning must be non-empty.")

    return {
        "tier": tier,
        "score": score,
        "reasoning": reasoning,
    }


@dataclass(frozen=True)
class SimulatorValidationFailure:
    """Normalized validation failure detail for a specific stage and validator."""

    stage: str
    validator_name: str
    message: str
    raw_result: dict[str, Any]


@dataclass(frozen=True)
class SimulatorComponentResult:
    """Generation and validation metadata for one simulator output component."""

    name: str
    content: str
    ok: bool
    metadata: dict[str, Any] = field(default_factory=dict)
    retries_used: int = 0
    validation_failures: list[SimulatorValidationFailure] = field(default_factory=list)
    raw_response: str = ""


@dataclass(frozen=True)
class SimulatorTurnResult:
    """Structured result for one attempted simulator turn."""

    ok: bool
    error_message: str | None = None
    failure_type: str | None = None
    simulator_response: str = ""
    pc_validation_failures: list[SimulatorValidationFailure] = field(default_factory=list)
    updater_result: SimulatorComponentResult | None = None


class ParsedSimulatorResponse(NamedTuple):
    """Normalized model response with primary content plus optional metadata."""

    type: str
    content: str
    metadata: dict[str, Any]
    raw_response: str


class SimulatorClient:
    """Thin orchestrator around configurable validation and simulator advancement."""

    _OPENING_SCENE_PREFIX = "Opening scene: "

    def __init__(
        self,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        player_turn_validators: list[str] | None = None,
        simulator_turn_validators: list[str] | None = None,
        opener_template: str | None = None,
        updater_template: str | None = None,
        opener_model: str = DEFAULT_MODEL,
        updater_model: str = DEFAULT_MODEL,
        validator_model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize a simulator client with characters, prompts, validators, and models."""
        self._pc = pc
        self._npc = npc
        self._history: list[str] = []
        self._transcript_events: list[str] = []
        self._opening_metadata: dict[str, Any] = {}
        self._opening_scenes: list[str] = []

        self._player_turn_validators = (
            list(player_turn_validators) if player_turn_validators is not None else list(DEFAULT_PLAYER_TURN_VALIDATORS)
        )
        self._simulator_turn_validators = (
            list(simulator_turn_validators) if simulator_turn_validators is not None else list(DEFAULT_SIMULATOR_TURN_VALIDATORS)
        )

        self._opener_template = opener_template or OPENER
        self._updater_template = updater_template or UPDATER

        self._opener_model = opener_model
        self._updater_model = updater_model
        self._validator_model = validator_model
        self._recorder: "ValidationEventRecorder | None" = None
        self._turn_index: Callable[[], int] = lambda: 0

    @property
    def scene_opener_model(self) -> str:
        """Return the scene-opener model identifier for metadata recording."""
        return self._opener_model

    @property
    def updater_model(self) -> str:
        """Return the updater model identifier for metadata recording."""
        return self._updater_model

    @property
    def validator_model(self) -> str:
        """Return the validator model identifier for metadata recording."""
        return self._validator_model

    def export_history(self) -> list[str]:
        """Return a JSON-serialisable copy of the conversation history."""
        return list(self._history)

    def import_history(self, history: list[str]) -> None:
        """Restore conversation history from a snapshot."""
        self._history = list(history)
        self._transcript_events = list(history)
        self._opening_scenes = self._derive_opening_scenes(self._history)

    def export_state(self) -> dict[str, Any]:
        """Return all mutable simulator state needed for pause/resume."""
        return {
            "history": list(self._history),
            "transcript_events": list(self._transcript_events),
            "opening_metadata": dict(self._opening_metadata),
            "opening_scenes": list(self._opening_scenes),
        }

    def import_state(self, state: dict[str, Any]) -> None:
        """Restore mutable simulator state from a snapshot."""
        history = state.get("history", [])
        transcript_events = state.get("transcript_events", history)
        opening_metadata = state.get("opening_metadata", {})
        opening_scenes = state.get("opening_scenes")

        self._history = [str(entry) for entry in history] if isinstance(history, list) else []
        if isinstance(transcript_events, list):
            self._transcript_events = [str(entry) for entry in transcript_events]
        else:
            self._transcript_events = list(self._history)
        self._opening_metadata = dict(opening_metadata) if isinstance(opening_metadata, dict) else {}
        if isinstance(opening_scenes, list):
            self._opening_scenes = [str(scene) for scene in opening_scenes if str(scene).strip()]
        else:
            self._opening_scenes = self._derive_opening_scenes(self._history)

    @classmethod
    def _derive_opening_scenes(cls, history: list[str]) -> list[str]:
        """Recover opening scene text from legacy history-only snapshots."""
        scenes: list[str] = []
        for entry in history:
            if entry.startswith(cls._OPENING_SCENE_PREFIX):
                scene = entry.removeprefix(cls._OPENING_SCENE_PREFIX).strip()
                if scene:
                    scenes.append(scene)
        return scenes

    @property
    def player_turn_validators(self) -> list[str]:
        """Configured player-turn validators for this simulator instance."""
        return list(self._player_turn_validators)

    @property
    def simulator_turn_validators(self) -> list[str]:
        """Configured simulator-turn validators for this simulator instance."""
        return list(self._simulator_turn_validators)

    def attach_recorder(self, recorder: "ValidationEventRecorder", turn_index_provider: Callable[[], int]) -> None:
        """Attach a validation recorder and turn-index provider."""
        self._recorder = recorder
        self._turn_index = turn_index_provider

    def _transcript_context(self) -> str:
        if not self._transcript_events:
            return "[No prior scene context]"
        return "\n".join(self._transcript_events[-12:])

    def _validator_transcript(self, user_input: str) -> str:
        base = self._transcript_context()
        pending_turn = f"Player ({self._pc.hid}): {user_input}"
        return pending_turn if base == "[No prior scene context]" else f"{base}\n{pending_turn}"

    def _game_objective(self) -> str:
        shared_goal = self._opening_metadata.get("shared_goal")
        if isinstance(shared_goal, str) and shared_goal.strip():
            return shared_goal.strip()
        return ""

    @staticmethod
    def _validator_name(template: str, *, fallback: str) -> str:
        for line in template.splitlines():
            stripped = line.strip()
            if stripped.startswith("RULE:"):
                return stripped.removeprefix("RULE:").strip()
        for line in template.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:80]
        return fallback

    async def _call_json_prompt(
        self,
        *,
        system_prompt: str,
        user_input: str | None,
        model: str,
        component: str,
        corrective_feedback: str | None = None,
    ) -> ParsedSimulatorResponse:
        """Execute a prompt and return normalized content plus optional metadata."""
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input or "Begin."}]
        if corrective_feedback is not None:
            messages.append({"role": "user", "content": corrective_feedback})
        raw = await _call_openrouter_with_retry(messages, model)
        if not isinstance(raw, str):
            raise ModelOutputContractError(
                component=component,
                model=model,
                detail="response content must be a string",
            )
        parsed = _parse_json_response(raw)
        if parsed.get("type") == "error":
            raise ModelOutputContractError(
                component=component,
                model=model,
                detail="response was not valid JSON",
                raw_response=raw,
            )
        response_type = parsed.get("type", "ai")
        content = parsed.get("content")
        if not isinstance(response_type, str) or response_type not in {"ai", "info", "warning"}:
            raise ModelOutputContractError(
                component=component,
                model=model,
                detail="response type must be one of: ai, info, warning",
                raw_response=raw,
            )
        if not isinstance(content, str) or not content.strip():
            raise ModelOutputContractError(
                component=component,
                model=model,
                detail="response content must be a non-empty string",
                raw_response=raw,
            )
        return ParsedSimulatorResponse(
            type=response_type,
            content=content,
            metadata=_extract_response_metadata(parsed),
            raw_response=raw,
        )

    def _build_opening_scene_prompt(self) -> str:
        """Render the configured opening-scene template."""
        return build_opener_prompt(
            self._pc,
            self._npc,
            template=self._opener_template,
            excluded_scenes=self._opening_scenes,
        )

    def _build_updater_prompt(self, *, user_input: str) -> str:
        """Render the configured simulator updater prompt."""
        return build_updater_prompt(
            self._pc,
            self._npc,
            game_objective=self._game_objective(),
            transcript=self._transcript_context(),
            player_action=user_input,
            template=self._updater_template,
        )

    def _build_player_validator_prompt(self, *, validator_template: str, user_input: str) -> str:
        """Render one player-turn validator prompt."""
        return build_player_validator_prompt(
            self._pc,
            self._npc,
            player_action=user_input,
            transcript=self._transcript_context(),
            validator_template=validator_template,
        )

    def _build_simulator_validator_prompt(
        self,
        *,
        validator_template: str,
        user_input: str,
        simulator_response: str,
    ) -> str:
        """Render one simulator-response validator prompt."""
        return build_simulator_validator_prompt(
            self._pc,
            self._npc,
            simulator_response=simulator_response,
            transcript=self._validator_transcript(user_input),
            game_objective=self._game_objective(),
            validator_template=validator_template,
        )

    async def _run_validator_once(self, system_prompt: str, *, corrective_feedback: str | None = None) -> dict[str, Any]:
        messages = [{"role": "system", "content": system_prompt}]
        if corrective_feedback is not None:
            messages.append({"role": "user", "content": corrective_feedback})
        raw = await _call_openrouter_with_retry(messages, self._validator_model)
        if not isinstance(raw, str):
            raise ModelOutputContractError(
                component="validator",
                model=self._validator_model,
                detail="response content must be a string",
            )
        result = _parse_json_response(raw)
        if result.get("type") == "error":
            raise ModelOutputContractError(
                component="validator",
                model=self._validator_model,
                detail="response was not valid JSON",
                raw_response=raw,
            )
        if not isinstance(result.get("pass"), bool):
            raise ModelOutputContractError(
                component="validator",
                model=self._validator_model,
                detail="response must include a boolean pass field",
                raw_response=raw,
            )
        return result

    async def _run_validator(self, system_prompt: str) -> dict[str, Any]:
        try:
            return await self._run_validator_once(system_prompt)
        except ModelProviderError:
            raise
        except ModelOutputContractError as exc:
            _log_model_output_contract_failure(exc, operation="validator", attempt=1, will_retry=True)
            try:
                return await self._run_validator_once(
                    system_prompt,
                    corrective_feedback=_contract_retry_instruction("validator", exc),
                )
            except ModelOutputContractError as retry_exc:
                raise _model_output_provider_error(retry_exc, operation="validator", attempt=2) from retry_exc

    async def _run_player_validator(self, validator_template: str, user_input: str) -> tuple[str, dict[str, Any]]:
        """Execute one configured player-turn validator."""
        validator_name = self._validator_name(validator_template, fallback="player validator")
        return validator_name, await self._run_validator(
            self._build_player_validator_prompt(validator_template=validator_template, user_input=user_input)
        )

    async def _generate_simulator_response(
        self,
        *,
        user_input: str,
        corrective_feedback: str | None = None,
    ) -> ParsedSimulatorResponse:
        """Generate the next immediate simulator response."""
        response = await self._call_json_prompt(
            system_prompt=self._build_updater_prompt(user_input=user_input),
            user_input=user_input,
            model=self._updater_model,
            component="updater",
            corrective_feedback=corrective_feedback,
        )
        return response

    async def _generate_simulator_response_with_retry(self, *, user_input: str) -> ParsedSimulatorResponse:
        """Generate a simulator response, retrying one model-output contract failure."""
        try:
            return await self._generate_simulator_response(user_input=user_input)
        except ModelProviderError:
            raise
        except ModelOutputContractError as exc:
            _log_model_output_contract_failure(exc, operation="updater", attempt=1, will_retry=True)
            try:
                return await self._generate_simulator_response(
                    user_input=user_input,
                    corrective_feedback=_contract_retry_instruction("updater", exc),
                )
            except ModelOutputContractError as retry_exc:
                raise _model_output_provider_error(retry_exc, operation="updater", attempt=2) from retry_exc

    @staticmethod
    def _validation_error(result: dict[str, Any], *, default_message: str) -> str | None:
        if result.get("pass") is False:
            return str(result.get("reason") or result.get("content") or default_message)
        return None

    async def _collect_player_validation_failures(self, user_input: str) -> list[SimulatorValidationFailure]:
        """Run all configured player validators concurrently and return failures only."""
        validator_tasks = [
            asyncio.create_task(self._run_player_validator(validator_template, user_input))
            for validator_template in self._player_turn_validators
        ]
        failures: list[SimulatorValidationFailure] = []
        try:
            for task in asyncio.as_completed(validator_tasks):
                validator_name, result = await task
                logger.debug(
                    "Player validator result: {} pass={} result={}",
                    validator_name,
                    result.get("pass"),
                    result,
                )
                error_message = self._validation_error(result, default_message="Invalid action.")
                if error_message is not None:
                    logger.info(f"Player validation failed: {validator_name} - {error_message}")
                    failures.append(
                        SimulatorValidationFailure(
                            stage="player_validation",
                            validator_name=validator_name,
                            message=error_message,
                            raw_result=result,
                        )
                    )
                    for pending_task in validator_tasks:
                        if not pending_task.done():
                            pending_task.cancel()
                    break
        except Exception:
            for pending_task in validator_tasks:
                if not pending_task.done():
                    pending_task.cancel()
            raise
        finally:
            await asyncio.gather(*validator_tasks, return_exceptions=True)

        return failures

    async def _record_validation_failures(
        self,
        *,
        failures: list[SimulatorValidationFailure],
        event_source: str,
        response: str,
    ) -> None:
        """Persist validation failures when a recorder is attached."""
        if self._recorder is None or not failures:
            return

        turn_index = self._turn_index()
        for failure in failures:
            await self._recorder.record_violation(
                event_source=event_source,
                validator_name=failure.validator_name,
                stage=failure.stage,
                message=failure.message,
                response=response,
                raw_result=failure.raw_result,
                turn_index=turn_index,
            )

    async def _validate_simulator_response(
        self,
        *,
        user_input: str,
        simulator_response: str,
    ) -> list[SimulatorValidationFailure]:
        """Validate one generated simulator response against its configured validator ensemble."""
        validator_tasks = [
            asyncio.create_task(
                self._run_simulator_validator(
                    validator_template,
                    user_input=user_input,
                    simulator_response=simulator_response,
                    fallback=f"simulator validator {index}",
                )
            )
            for index, validator_template in enumerate(self._simulator_turn_validators, start=1)
        ]
        failures: list[SimulatorValidationFailure] = []
        try:
            for task in asyncio.as_completed(validator_tasks):
                validator_name, result = await task
                logger.debug(
                    "Simulator validator result: {} pass={} result={}",
                    validator_name,
                    result.get("pass"),
                    result,
                )
                error_message = self._validation_error(result, default_message="Invalid simulator response.")
                if error_message is not None:
                    logger.info(f"Simulator validation failed: {validator_name} - {error_message}")
                    failures.append(
                        SimulatorValidationFailure(
                            stage="simulator_validation",
                            validator_name=validator_name,
                            message=error_message,
                            raw_result=result,
                        )
                    )
                    for pending_task in validator_tasks:
                        if not pending_task.done():
                            pending_task.cancel()
                    break
        finally:
            await asyncio.gather(*validator_tasks, return_exceptions=True)

        return failures

    async def _run_simulator_validator(
        self,
        validator_template: str,
        *,
        user_input: str,
        simulator_response: str,
        fallback: str,
    ) -> tuple[str, dict[str, Any]]:
        """Execute one configured simulator-response validator."""
        validator_name = self._validator_name(validator_template, fallback=fallback)
        result = await self._run_validator(
            self._build_simulator_validator_prompt(
                validator_template=validator_template,
                user_input=user_input,
                simulator_response=simulator_response,
            )
        )
        return validator_name, result

    async def _cancel_tasks(self, *tasks: asyncio.Task[Any]) -> None:
        """Cancel unfinished tasks and absorb cancellation errors."""
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_updater_with_retry(
        self,
        *,
        user_input: str,
        initial_response: ParsedSimulatorResponse,
    ) -> SimulatorComponentResult:
        """Validate the updater output and retry once if validators fail."""
        response = initial_response
        retries_used = 0
        failures = await self._validate_simulator_response(
            user_input=user_input,
            simulator_response=response.content,
        )
        await self._record_validation_failures(
            failures=failures,
            event_source="simulator_validation",
            response=response.content,
        )
        if failures:
            retries_used = 1
            response = await self._generate_simulator_response_with_retry(user_input=user_input)
            failures = await self._validate_simulator_response(
                user_input=user_input,
                simulator_response=response.content,
            )
            await self._record_validation_failures(
                failures=failures,
                event_source="simulator_validation",
                response=response.content,
            )

        return SimulatorComponentResult(
            name="updater",
            content=response.content,
            ok=not failures,
            metadata=response.metadata,
            retries_used=retries_used,
            validation_failures=failures,
            raw_response=response.raw_response,
        )

    async def chat(self, user_input: str | None) -> ParsedSimulatorResponse:
        """Generate the opening scene without player-input validation."""
        try:
            opening = await self._call_json_prompt(
                system_prompt=self._build_opening_scene_prompt(),
                user_input=user_input,
                model=self._opener_model,
                component="opener",
            )
        except ModelOutputContractError as exc:
            _log_model_output_contract_failure(exc, operation="opener", attempt=1, will_retry=True)
            try:
                opening = await self._call_json_prompt(
                    system_prompt=self._build_opening_scene_prompt(),
                    user_input=user_input,
                    model=self._opener_model,
                    component="opener",
                    corrective_feedback=_contract_retry_instruction("opener", exc),
                )
            except ModelOutputContractError as retry_exc:
                raise _model_output_provider_error(retry_exc, operation="opener", attempt=2) from retry_exc
        self._opening_metadata = dict(opening.metadata)
        self._opening_scenes.append(opening.content)
        self._history.append(f"Opening scene: {opening.content}")
        self._transcript_events.append(f"Opening scene: {opening.content}")
        return opening

    async def step(self, user_input: str) -> SimulatorTurnResult:
        """Validate player input, then generate and validate one simulator response."""
        player_validation_task = asyncio.create_task(self._collect_player_validation_failures(user_input))
        updater_generation_task = asyncio.create_task(self._generate_simulator_response_with_retry(user_input=user_input))

        try:
            player_validation_failures = await player_validation_task
        except ModelProviderError:
            await self._cancel_tasks(updater_generation_task)
            raise
        except Exception:
            await self._cancel_tasks(updater_generation_task)
            logger.exception("Player validation failed due to LLM/runtime error.")
            return SimulatorTurnResult(
                ok=False,
                error_message="The simulation engine hit an internal problem while validating the action.",
                failure_type=INTERNAL_ERROR,
            )

        if player_validation_failures:
            await self._cancel_tasks(updater_generation_task)
            await self._record_validation_failures(
                failures=player_validation_failures,
                event_source="player_validation",
                response=user_input,
            )
            return SimulatorTurnResult(
                ok=False,
                error_message=player_validation_failures[0].message,
                failure_type=PLAYER_TURN_VALIDATION_FAILED,
                pc_validation_failures=player_validation_failures,
            )

        try:
            initial_response = await updater_generation_task
            updater_result = await self._run_updater_with_retry(
                user_input=user_input,
                initial_response=initial_response,
            )
        except ModelProviderError:
            raise
        except Exception:
            logger.exception("Simulator updater failed due to LLM/runtime error.")
            return SimulatorTurnResult(
                ok=False,
                error_message="The simulation engine hit an internal problem while producing a simulator response.",
                failure_type=INTERNAL_ERROR,
                pc_validation_failures=player_validation_failures,
            )

        if not updater_result.ok:
            return SimulatorTurnResult(
                ok=False,
                error_message="I couldn't produce a valid simulator response. Please retry your action.",
                failure_type=SIMULATOR_TURN_VALIDATION_RETRY_EXHAUSTED,
                simulator_response="",
                pc_validation_failures=player_validation_failures,
                updater_result=updater_result,
            )

        self._transcript_events.extend(
            [
                f"Player ({self._pc.hid}): {user_input}",
                f"Simulator: {updater_result.content}",
            ]
        )
        self._history.extend(
            [
                f"Player ({self._pc.hid}): {user_input}",
                f"Simulator: {updater_result.content}",
            ]
        )
        logger.debug(f"SimulatorClient simulator reply ({len(updater_result.content)} chars)")
        return SimulatorTurnResult(
            ok=True,
            simulator_response=updater_result.content,
            pc_validation_failures=player_validation_failures,
            updater_result=updater_result,
        )


class ScorerResult(NamedTuple):
    """Parsed evaluation payload plus the raw JSON text returned by the scorer."""

    evaluation: dict[str, Any]
    raw_json: str


class ScorerClient:
    """One-shot stateless client that executes a rendered scoring prompt."""

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        """Initialise with model identifier only."""
        self._model = model

    def _parse_score_response(self, raw: str) -> ScorerResult:
        if not isinstance(raw, str):
            raise ModelOutputContractError(
                component="scorer",
                model=self._model,
                detail="response content must be a string",
            )
        stripped = _strip_json_fences(raw)
        parsed = _parse_json_response(raw)
        if parsed.get("type") == "error":
            raise ModelOutputContractError(
                component="scorer",
                model=self._model,
                detail="response was not valid JSON",
                raw_response=raw,
            )
        try:
            result = _normalize_evaluation(parsed)
        except ValueError as exc:
            raise ModelOutputContractError(
                component="scorer",
                model=self._model,
                detail=str(exc),
                raw_response=raw,
            ) from exc
        logger.debug(f"ScorerClient result: {result}")
        return ScorerResult(evaluation=result, raw_json=stripped)

    async def score(self, *, prompt: str, transcript: str) -> ScorerResult:
        """Execute a rendered scoring prompt and return parsed + raw JSON results."""
        if not prompt.strip():
            raise ValueError("Scoring prompt must be non-empty.")
        if not transcript.strip():
            raise ValueError("Scoring transcript must be non-empty.")

        try:
            raw = await _call_openrouter_with_retry([{"role": "user", "content": prompt}], self._model)
            return self._parse_score_response(raw)
        except ModelOutputContractError as exc:
            _log_model_output_contract_failure(exc, operation="scorer", attempt=1, will_retry=True)
            retry_prompt = f"{prompt}\n\n{_contract_retry_instruction('scorer', exc)}"
            try:
                retry_raw = await _call_openrouter_with_retry(
                    [{"role": "user", "content": retry_prompt}],
                    self._model,
                )
                return self._parse_score_response(retry_raw)
            except ModelOutputContractError as retry_exc:
                raise _model_output_provider_error(retry_exc, operation="scorer", attempt=2) from retry_exc
