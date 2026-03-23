"""Async AI client for new-style games.

Provides two client types:
- UpdaterClient: stateful, maintains conversation history for multi-turn chat.
- ValidatorClient: stateless, sends only the system prompt + current action each call.

Both call OpenRouter's OpenAI-compatible chat completions endpoint.
"""
# ruff: noqa: E501  — prompt strings are intentionally long prose

import json
import os
from typing import Any, NamedTuple

import httpx
from dcs_simulation_engine.core.constants import (
    OPENROUTER_BASE_URL,
)
from dcs_simulation_engine.dal.base import CharacterRecord
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

DEFAULT_MODEL = "openai/gpt-5-mini"
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


async def _call_openrouter(messages: list[dict[str, str]], model: str) -> str:
    """Send a chat completions request and return the assistant's reply text."""
    if _FAKE_AI_RESPONSE is not None:
        return _FAKE_AI_RESPONSE

    api_key = _get_api_key()
    async with httpx.AsyncClient() as client:
        response = await client.post(
            _CHAT_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": messages},
            timeout=None,
        )
        if response.is_error:
            raise httpx.HTTPStatusError(
                f"{response.status_code}: {response.text}",
                request=response.request,
                response=response,
            )
    data = response.json()
    return data["choices"][0]["message"]["content"]


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


def _normalize_inference_evaluation(parsed: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the scorer payload into a stable dict shape."""
    try:
        tier = int(parsed["tier"])
        score = int(parsed["score"])
        reasoning = str(parsed["reasoning"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid inference evaluation payload: {parsed!r}") from exc

    if tier < 0 or tier > 3:
        raise ValueError(f"Inference evaluation tier must be between 0 and 3; got {tier!r}")
    if score < 0 or score > 100:
        raise ValueError(f"Inference evaluation score must be between 0 and 100; got {score!r}")
    if not reasoning.strip():
        raise ValueError("Inference evaluation reasoning must be non-empty.")

    return {
        "tier": tier,
        "score": score,
        "reasoning": reasoning,
    }


_INFERENCE_SCORER_TEMPLATE = """
You are an expert evaluator for a social cognition research study.

A player interacted with a simulated character and then guessed the character's goal or intention.
Your job is to score how accurately the player identified the character's goal.

## NPC Character Profile
{{ npc_long_description }}

Abilities:
{{ npc_abilities }}

## Interaction Transcript
{{ transcript }}

## Player's Guess
{{ guess }}

## Scoring Rubric
- Tier 0 (0-24): Completely incorrect - the guess bears no meaningful resemblance to the character's actual behavior or goal
- Tier 1 (25-49): Weak resemblance - some superficial overlap but fundamentally misses the goal
- Tier 2 (50-74): Partial understanding - captures key aspects but incomplete or imprecise
- Tier 3 (75-100): Nearly or fully correct - accurately identifies the goal with appropriate nuance

## Instructions
1. Based on the NPC character profile and the transcript, identify the most plausible goal or intention driving the NPC's behavior.
2. Compare the player's guess to that goal.
3. Select a tier (0-3) and assign a specific score within that tier's range.
4. Briefly explain your reasoning.

Return only valid JSON with no extra text:
{
    "tier": <int 0-3>,
    "score": <int 0-100>,
    "reasoning": <str>
}
"""


class UpdaterClient:
    """Stateful async client for the scene-advancing (updater) LLM.

    Maintains the full conversation history so the model has context for each
    new turn. The system prompt is injected once at the start of each history.
    """

    def __init__(self, system_prompt: str, model: str = DEFAULT_MODEL) -> None:
        """Initialise with a system prompt and model identifier."""
        self._system_prompt = system_prompt
        self._model = model
        self._history: list[dict[str, str]] = []

    @property
    def history(self) -> list[dict[str, str]]:
        """Read-only copy of the conversation history."""
        return list(self._history)

    def reset(self) -> None:
        """Clear conversation history (e.g. on game reset)."""
        self._history = []

    async def chat(self, user_input: str | None) -> str:
        """Send the user's action and return the NPC's response content string."""
        # On the very first call (no history, no input), prompt the model to open the scene.
        content = user_input or "Begin."
        self._history.append({"role": "user", "content": content})

        messages = [{"role": "system", "content": self._system_prompt}] + self._history
        raw = await _call_openrouter(messages, self._model)

        # Parse the JSON wrapper the updater prompt requests.
        parsed = _parse_json_response(raw)
        reply = parsed.get("content", raw)

        self._history.append({"role": "assistant", "content": reply})
        logger.debug(f"UpdaterClient reply ({len(reply)} chars)")
        return reply


class ValidatorClient:
    """Stateless async client for the input-validation LLM.

    Sends a fresh context each call: just the pre-rendered system prompt
    (which already includes pc abilities) plus the user's proposed action.
    No history is maintained between calls.
    """

    def __init__(self, system_prompt_template: str, model: str = DEFAULT_MODEL) -> None:
        """Initialise with the Jinja2 template string from build_validator_prompt()."""
        # The template has a {{ user_input }} placeholder filled per-call via Jinja2.
        # Character data with literal { } braces is safe because Jinja2 only
        # expands {{ var }} syntax, not arbitrary brace sequences.
        self._system_prompt_template = system_prompt_template
        self._model = model

    async def validate(self, user_input: str) -> dict[str, Any]:
        """Validate a user action. Returns {"type": "info"|"error", "content": str}."""
        system_prompt = SandboxedEnvironment().from_string(self._system_prompt_template).render(user_input=user_input)
        messages = [{"role": "system", "content": system_prompt}]
        raw = await _call_openrouter(messages, self._model)
        result = _parse_json_response(raw)
        logger.debug(f"ValidatorClient result: {result}")
        return result


class ScorerResult(NamedTuple):
    """Parsed evaluation payload plus the raw JSON text returned by the scorer."""

    evaluation: dict[str, Any]
    raw_json: str


class ScorerClient:
    """One-shot stateless client that scores a player's goal inference against the NPC profile."""

    def __init__(self, npc: CharacterRecord, model: str = DEFAULT_MODEL) -> None:
        """Initialise with NPC character record and model identifier."""
        self._npc = npc
        self._model = model

    async def score(self, transcript: str, guess: str) -> ScorerResult:
        """Score the player's goal inference and return parsed + raw JSON results."""
        prompt = (
            SandboxedEnvironment()
            .from_string(_INFERENCE_SCORER_TEMPLATE)
            .render(
                npc_long_description=self._npc.data.get("long_description", ""),
                npc_abilities=self._npc.data.get("abilities", ""),
                transcript=transcript,
                guess=guess,
            )
        )
        raw = await _call_openrouter([{"role": "user", "content": prompt}], self._model)
        stripped = _strip_json_fences(raw)
        result = _normalize_inference_evaluation(_parse_json_response(raw))
        logger.debug(f"ScorerClient result: {result}")
        return ScorerResult(evaluation=result, raw_json=stripped)
