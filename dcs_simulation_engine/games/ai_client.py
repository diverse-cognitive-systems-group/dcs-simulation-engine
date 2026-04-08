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
from typing import Any, NamedTuple

import httpx
from dcs_simulation_engine.core.constants import (
    OPENROUTER_BASE_URL,
)
from dcs_simulation_engine.dal.base import CharacterRecord
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


# Backward-compatible aliases
EngineValidationResult = EnsembleValidationResult
RolePlayingLLMValidationResult = EnsembleValidationResult


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
            "OPENROUTER_API_KEY is required to start the server. "
            "Set it in the environment, or use --fake-ai-response for local mock mode."
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
    text = raw.strip()
    # Strip optional ```json ... ``` fences that some models add
    if text.startswith("```"):
        lines = text.splitlines()
        # drop first line (```json or ```) and last line (```)
        text = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse LLM response as JSON: {exc}\nRaw: {raw!r}")
        return {"type": "error", "content": raw}


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


class ScorerClient:
    """One-shot stateless client that scores a player's goal inference against the NPC profile."""

    def __init__(self, npc: CharacterRecord, model: str = DEFAULT_MODEL) -> None:
        """Initialise with NPC character record and model identifier."""
        self._npc = npc
        self._model = model

    async def score(self, transcript: str, guess: str) -> dict[str, Any]:
        """Score the player's goal inference. Returns {"tier": int, "score": int, "reasoning": str}."""
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
        result = _parse_json_response(raw)
        logger.debug(f"ScorerClient result: {result}")
        return result



def format_ensemble_failures(result: EnsembleValidationResult) -> str:
    """Convert ensemble validation failures into a user-facing error string."""
    if not result.failed:
        return "Validation failed."
    lines = [f"[{f.rule}] {f.reason}" for f in result.failed if f.reason]
    return "\n".join(lines) if lines else "Validation failed."


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
    def create(cls, model: str = DEFAULT_VALIDATOR_MODEL) -> "EnsembleValidator":
        """Build all AtomicValidators from the subclass's ``_prompts`` dict."""
        validators = {
            rule: AtomicValidator(system_prompt=prompt, model=model)
            for rule, prompt in cls._prompts.items()
        }
        return cls(validators)

    def _pre_checks(self, text: str) -> list[ValidationResult]:
        """Override to add programmatic checks before LLM validation."""
        return []

    async def validate(
        self, text: str, context: dict[str, str] | None = None,
    ) -> EnsembleValidationResult:
        """Run pre-checks + all LLM validators in parallel."""
        ctx = context or {}
        pre_results = self._pre_checks(text)

        async def _run(rule: str, validator: AtomicValidator) -> ValidationResult:
            try:
                ctx_keys = self._context_routing.get(rule, [])
                rule_ctx = "\n".join(
                    f"{k}: {ctx.get(k, '')}" for k in ctx_keys if ctx.get(k)
                )
                passed, reason = await validator.validate(text, context=rule_ctx)
                return ValidationResult(rule=rule, passed=passed, reason=reason)
            except Exception as exc:
                logger.warning(f"{type(self).__name__} rule {rule} raised: {exc}")
                return ValidationResult(rule=rule, passed=False, reason=f"Validator error: {exc}")

        llm_results = list(
            await asyncio.gather(*[_run(r, v) for r, v in self._validators.items()])
        )
        results = pre_results + llm_results
        failed = [r for r in results if not r.passed]
        return EnsembleValidationResult(passed=len(failed) == 0, results=results, failed=failed)


class EngineValidator(EnsembleValidator):
    """Universally applicable simulation engine rules.

    Applied to both player (PC) input and LLM (MPC) output.
    """

    _prompts = ENGINE_VALIDATOR_PROMPTS
    _context_routing = ENGINE_CONTEXT_ROUTING
    RULES: list[str] = list(ENGINE_VALIDATOR_PROMPTS)

    @classmethod
    def create(cls, model: str = DEFAULT_VALIDATOR_MODEL) -> "EngineValidator":
        """Build all AtomicValidators from the subclass's ``_prompts`` dict."""
        validators = {
            rule: AtomicValidator(system_prompt=prompt, model=model)
            for rule, prompt in cls._prompts.items()
        }
        return cls(validators)


