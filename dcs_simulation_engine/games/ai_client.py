"""Async AI client for new-style games.

Provides two client types:
- UpdaterClient: stateful, maintains conversation history for multi-turn chat.
- ValidatorClient: stateless, sends only the system prompt + current action each call.

Both call OpenRouter's OpenAI-compatible chat completions endpoint.
"""
# ruff: noqa: E501  — prompt strings are intentionally long prose

import asyncio
import json
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Self

import httpx
from dcs_simulation_engine.core.constants import (
    OPENROUTER_BASE_URL,
)
from dcs_simulation_engine.dal.base import CharacterRecord

if TYPE_CHECKING:
    from dcs_simulation_engine.core.session_event_recorder import ValidationEventRecorder
from dcs_simulation_engine.games.prompts import (
    ENGINE_CONTEXT_ROUTING,
    ENGINE_VALIDATOR_PROMPTS,
    EXPLORE_GAME_CONTEXT_ROUTING,
    EXPLORE_GAME_PROMPTS,
    FORESIGHT_GAME_CONTEXT_ROUTING,
    FORESIGHT_GAME_PROMPTS,
    GOAL_HORIZON_GAME_CONTEXT_ROUTING,
    GOAL_HORIZON_GAME_PROMPTS,
    INFER_INTENT_GAME_CONTEXT_ROUTING,
    INFER_INTENT_GAME_PROMPTS,
    ROLEPLAYING_CONTEXT_ROUTING,
    ROLEPLAYING_VALIDATOR_PROMPTS,
)
from jinja2.sandbox import SandboxedEnvironment
from loguru import logger

DEFAULT_MODEL = "openai/gpt-5-mini"
DEFAULT_VALIDATOR_MODEL = "openai/gpt-4.1-mini"
_CHAT_ENDPOINT = f"{OPENROUTER_BASE_URL}/chat/completions"
_FAKE_AI_RESPONSE: str | None = None


class ValidationResult(NamedTuple):
    """Result of a single atomic validation rule."""

    rule: str  # e.g. "VALID-FORM"
    passed: bool
    reason: str  # empty if passed, explanation if failed


class EnsembleValidationResult(NamedTuple):
    """Aggregate result from running an ensemble validator."""

    passed: bool  # True only if ALL rules passed
    results: list[ValidationResult]  # all per-rule results
    failed: list[ValidationResult]  # convenience: only failures


# Rules to skip during opening-scene validation — these are designed for
# action-response context and produce false failures on narrative scene descriptions.
OPENING_SCENE_SKIP_RULES: frozenset[str] = frozenset(
    {
        "VALID-FORM",
        "VALID-TEMPORAL-STRUCTURE",
        "INVENTED-PC-ACTION",
        "ADJUDICATED-UNOBSERVABLE",
    }
)


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

    def pop_last_response(self) -> str | None:
        """Remove and return the last assistant message from history, or ``None``."""
        if self._history and self._history[-1].get("role") == "assistant":
            return self._history.pop().get("content")
        return None


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


def format_ensemble_failures(result: EnsembleValidationResult) -> str:
    """Convert ensemble validation failures into a user-facing error string."""
    if not result.failed:
        return "Validation failed."
    lines = [f"[{f.rule}] {f.reason}" for f in result.failed if f.reason]
    return "\n".join(lines) if lines else "Validation failed."


NPC_SCHEMA_ENSEMBLE: str = "NpcSchema"


def _check_npc_schema(text: str) -> EnsembleValidationResult | None:
    """Verify NPC output matches ``{"type": "ai", "content": "..."}``.

    Returns ``None`` on success, or an ``EnsembleValidationResult`` whose
    single failure carries rule ``VALID-SCHEMA`` on failure.
    """
    stripped = text.strip()
    failure: ValidationResult | None = None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        failure = ValidationResult("VALID-SCHEMA", False, "Response is not valid JSON")
    else:
        if not isinstance(parsed, dict):
            failure = ValidationResult("VALID-SCHEMA", False, "Response is not a JSON object")
        elif parsed.get("type") != "ai" or "content" not in parsed:
            failure = ValidationResult(
                "VALID-SCHEMA",
                False,
                'Missing or wrong "type"/"content" keys',
            )
        else:
            extra = set(parsed.keys()) - {"type", "content"}
            if extra:
                failure = ValidationResult("VALID-SCHEMA", False, f"Extra keys: {extra}")

    if failure is None:
        return None
    return EnsembleValidationResult(passed=False, results=[failure], failed=[failure])


