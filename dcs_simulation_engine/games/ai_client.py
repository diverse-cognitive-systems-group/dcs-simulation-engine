"""Async AI client."""
# ruff: noqa: E501  — prompt strings are intentionally long prose

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import httpx
from dcs_simulation_engine.core.constants import (
    OPENROUTER_BASE_URL,
)
from dcs_simulation_engine.dal.base import CharacterRecord
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

DEFAULT_MODEL = "openai/gpt-5-mini"
_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"
_FAKE_AI_RESPONSE: str | None = None


# TODO: I don't get why this fake_ai_response is here....why not in testing?
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
        self._pc = pc
        self._npc = npc
        self._history: list[str] = []
        self._transcript_events: list[str] = []
        self._opening_metadata: dict[str, Any] = {}

        self._player_turn_validators = (
            list(player_turn_validators) if player_turn_validators is not None else list(DEFAULT_PLAYER_TURN_VALIDATORS)
        )
        self._simulator_turn_validators = (
            list(simulator_turn_validators)
            if simulator_turn_validators is not None
            else list(DEFAULT_SIMULATOR_TURN_VALIDATORS)
        )

        self._opener_template = opener_template or OPENER
        self._updater_template = updater_template or UPDATER

        self._opener_model = opener_model
        self._updater_model = updater_model
        self._validator_model = validator_model

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

    @property
    def player_turn_validators(self) -> list[str]:
        """Configured player-turn validators for this simulator instance."""
        return list(self._player_turn_validators)

    @property
    def simulator_turn_validators(self) -> list[str]:
        """Configured simulator-turn validators for this simulator instance."""
        return list(self._simulator_turn_validators)

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

    async def _call_json_prompt(self, *, system_prompt: str, user_input: str | None, model: str) -> ParsedSimulatorResponse:
        """Execute a prompt and return normalized content plus optional metadata."""
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_input or "Begin."}]
        raw = await _call_openrouter(messages, model)
        parsed = _parse_json_response(raw)
        return ParsedSimulatorResponse(
            type=str(parsed.get("type", "ai")),
            content=str(parsed.get("content", raw)),
            metadata=_extract_response_metadata(parsed),
            raw_response=raw,
        )

    def _build_opening_scene_prompt(self) -> str:
        """Render the configured opening-scene template."""
        return build_opener_prompt(self._pc, self._npc, template=self._opener_template)

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

    async def _run_validator(self, system_prompt: str) -> dict[str, Any]:
        raw = await _call_openrouter([{"role": "system", "content": system_prompt}], self._validator_model)
        result = _parse_json_response(raw)
        logger.debug(f"Validator result: {result}")
        return result

    async def _run_player_validator(self, validator_template: str, user_input: str) -> tuple[str, dict[str, Any]]:
        """Execute one configured player-turn validator."""
        validator_name = self._validator_name(validator_template, fallback="player validator")
        return validator_name, await self._run_validator(
            self._build_player_validator_prompt(validator_template=validator_template, user_input=user_input)
        )

    async def _generate_simulator_response(self, *, user_input: str) -> ParsedSimulatorResponse:
        """Generate the next immediate simulator response."""
        response = await self._call_json_prompt(
            system_prompt=self._build_updater_prompt(user_input=user_input),
            user_input=user_input,
            model=self._updater_model,
        )
        if response.type == "error":
            raise ValueError("Updater returned an invalid JSON payload.")
        return response

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
                if result.get("type") == "error":
                    raise ValueError(f"{validator_name} returned an invalid JSON payload.")
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
        finally:
            await asyncio.gather(*validator_tasks, return_exceptions=True)

        return failures

    async def _validate_simulator_response(
        self,
        *,
        user_input: str,
        simulator_response: str,
    ) -> list[SimulatorValidationFailure]:
        """Validate one generated simulator response against its configured validator ensemble."""
        failures: list[SimulatorValidationFailure] = []
        for index, validator_template in enumerate(self._simulator_turn_validators, start=1):
            validator_name = self._validator_name(validator_template, fallback=f"simulator validator {index}")
            result = await self._run_validator(
                self._build_simulator_validator_prompt(
                    validator_template=validator_template,
                    user_input=user_input,
                    simulator_response=simulator_response,
                )
            )
            if result.get("type") == "error":
                raise ValueError(f"{validator_name} returned an invalid JSON payload.")
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
                break
        return failures

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
        if failures:
            retries_used = 1
            response = await self._generate_simulator_response(user_input=user_input)
            failures = await self._validate_simulator_response(
                user_input=user_input,
                simulator_response=response.content,
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
        opening = await self._call_json_prompt(
            system_prompt=self._build_opening_scene_prompt(),
            user_input=user_input,
            model=self._opener_model,
        )
        if opening.type == "error":
            raise ValueError("Opener returned an invalid JSON payload.")
        self._opening_metadata = dict(opening.metadata)
        self._history.append(f"Opening scene: {opening.content}")
        self._transcript_events.append(f"Opening scene: {opening.content}")
        return opening

    async def step(self, user_input: str) -> SimulatorTurnResult:
        """Validate player input, then generate and validate one simulator response."""
        player_validation_task = asyncio.create_task(self._collect_player_validation_failures(user_input))
        updater_generation_task = asyncio.create_task(self._generate_simulator_response(user_input=user_input))

        try:
            player_validation_failures = await player_validation_task
        except Exception as exc:
            await self._cancel_tasks(updater_generation_task)
            logger.exception("Player validation failed due to LLM/runtime error.")
            return SimulatorTurnResult(
                ok=False,
                error_message=f"I couldn't validate your action just now ({exc}). Please try again.",
            )

        if player_validation_failures:
            await self._cancel_tasks(updater_generation_task)
            return SimulatorTurnResult(
                ok=False,
                error_message=player_validation_failures[0].message,
                pc_validation_failures=player_validation_failures,
            )

        try:
            initial_response = await updater_generation_task
            updater_result = await self._run_updater_with_retry(
                user_input=user_input,
                initial_response=initial_response,
            )
        except Exception as exc:
            logger.exception("Simulator updater failed due to LLM/runtime error.")
            return SimulatorTurnResult(
                ok=False,
                error_message=f"I couldn't produce a simulator response just now ({exc}). Please try again.",
                pc_validation_failures=player_validation_failures,
            )

        if not updater_result.ok:
            return SimulatorTurnResult(
                ok=False,
                error_message="I couldn't produce a valid simulator response. Please retry your action.",
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

    async def score(self, *, prompt: str, transcript: str) -> ScorerResult:
        """Execute a rendered scoring prompt and return parsed + raw JSON results."""
        if not prompt.strip():
            raise ValueError("Scoring prompt must be non-empty.")
        if not transcript.strip():
            raise ValueError("Scoring transcript must be non-empty.")

        raw = await _call_openrouter([{"role": "user", "content": prompt}], self._model)
        stripped = _strip_json_fences(raw)
        result = _normalize_evaluation(_parse_json_response(raw))
        logger.debug(f"ScorerClient result: {result}")
        return ScorerResult(evaluation=result, raw_json=stripped)