class GameValidator(EnsembleValidator):
    """Base class for game-specific ensemble validators.

    Use ``GameValidator.for_game(game_name)`` to obtain the correct
    validator for a given game.  Each subclass sets ``_prompts`` and
    ``_context_routing`` following the standard EnsembleValidator pattern.
    """

    _prompts: dict[str, str] = {}
    _context_routing: dict[str, list[str]] = {}

    @classmethod
    def create(cls, model: str = DEFAULT_VALIDATOR_MODEL) -> "GameValidator":
        """Build all AtomicValidators from the subclass's ``_prompts`` dict."""
        validators = {
            rule: AtomicValidator(system_prompt=prompt, model=model)
            for rule, prompt in cls._prompts.items()
        }
        return cls(validators)

    @classmethod
    def for_game(cls, game_name: str, model: str = DEFAULT_VALIDATOR_MODEL) -> "GameValidator":
        """Factory: return the GameValidator subclass for *game_name*."""
        registry: dict[str, type[GameValidator]] = {
            "explore": ExploreGameValidator,
            "infer intent": InferIntentGameValidator,
            "foresight": ForesightGameValidator,
            "goal horizon": GoalHorizonGameValidator,
        }
        key = game_name.strip().lower()
        klass = registry.get(key)
        if klass is None:
            raise ValueError(
                f"No GameValidator registered for game: {game_name!r}"
            )
        return klass.create(model=model)


class ExploreGameValidator(GameValidator):
    """Game-specific rules for the Explore sandbox game."""

    _prompts = EXPLORE_GAME_PROMPTS
    _context_routing = EXPLORE_GAME_CONTEXT_ROUTING
    RULES: list[str] = list(EXPLORE_GAME_PROMPTS)


class InferIntentGameValidator(GameValidator):
    """Game-specific rules for the Infer Intent game."""

    _prompts = INFER_INTENT_GAME_PROMPTS
    _context_routing = INFER_INTENT_GAME_CONTEXT_ROUTING
    RULES: list[str] = list(INFER_INTENT_GAME_PROMPTS)


class ForesightGameValidator(GameValidator):
    """Game-specific rules for the Foresight game."""

    _prompts = FORESIGHT_GAME_PROMPTS
    _context_routing = FORESIGHT_GAME_CONTEXT_ROUTING
    RULES: list[str] = list(FORESIGHT_GAME_PROMPTS)


class GoalHorizonGameValidator(GameValidator):
    """Game-specific rules for the Goal Horizon game."""

    _prompts = GOAL_HORIZON_GAME_PROMPTS
    _context_routing = GOAL_HORIZON_GAME_CONTEXT_ROUTING
    RULES: list[str] = list(GOAL_HORIZON_GAME_PROMPTS)


