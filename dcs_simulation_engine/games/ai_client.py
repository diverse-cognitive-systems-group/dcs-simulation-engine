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
    CHARACTER_UPDATER_SYSTEM_TEMPLATE,
    DEFAULT_NPC_VALIDATOR_PROMPTS,
    DEFAULT_PC_VALIDATOR_PROMPTS,
    DEFAULT_SCENE_VALIDATOR_PROMPTS,
    OPENING_SCENE_TEMPLATE,
    PLAYER_VALIDATOR_SYSTEM_TEMPLATE,
    SCENE_UPDATER_TEMPLATE,
    SIMULATOR_VALIDATOR_SYSTEM_TEMPLATE,
)
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

DEFAULT_MODEL = "openai/gpt-5-mini"
_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"
_FAKE_AI_RESPONSE: str | None = None
_PROMPT_ENV = SandboxedEnvironment()


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


def _format_prompt_value(value: Any) -> str:
    """Normalize prompt values to strings while preserving simple list structure."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


def _build_character_context(pc: CharacterRecord, npc: CharacterRecord, **extra: Any) -> dict[str, str]:
    """Build the common prompt-rendering context for a PC/NPC pair."""
    context: dict[str, Any] = {
        "pc_hid": getattr(pc, "hid", ""),
        "pc_short_description": getattr(pc, "short_description", ""),
        "pc_long_description": pc.data.get("long_description", ""),
        "pc_abilities": pc.data.get("abilities", ""),
        "pc_scenarios": pc.data.get("scenarios", ""),
        "npc_hid": getattr(npc, "hid", ""),
        "npc_short_description": getattr(npc, "short_description", ""),
        "npc_long_description": npc.data.get("long_description", ""),
        "npc_abilities": npc.data.get("abilities", ""),
        "npc_scenarios": npc.data.get("scenarios", ""),
        **extra,
    }
    return {key: _format_prompt_value(value) for key, value in context.items()}


def _render_prompt(template: str, **context: Any) -> str:
    """Render a prompt template with normalized string context."""
    return _PROMPT_ENV.from_string(template).render(**{key: _format_prompt_value(value) for key, value in context.items()})


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
    scene_response: str = ""
    character_action: str = ""
    pc_validation_failures: list[SimulatorValidationFailure] = field(default_factory=list)
    scene_result: SimulatorComponentResult | None = None
    npc_result: SimulatorComponentResult | None = None


class ParsedSimulatorResponse(NamedTuple):
    """Normalized model response with primary content plus optional metadata."""

    type: str
    content: str
    metadata: dict[str, Any]
    raw_response: str


class SimulatorClient:
    """Thin orchestrator around configurable validation and scene/NPC advancement."""

    DEFAULT_PC_VALIDATOR_NAMES = list(DEFAULT_PC_VALIDATOR_PROMPTS.keys())
    DEFAULT_SCENE_VALIDATOR_NAMES = list(DEFAULT_SCENE_VALIDATOR_PROMPTS.keys())
    DEFAULT_NPC_VALIDATOR_NAMES = list(DEFAULT_NPC_VALIDATOR_PROMPTS.keys())

    def __init__(
        self,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        pc_validator_names: list[str] | None = None,
        scene_validator_names: list[str] | None = None,
        npc_validator_names: list[str] | None = None,
        opening_scene_template: str | None = None,
        scene_updater_template: str | None = None,
        npc_updater_template: str | None = None,
        opening_scene_model: str = DEFAULT_MODEL,
        scene_updater_model: str = DEFAULT_MODEL,
        npc_updater_model: str = DEFAULT_MODEL,
        validator_model: str = DEFAULT_MODEL,
    ) -> None:
        self._pc = pc
        self._npc = npc
        self._history: list[str] = []
        self._scene_context_events: list[str] = []

        self._pc_validator_names = list(pc_validator_names) if pc_validator_names is not None else list(self.DEFAULT_PC_VALIDATOR_NAMES)
        self._scene_validator_names = (
            list(scene_validator_names) if scene_validator_names is not None else list(self.DEFAULT_SCENE_VALIDATOR_NAMES)
        )
        self._npc_validator_names = list(npc_validator_names) if npc_validator_names is not None else list(self.DEFAULT_NPC_VALIDATOR_NAMES)

        self._ensure_known_names(self._pc_validator_names, DEFAULT_PC_VALIDATOR_PROMPTS, "pc validators")
        self._ensure_known_names(self._scene_validator_names, DEFAULT_SCENE_VALIDATOR_PROMPTS, "scene validators")
        self._ensure_known_names(self._npc_validator_names, DEFAULT_NPC_VALIDATOR_PROMPTS, "npc validators")

        self._opening_scene_template = opening_scene_template or OPENING_SCENE_TEMPLATE
        self._scene_updater_template = scene_updater_template or SCENE_UPDATER_TEMPLATE
        self._npc_updater_template = npc_updater_template or CHARACTER_UPDATER_SYSTEM_TEMPLATE

        self._opening_scene_model = opening_scene_model
        self._scene_updater_model = scene_updater_model
        self._npc_updater_model = npc_updater_model
        self._validator_model = validator_model

    @staticmethod
    def _ensure_known_names(names: list[str], registry: dict[str, str], label: str) -> None:
        """Validate configured prompt-name selections early with a helpful error."""
        unknown = sorted(name for name in names if name not in registry)
        if unknown:
            available = ", ".join(sorted(registry))
            raise ValueError(f"Unknown {label}: {', '.join(unknown)}. Available names: {available}")

    @property
    def scene_opener_model(self) -> str:
        """Return the scene-opener model identifier for metadata recording."""
        return self._opening_scene_model

    @property
    def scene_updater_model(self) -> str:
        """Return the scene-updater model identifier for metadata recording."""
        return self._scene_updater_model

    @property
    def npc_updater_model(self) -> str:
        """Return the NPC-updater model identifier for metadata recording."""
        return self._npc_updater_model

    @property
    def validator_model(self) -> str:
        """Return the validator model identifier for metadata recording."""
        return self._validator_model

    @property
    def pc_validator_names(self) -> list[str]:
        """Configured PC validator names for this simulator instance."""
        return list(self._pc_validator_names)

    @property
    def scene_validator_names(self) -> list[str]:
        """Configured scene validator names for this simulator instance."""
        return list(self._scene_validator_names)

    @property
    def npc_validator_names(self) -> list[str]:
        """Configured NPC validator names for this simulator instance."""
        return list(self._npc_validator_names)

    def _scene_context(self) -> str:
        if not self._scene_context_events:
            return "[No prior scene context]"
        return "\n".join(self._scene_context_events[-12:])

    def _prompt_context(self, **extra: Any) -> dict[str, str]:
        """Build the render context used by simulator prompt templates."""
        return _build_character_context(self._pc, self._npc, **extra)

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
        return _render_prompt(self._opening_scene_template, **self._prompt_context())

    def _build_npc_prompt(self, *, user_input: str) -> str:
        """Render the configured NPC updater prompt."""
        return _render_prompt(
            self._npc_updater_template,
            **self._prompt_context(
                user_input=user_input,
                scene_context=self._scene_context(),
                character_action="",
            ),
        )

    def _build_scene_prompt(self, *, user_input: str, character_action: str = "") -> str:
        """Render the configured scene updater prompt."""
        return _render_prompt(
            self._scene_updater_template,
            **self._prompt_context(
                user_input=user_input,
                scene_context=self._scene_context(),
                character_action=character_action,
            ),
        )

    def _build_pc_validator_prompt(self, *, validator_name: str, user_input: str) -> str:
        """Render one named player-input validator prompt."""
        return _render_prompt(
            PLAYER_VALIDATOR_SYSTEM_TEMPLATE,
            **self._prompt_context(
                user_input=user_input,
                rule_prompt=DEFAULT_PC_VALIDATOR_PROMPTS[validator_name],
            ),
        )

    def _build_component_validator_prompt(
        self,
        *,
        validator_name: str,
        target: str,
        user_input: str,
        character_action: str,
        scene_response: str,
    ) -> str:
        """Render one named simulator-output validator prompt focused on one component."""
        registry = DEFAULT_NPC_VALIDATOR_PROMPTS if target == "npc" else DEFAULT_SCENE_VALIDATOR_PROMPTS
        target_instruction = (
            "Validation target: NPC action only. Treat the scene update as supporting context only.\n\n"
            if target == "npc"
            else "Validation target: scene update only. Treat the other character action as supporting context only.\n\n"
        )
        return _render_prompt(
            SIMULATOR_VALIDATOR_SYSTEM_TEMPLATE,
            **self._prompt_context(
                user_input=user_input,
                character_action=character_action,
                scene_response=scene_response,
                scene_context=self._scene_context(),
                rule_prompt=target_instruction + registry[validator_name],
            ),
        )

    async def _run_validator(self, system_prompt: str) -> dict[str, Any]:
        raw = await _call_openrouter([{"role": "system", "content": system_prompt}], self._validator_model)
        result = _parse_json_response(raw)
        logger.debug(f"Validator result: {result}")
        return result

    async def _run_named_pc_validator(self, validator_name: str, user_input: str) -> tuple[str, dict[str, Any]]:
        """Execute one configured player-input validator."""
        return validator_name, await self._run_validator(
            self._build_pc_validator_prompt(validator_name=validator_name, user_input=user_input)
        )

    async def _generate_npc_action(self, *, user_input: str) -> tuple[str, str]:
        """Generate the NPC's next action."""
        return await self._call_json_prompt(
            system_prompt=self._build_npc_prompt(user_input=user_input),
            user_input=user_input,
            model=self._npc_updater_model,
        )

    async def _generate_scene_response(self, *, user_input: str, character_action: str = "") -> tuple[str, str]:
        """Generate the scene's next immediate update."""
        return await self._call_json_prompt(
            system_prompt=self._build_scene_prompt(user_input=user_input, character_action=character_action),
            user_input=user_input,
            model=self._scene_updater_model,
        )

    @staticmethod
    def _validation_error(result: dict[str, Any], *, default_message: str) -> str | None:
        if result.get("type") == "error":
            return str(result.get("content") or default_message)
        if result.get("pass") is False:
            return str(result.get("reason") or result.get("content") or default_message)
        return None

    async def _collect_pc_validation_failures(self, user_input: str) -> list[SimulatorValidationFailure]:
        """Run all configured PC validators concurrently and return failures only."""
        validator_tasks = [
            asyncio.create_task(self._run_named_pc_validator(validator_name, user_input)) for validator_name in self._pc_validator_names
        ]
        failures: list[SimulatorValidationFailure] = []
        try:
            for task in asyncio.as_completed(validator_tasks):
                validator_name, result = await task
                error_message = self._validation_error(result, default_message="Invalid action.")
                if error_message is not None:
                    failures.append(
                        SimulatorValidationFailure(
                            stage="pc_validation",
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

    async def _validate_component(
        self,
        *,
        target: str,
        validator_names: list[str],
        user_input: str,
        character_action: str,
        scene_response: str,
    ) -> list[SimulatorValidationFailure]:
        """Validate one generated component against its configured validator ensemble."""
        failures: list[SimulatorValidationFailure] = []
        for validator_name in validator_names:
            result = await self._run_validator(
                self._build_component_validator_prompt(
                    validator_name=validator_name,
                    target=target,
                    user_input=user_input,
                    character_action=character_action,
                    scene_response=scene_response,
                )
            )
            error_message = self._validation_error(result, default_message=f"Invalid {target} output.")
            if error_message is not None:
                failures.append(
                    SimulatorValidationFailure(
                        stage=f"{target}_validation",
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

    async def chat(self, user_input: str | None) -> ParsedSimulatorResponse:
        """Generate the opening scene without player-input validation."""
        opening = await self._call_json_prompt(
            system_prompt=self._build_opening_scene_prompt(),
            user_input=user_input,
            model=self._opening_scene_model,
        )
        self._history.append(f"Opening scene: {opening.content}")
        self._scene_context_events.append(f"Opening scene: {opening.content}")
        return opening

    async def step(self, user_input: str) -> SimulatorTurnResult:
        """Validate player input, then generate and validate NPC/scene outputs."""
        pc_validation_task = asyncio.create_task(self._collect_pc_validation_failures(user_input))
        npc_generation_task = asyncio.create_task(self._generate_npc_action(user_input=user_input))
        scene_generation_task = asyncio.create_task(self._generate_scene_response(user_input=user_input))

        pc_validation_failures = await pc_validation_task
        if pc_validation_failures:
            await self._cancel_tasks(npc_generation_task, scene_generation_task)
            return SimulatorTurnResult(
                ok=False,
                error_message=pc_validation_failures[0].message,
                pc_validation_failures=pc_validation_failures,
            )

        npc_response = await npc_generation_task
        scene_response_payload = await scene_generation_task
        character_action = npc_response.content
        npc_raw = npc_response.raw_response
        scene_response = scene_response_payload.content
        scene_raw = scene_response_payload.raw_response

        npc_failures = await self._validate_component(
            target="npc",
            validator_names=self._npc_validator_names,
            user_input=user_input,
            character_action=character_action,
            scene_response=scene_response,
        )
        npc_retries_used = 0
        if npc_failures:
            npc_retries_used = 1
            npc_response = await self._generate_npc_action(user_input=user_input)
            character_action = npc_response.content
            npc_raw = npc_response.raw_response
            npc_failures = await self._validate_component(
                target="npc",
                validator_names=self._npc_validator_names,
                user_input=user_input,
                character_action=character_action,
                scene_response=scene_response,
            )

        scene_failures = await self._validate_component(
            target="scene",
            validator_names=self._scene_validator_names,
            user_input=user_input,
            character_action=character_action,
            scene_response=scene_response,
        )
        scene_retries_used = 0
        if scene_failures:
            scene_retries_used = 1
            scene_response_payload = await self._generate_scene_response(user_input=user_input, character_action=character_action)
            scene_response = scene_response_payload.content
            scene_raw = scene_response_payload.raw_response
            scene_failures = await self._validate_component(
                target="scene",
                validator_names=self._scene_validator_names,
                user_input=user_input,
                character_action=character_action,
                scene_response=scene_response,
            )

        npc_result = SimulatorComponentResult(
            name="npc",
            content=character_action,
            ok=not npc_failures,
            metadata=npc_response.metadata,
            retries_used=npc_retries_used,
            validation_failures=npc_failures,
            raw_response=npc_raw,
        )
        scene_result = SimulatorComponentResult(
            name="scene",
            content=scene_response,
            ok=not scene_failures,
            metadata=scene_response_payload.metadata,
            retries_used=scene_retries_used,
            validation_failures=scene_failures,
            raw_response=scene_raw,
        )

        if npc_failures or scene_failures:
            first_failure = (npc_failures or scene_failures)[0]
            return SimulatorTurnResult(
                ok=False,
                error_message=first_failure.message,
                scene_response=scene_response,
                character_action=character_action,
                pc_validation_failures=pc_validation_failures,
                scene_result=scene_result,
                npc_result=npc_result,
            )

        self._scene_context_events.extend(
            [
                f"Player action: {user_input}",
                f"{self._npc.hid} action: {character_action}",
                f"Scene update: {scene_response}",
            ]
        )
        self._history.extend(
            [
                f"Player action: {user_input}",
                f"{self._npc.hid} action: {character_action}",
                f"Scene update: {scene_response}",
            ]
        )
        logger.debug(f"SimulatorClient scene reply ({len(scene_response)} chars)")
        return SimulatorTurnResult(
            ok=True,
            scene_response=scene_response,
            character_action=character_action,
            pc_validation_failures=pc_validation_failures,
            scene_result=scene_result,
            npc_result=npc_result,
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