class AtomicValidator:
    """A validator that checks for a SINGLE condition.

    Instantiated with a system prompt describing one atomic validation rule.
    Each call sends the rule + text to the LLM and returns True (pass) or False (fail).
    """

    def __init__(self, system_prompt: str, model: str = DEFAULT_VALIDATOR_MODEL) -> None:
        """Initialise with a system prompt describing the condition and an optional model."""
        self._system_prompt = system_prompt
        self._model = model

    async def validate(self, text: str, context: str = "") -> tuple[bool, str]:
        """Validate text against this validator's condition.

        Returns (passed, reason) where reason is empty on success.
        When *context* is provided it is prepended to the user message
        above a ``---`` separator so the LLM can use it for judgment.
        """
        user_content = f"{context}\n---\nText to evaluate:\n{text}" if context else text
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]

        raw = await _call_openrouter(messages, self._model)
        parsed = _parse_json_response(raw)
        result = parsed.get("pass", False)
        reason = parsed.get("reason", "")

        if isinstance(result, str):
            result = result.lower() in ("true", "1", "yes")

        logger.debug(f"AtomicValidator result: {result}, reason: {reason}")
        return bool(result), str(reason)


class EnsembleValidator:
    """Base class for ensemble validators that compose AtomicValidators.

    Subclasses set two class variables:

    - ``_prompts``         — ``dict[str, str]``  rule name → system prompt
    - ``_context_routing`` — ``dict[str, list[str]]``  rule name → context keys

    Optionally override ``_pre_checks`` for programmatic validations.
    """

    _prompts: dict[str, str]
    _context_routing: dict[str, list[str]]

    def __init__(self, validators: dict[str, AtomicValidator]) -> None:
        """Initialise with a mapping of rule name to AtomicValidator."""
        self._validators = validators

    @classmethod
    def create(cls, model: str = DEFAULT_VALIDATOR_MODEL) -> Self:
        """Build all AtomicValidators from the subclass's ``_prompts`` dict."""
        validators = {rule: AtomicValidator(system_prompt=prompt, model=model) for rule, prompt in cls._prompts.items()}
        return cls(validators)

    def _pre_checks(self, text: str) -> list[ValidationResult]:
        """Override to add programmatic checks before LLM validation."""
        return []

    async def validate(
        self,
        text: str,
        context: dict[str, str] | None = None,
        skip_rules: frozenset[str] = frozenset(),
    ) -> EnsembleValidationResult:
        """Run pre-checks + LLM validators in parallel, stopping at the first failure.

        Pre-check failures short-circuit before any LLM calls are made.
        Atomic LLM validators race in parallel; the first failure observed
        cancels the remaining in-flight validators to avoid wasted work.
        """
        ctx = context or {}
        pre_results = self._pre_checks(text)
        pre_failed = [r for r in pre_results if not r.passed]
        if pre_failed:
            return EnsembleValidationResult(passed=False, results=pre_results, failed=pre_failed)

        async def _run(rule: str, validator: AtomicValidator) -> ValidationResult:
            if rule in skip_rules:
                return ValidationResult(rule=rule, passed=True, reason="")
            try:
                ctx_keys = self._context_routing.get(rule, [])
                rule_ctx = "\n".join(f"{k}: {ctx.get(k, '')}" for k in ctx_keys if ctx.get(k))
                passed, reason = await validator.validate(text, context=rule_ctx)
                return ValidationResult(rule=rule, passed=passed, reason=reason)
            except Exception as exc:
                logger.warning(f"{type(self).__name__} rule {rule} raised: {exc}")
                return ValidationResult(rule=rule, passed=False, reason=f"Validator error: {exc}")

        tasks = [asyncio.create_task(_run(r, v)) for r, v in self._validators.items()]
        collected: list[ValidationResult] = list(pre_results)
        try:
            for finished in asyncio.as_completed(tasks):
                result = await finished
                collected.append(result)
                if not result.passed:
                    break
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        failed = [r for r in collected if not r.passed]
        return EnsembleValidationResult(passed=len(failed) == 0, results=collected, failed=failed)


class EngineValidator(EnsembleValidator):
    """Universally applicable simulation engine rules.

    Applied to both player (PC) input and LLM (MPC) output.
    """

    _prompts = ENGINE_VALIDATOR_PROMPTS
    _context_routing = ENGINE_CONTEXT_ROUTING