class RolePlayingLLMValidator(EnsembleValidator):
    """LLM role-play fidelity rules for UpdaterClient (MPC) output.

    VALID-SCHEMA is checked programmatically via ``_pre_checks``;
    the remaining 11 rules are checked via AtomicValidator in parallel.
    """

    _prompts = ROLEPLAYING_VALIDATOR_PROMPTS
    _context_routing = ROLEPLAYING_CONTEXT_ROUTING
    RULES: list[str] = ["VALID-SCHEMA"] + list(ROLEPLAYING_VALIDATOR_PROMPTS)

    @classmethod
    def create(cls, model: str = DEFAULT_VALIDATOR_MODEL) -> "RolePlayingLLMValidator":
        """Build all AtomicValidators from the subclass's ``_prompts`` dict."""
        validators = {
            rule: AtomicValidator(system_prompt=prompt, model=model)
            for rule, prompt in cls._prompts.items()
        }
        return cls(validators)

    def _pre_checks(self, text: str) -> list[ValidationResult]:
        """Programmatic VALID-SCHEMA check before LLM validation."""
        return [self._check_schema(text)]

    @staticmethod
    def _check_schema(text: str) -> ValidationResult:
        """Check updater output matches ``{"type": "ai", "content": "..."}``."""
        stripped = text.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return ValidationResult("VALID-SCHEMA", False, "Response is not valid JSON")
        if not isinstance(parsed, dict):
            return ValidationResult("VALID-SCHEMA", False, "Response is not a JSON object")
        if parsed.get("type") != "ai" or "content" not in parsed:
            return ValidationResult("VALID-SCHEMA", False, 'Missing or wrong "type"/"content" keys')
        extra = set(parsed.keys()) - {"type", "content"}
        if extra:
            return ValidationResult("VALID-SCHEMA", False, f"Extra keys: {extra}")
        return ValidationResult("VALID-SCHEMA", True, "")


class ValidationOrchestrator:
    """Composes EngineValidator, GameValidator, and RolePlayingLLMValidator.

    Provides ``validate_pc_input`` and ``generate_validated_npc_response`` as
    the two public entry points used by game ``step()`` methods.
    """

    NPC_OUTPUT_RETRY_BUDGET: int = 2

    def __init__(
        self,
        engine_validator: EngineValidator,
        game_validator: GameValidator,
        roleplaying_validator: RolePlayingLLMValidator,
        is_llm_player: bool = False,
    ) -> None:
        """Initialise with pre-built sub-validators."""
        self._engine = engine_validator
        self._game = game_validator
        self._roleplaying = roleplaying_validator
        self._is_llm_player = is_llm_player

    @classmethod
    def create(
        cls,
        game_name: str,
        is_llm_player: bool = False,
        model: str = DEFAULT_VALIDATOR_MODEL,
    ) -> "ValidationOrchestrator":
        """Build all sub-validators for the given game."""
        return cls(
            engine_validator=EngineValidator.create(model=model),
            game_validator=GameValidator.for_game(game_name, model=model),
            roleplaying_validator=RolePlayingLLMValidator.create(model=model),
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
    # PC input validation
    # ------------------------------------------------------------------

    async def validate_pc_input(
        self,
        text: str,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
    ) -> EnsembleValidationResult | None:
        """Run ensemble validators on PC input. Returns ``None`` if all pass."""
        ctx = self._build_context(pc=pc, npc=npc, updater=updater, player_action=text)
        coros = [
            self._engine.validate(text, ctx),
            self._game.validate(text, ctx),
        ]
        if self._is_llm_player:
            coros.append(self._roleplaying.validate(text, ctx))
        results = list(await asyncio.gather(*coros))
        return self._merge_results(results)

    # ------------------------------------------------------------------
    # NPC output validation
    # ------------------------------------------------------------------

    async def validate_npc_output(
        self,
        text: str,
        *,
        pc: CharacterRecord,
        npc: CharacterRecord,
        updater: UpdaterClient,
        player_action: str,
    ) -> EnsembleValidationResult | None:
        """Run all ensemble validators on NPC output. Returns ``None`` if all pass."""
        ctx = self._build_context(pc=pc, npc=npc, updater=updater, player_action=player_action)
        results = list(
            await asyncio.gather(
                self._engine.validate(text, ctx),
                self._game.validate(text, ctx),
                self._roleplaying.validate(text, ctx),
            )
        )
        return self._merge_results(results)

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
        for attempt in range(1, self.NPC_OUTPUT_RETRY_BUDGET + 1):
            reply = await updater.chat(user_input)
            # Re-wrap in JSON for RolePlayingLLMValidator's VALID-SCHEMA check;
            # updater.chat() already parsed and extracted the content field.
            raw_wrapped = json.dumps({"type": "ai", "content": reply})
            result = await self.validate_npc_output(
                raw_wrapped, pc=pc, npc=npc, updater=updater, player_action=action,
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