class GameValidator(EnsembleValidator):
    """Ensemble of game-specific validation rules.

    Built via ``GameValidator.for_game(game_name)``. Each registered game
    supplies its own ``_prompts`` and ``_context_routing`` dicts; rule
    behavior is pure data, so one class serves all games.
    """

    _registry: "dict[str, tuple[dict[str, str], dict[str, list[str]]]]" = {
        "explore": (EXPLORE_GAME_PROMPTS, EXPLORE_GAME_CONTEXT_ROUTING),
        "infer intent": (INFER_INTENT_GAME_PROMPTS, INFER_INTENT_GAME_CONTEXT_ROUTING),
        "foresight": (FORESIGHT_GAME_PROMPTS, FORESIGHT_GAME_CONTEXT_ROUTING),
        "goal horizon": (GOAL_HORIZON_GAME_PROMPTS, GOAL_HORIZON_GAME_CONTEXT_ROUTING),
    }

    def __init__(
        self,
        validators: dict[str, AtomicValidator],
        *,
        game_name: str,
        prompts: dict[str, str],
        context_routing: dict[str, list[str]],
    ) -> None:
        super().__init__(validators)
        self._game_name = game_name
        self._prompts = prompts
        self._context_routing = context_routing

    @property
    def ensemble_name(self) -> str:
        """Legacy-compatible label used in logs and persisted event records."""
        return "".join(w.capitalize() for w in self._game_name.split()) + "GameValidator"

    @classmethod
    def for_game(cls, game_name: str, model: str = DEFAULT_VALIDATOR_MODEL) -> "GameValidator":
        """Factory: build a GameValidator for *game_name* from the registry."""
        key = game_name.strip().lower()
        entry = cls._registry.get(key)
        if entry is None:
            raise ValueError(f"No GameValidator registered for game: {game_name!r}")
        prompts, routing = entry
        validators = {rule: AtomicValidator(system_prompt=prompt, model=model) for rule, prompt in prompts.items()}
        return cls(
            validators,
            game_name=key,
            prompts=prompts,
            context_routing=routing,
        )


class RolePlayingValidator(EnsembleValidator):
    """Role-play fidelity rules applied to both PC and NPC input.

    All rules are checked via AtomicValidator in parallel. Schema-format
    checks live outside this validator (see ``_check_npc_schema``).
    """

    _prompts = ROLEPLAYING_VALIDATOR_PROMPTS
    _context_routing = ROLEPLAYING_CONTEXT_ROUTING


class ValidationOrchestrator:
    """Composes EngineValidator, GameValidator, and RolePlayingValidator.

    Exposes ``validate_input`` and ``generate_validated_npc_response`` as
    the public entry points used by game ``step()`` methods.
    """

    NPC_OUTPUT_RETRY_BUDGET: int = 2

    def __init__(
        self,
        engine_validator: EngineValidator,
        game_validator: GameValidator,
        roleplaying_validator: RolePlayingValidator,
        is_llm_player: bool = False,
    ) -> None:
        """Initialise with pre-built sub-validators."""
        self._engine = engine_validator
        self._game = game_validator
        self._roleplaying = roleplaying_validator
        self._is_llm_player = is_llm_player
        self._recorder: "ValidationEventRecorder | None" = None
        self._turn_index: Callable[[], int] = lambda: 0

    def attach_recorder(self, recorder: "ValidationEventRecorder", turn_index_provider: Callable[[], int]) -> None:
        """Attach a validation recorder + turn-index callback so violations are persisted."""
        self._recorder = recorder
        self._turn_index = turn_index_provider

    @classmethod
    def create(cls, game_name: str, is_llm_player: bool = False, model: str = DEFAULT_VALIDATOR_MODEL) -> "ValidationOrchestrator":
        """Build all sub-validators for the given game."""
        return cls(
            engine_validator=EngineValidator.create(model=model),
            game_validator=GameValidator.for_game(game_name, model=model),
            roleplaying_validator=RolePlayingValidator.create(model=model),
            is_llm_player=is_llm_player,
        )

    @property
    def is_llm_player(self) -> bool:
        """Whether the player character is LLM-controlled."""
        return self._is_llm_player

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
        player_action: str = "",
    ) -> dict[str, str]:
        """Build the context dict consumed by ensemble validator routing."""
        history = updater.history
        scene_lines: list[str] = []
        for msg in history[-6:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant"):
                scene_lines.append(f"{role}: {content}")
        pc_abilities = str(pc.data.get("abilities", ""))
        npc_abilities = str(npc.data.get("abilities", ""))
        return {
            "character_abilities": f"Player: {pc_abilities}\nNPC: {npc_abilities}",
            "scene_context": "\n".join(scene_lines),
            "player_action": player_action,
        }

    @staticmethod
    def _merge_results(
        results: list[EnsembleValidationResult],
    ) -> EnsembleValidationResult | None:
        """Merge multiple ensemble results. Returns ``None`` when all pass."""
        all_results: list[ValidationResult] = []
        all_failed: list[ValidationResult] = []
        for r in results:
            all_results.extend(r.results)
            all_failed.extend(r.failed)
        if all_failed:
            return EnsembleValidationResult(passed=False, results=all_results, failed=all_failed)
        return None

    # ------------------------------------------------------------------
    # Event source packing
    # ------------------------------------------------------------------

    def _event_source(self, source: Literal["pc", "npc"]) -> str:
        """Pack source + character type into a single event_source string."""
        if source == "npc":
            return "npc_llm"
        return "pc_llm" if self._is_llm_player else "pc_human"

    # ------------------------------------------------------------------
    # Unified input validation
    # ------------------------------------------------------------------

    async def validate_input(
        self,
        text: str,
        *,
        source: Literal["pc", "npc"],
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
        player_action: str = "",
        skip_rules: frozenset[str] = frozenset(),
        response_text: str | None = None,
    ) -> EnsembleValidationResult | None:
        """Run all ensemble validators on an input. Returns ``None`` if all pass.

        ``source`` identifies whether the text came from the PC or NPC and,
        combined with the orchestrator's ``is_llm_player`` flag, drives the
        ``event_source`` label used by the recorder. ``response_text``
        overrides the recorded text (NPC-side: text is a JSON wrapper;
        response_text is the unwrapped reply).
        """
        ctx = self._build_context(pc=pc, npc=npc, updater=updater, player_action=player_action)

        ensembles: list[tuple[str, EnsembleValidator]] = [
            ("EngineValidator", self._engine),
            (self._game.ensemble_name, self._game),
            ("RolePlayingValidator", self._roleplaying),
        ]

        async def _labeled(
            label: str, ensemble: EnsembleValidator,
        ) -> tuple[str, EnsembleValidationResult]:
            return label, await ensemble.validate(text, ctx, skip_rules=skip_rules)

        tasks = [asyncio.create_task(_labeled(lbl, ens)) for lbl, ens in ensembles]
        collected: list[tuple[str, EnsembleValidationResult]] = []
        try:
            for finished in asyncio.as_completed(tasks):
                label, res = await finished
                collected.append((label, res))
                if res.failed:
                    break
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        await self._record_violations(
            collected,
            event_source=self._event_source(source),
            response=response_text if response_text is not None else text,
        )

        return self._merge_results([r for _, r in collected])

    async def _record_violations(
        self,
        labeled: list[tuple[str, EnsembleValidationResult]],
        *,
        event_source: str,
        response: str,
    ) -> None:
        """Record each ensemble's failures to the attached validation recorder."""
        if self._recorder is None:
            return
        ti = self._turn_index()
        for ensemble_name, res in labeled:
            if res.failed:
                await self._recorder.record_ensemble_violations(
                    event_source=event_source,
                    ensemble_name=ensemble_name,
                    failed=res.failed,
                    response=response,
                    turn_index=ti,
                )

    async def _record_schema_failure(
        self,
        *,
        failure: EnsembleValidationResult,
        response: str,
    ) -> None:
        """Record an NPC schema-check failure under the NpcSchema ensemble."""
        if self._recorder is None:
            return
        await self._recorder.record_ensemble_violations(
            event_source=self._event_source("npc"),
            ensemble_name=NPC_SCHEMA_ENSEMBLE,
            failed=failure.failed,
            response=response,
            turn_index=self._turn_index(),
        )

    async def generate_validated_npc_response(
        self,
        user_input: str | None,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
    ) -> str | None:
        """Generate and validate NPC output, retrying on failure.

        Returns the validated reply text, or ``None`` if the retry budget
        is exhausted. All failures are logged.
        """
        action = user_input or ""
        is_opening_scene = user_input is None
        skip = OPENING_SCENE_SKIP_RULES if is_opening_scene else frozenset()
        for attempt in range(1, self.NPC_OUTPUT_RETRY_BUDGET + 1):
            reply = await updater.chat(user_input)
            # Re-wrap in JSON for the schema pre-check; updater.chat() already
            # parsed and extracted the content field.
            raw_wrapped = json.dumps({"type": "ai", "content": reply})
            schema_fail = _check_npc_schema(raw_wrapped)
            if schema_fail is not None:
                await self._record_schema_failure(failure=schema_fail, response=reply)
                msg = format_ensemble_failures(schema_fail)
                logger.warning(
                    "NPC output schema check failed (attempt {}/{}): {}",
                    attempt,
                    self.NPC_OUTPUT_RETRY_BUDGET,
                    msg,
                )
                updater.pop_last_response()
                continue
            result = await self.validate_input(
                raw_wrapped,
                source="npc",
                pc=pc,
                npc=npc,
                updater=updater,
                player_action=action,
                skip_rules=skip,
                response_text=reply,
            )
            if result is None:
                return reply  # passed
            msg = format_ensemble_failures(result)
            logger.warning(
                "NPC output validation failed (attempt {}/{}): {}",
                attempt,
                self.NPC_OUTPUT_RETRY_BUDGET,
                msg,
            )
            updater.pop_last_response()
        logger.error(
            "NPC output validation exhausted retry budget ({} attempts)",
            self.NPC_OUTPUT_RETRY_BUDGET,
        )
        return None
