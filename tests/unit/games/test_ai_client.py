"""Unit tests for OpenRouter call behavior in ai_client."""

import asyncio
from typing import Any

import pytest
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.games import prompts as P


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


# ── NPC schema pre-check tests ─────────────────────────────────────


@pytest.mark.unit
def test_check_npc_schema_pass() -> None:
    """_check_npc_schema returns None for well-formed updater JSON."""
    assert ai_client._check_npc_schema('{"type": "ai", "content": "hello"}') is None


@pytest.mark.unit
def test_check_npc_schema_fail_not_json() -> None:
    """_check_npc_schema reports VALID-SCHEMA failure for non-JSON text."""
    result = ai_client._check_npc_schema("not json")
    assert result is not None
    assert result.failed[0].rule == "VALID-SCHEMA"
    assert "not valid JSON" in result.failed[0].reason


@pytest.mark.unit
def test_check_npc_schema_fail_wrong_keys() -> None:
    """_check_npc_schema reports failure when required keys are missing."""
    result = ai_client._check_npc_schema('{"foo": "bar"}')
    assert result is not None
    reason = result.failed[0].reason
    assert "type" in reason or "content" in reason


@pytest.mark.unit
def test_check_npc_schema_fail_extra_keys() -> None:
    """_check_npc_schema reports failure when extra keys are present."""
    result = ai_client._check_npc_schema(
        '{"type": "ai", "content": "hello", "extra": 1}'
    )
    assert result is not None
    assert "Extra keys" in result.failed[0].reason


# ── RolePlayingValidator tests ────────────────────────────────────


@pytest.mark.unit
def test_roleplaying_validator_all_pass() -> None:
    """RolePlayingValidator reports passed=True when all rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.RolePlayingValidator.create()
        result = asyncio.run(v.validate("The door creaks open."))
        assert result.passed is True
        assert len(result.failed) == 0
        # 5 LLM rules (no schema pre-check in the validator itself).
        assert len(result.results) == len(ai_client.ROLEPLAYING_VALIDATOR_PROMPTS)
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_roleplaying_validator_llm_fail_propagates() -> None:
    """RolePlayingValidator reports failures from LLM-based validators."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "invented action"}')
    try:
        v = ai_client.RolePlayingValidator.create()
        result = asyncio.run(v.validate("You step back."))
        assert result.passed is False
        assert len(result.failed) == len(ai_client.ROLEPLAYING_VALIDATOR_PROMPTS)
    finally:
        ai_client.set_fake_ai_response(None)


# ── GameValidator tests ─────────────────────────────────────────────


@pytest.mark.unit
def test_game_validator_for_game_returns_correct_class() -> None:
    """GameValidator.for_game builds a GameValidator tagged with the right game."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        cases = [
            ("Explore", "explore", "ExploreGameValidator"),
            ("infer intent", "infer intent", "InferIntentGameValidator"),
            ("Foresight", "foresight", "ForesightGameValidator"),
            ("goal horizon", "goal horizon", "GoalHorizonGameValidator"),
        ]
        for input_name, expected_key, expected_label in cases:
            v = ai_client.GameValidator.for_game(input_name)
            assert isinstance(v, ai_client.GameValidator)
            assert v._game_name == expected_key
            assert v.ensemble_name == expected_label
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_game_validator_for_game_unknown_raises() -> None:
    """GameValidator.for_game raises ValueError for unknown game names."""
    with pytest.raises(ValueError, match="No GameValidator registered"):
        ai_client.GameValidator.for_game("nonexistent game")


@pytest.mark.unit
def test_explore_game_validator_all_pass() -> None:
    """GameValidator for 'explore' reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.GameValidator.for_game("explore")
        result = asyncio.run(v.validate("I wave at the creature."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_infer_intent_game_validator_all_pass() -> None:
    """GameValidator for 'infer intent' reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.GameValidator.for_game("infer intent")
        result = asyncio.run(v.validate("I watch the creature carefully."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_foresight_game_validator_all_pass() -> None:
    """GameValidator for 'foresight' reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.GameValidator.for_game("foresight")
        result = asyncio.run(v.validate("I wave and predict they will wave back."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_goal_horizon_game_validator_all_pass() -> None:
    """GameValidator for 'goal horizon' reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.GameValidator.for_game("goal horizon")
        result = asyncio.run(v.validate("I observe the creature."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_game_validator_llm_fail_propagates() -> None:
    """GameValidator reports failures from LLM-based validators."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "references a quest"}')
    try:
        v = ai_client.GameValidator.for_game("explore")
        result = asyncio.run(v.validate("How do I complete the quest?"))
        assert result.passed is False
        assert len(result.failed) == 2
    finally:
        ai_client.set_fake_ai_response(None)


# ── ValidationOrchestrator tests ────────────────────────────────────


@pytest.mark.unit
def test_orchestrator_create() -> None:
    """ValidationOrchestrator.create builds all three sub-validators."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        assert isinstance(orch._engine, ai_client.EngineValidator)
        assert isinstance(orch._game, ai_client.GameValidator)
        assert orch._game._game_name == "explore"
        assert isinstance(orch._roleplaying, ai_client.RolePlayingValidator)
        assert orch.is_llm_player is False
    finally:
        ai_client.set_fake_ai_response(None)


def _make_pc_npc_updater() -> tuple[Any, Any, Any]:
    from dcs_simulation_engine.dal.base import CharacterRecord

    pc = CharacterRecord(hid="pc1", name="PC", short_description="a player", data={"abilities": "can see"})
    npc = CharacterRecord(hid="npc1", name="NPC", short_description="a creature", data={"abilities": "can move"})
    updater = ai_client.UpdaterClient(system_prompt="test")
    return pc, npc, updater


@pytest.mark.unit
def test_orchestrator_validate_input_pc_all_pass() -> None:
    """validate_input(source='pc') returns None when all validators pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        pc, npc, updater = _make_pc_npc_updater()
        result = asyncio.run(
            orch.validate_input(
                "I wave.", source="pc", pc=pc, npc=npc, updater=updater,
                player_action="I wave.",
            )
        )
        assert result is None
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_validate_input_pc_fail_propagates() -> None:
    """validate_input returns merged failures from all three ensembles."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "invalid"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        pc, npc, updater = _make_pc_npc_updater()
        result = asyncio.run(
            orch.validate_input(
                "bad input", source="pc", pc=pc, npc=npc, updater=updater,
                player_action="bad input",
            )
        )
        assert result is not None
        assert result.passed is False
        # Engine (1) + Game (2) + RolePlaying (5) = 8 failures; no
        # conditional skip — role-playing runs for every actor.
        expected = (
            len(ai_client.ENGINE_VALIDATOR_PROMPTS)
            + len(ai_client.EXPLORE_GAME_PROMPTS)
            + len(ai_client.ROLEPLAYING_VALIDATOR_PROMPTS)
        )
        assert len(result.failed) == expected
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_pc_rp_runs_for_human() -> None:
    """RolePlayingValidator runs for human PC (no longer gated by is_llm_player)."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "fail"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore", is_llm_player=False)
        pc, npc, updater = _make_pc_npc_updater()
        result = asyncio.run(
            orch.validate_input(
                "x", source="pc", pc=pc, npc=npc, updater=updater, player_action="x",
            )
        )
        assert result is not None
        expected = (
            len(ai_client.ENGINE_VALIDATOR_PROMPTS)
            + len(ai_client.EXPLORE_GAME_PROMPTS)
            + len(ai_client.ROLEPLAYING_VALIDATOR_PROMPTS)
        )
        assert len(result.failed) == expected
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_pc_rp_runs_for_llm() -> None:
    """RolePlayingValidator runs for LLM PC as well — same rule set, no schema."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "fail"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore", is_llm_player=True)
        pc, npc, updater = _make_pc_npc_updater()
        result = asyncio.run(
            orch.validate_input(
                "x", source="pc", pc=pc, npc=npc, updater=updater, player_action="x",
            )
        )
        assert result is not None
        expected = (
            len(ai_client.ENGINE_VALIDATOR_PROMPTS)
            + len(ai_client.EXPLORE_GAME_PROMPTS)
            + len(ai_client.ROLEPLAYING_VALIDATOR_PROMPTS)
        )
        assert len(result.failed) == expected
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_validate_input_npc_all_pass() -> None:
    """validate_input(source='npc') returns None when all validators pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        pc, npc, updater = _make_pc_npc_updater()
        result = asyncio.run(
            orch.validate_input(
                '{"type": "ai", "content": "hello"}',
                source="npc", pc=pc, npc=npc, updater=updater, player_action="I wave.",
            )
        )
        assert result is None
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_format_ensemble_failures() -> None:
    """format_ensemble_failures produces expected output."""
    from dcs_simulation_engine.games.ai_client import (
        EnsembleValidationResult,
        ValidationResult,
        format_ensemble_failures,
    )

    result = EnsembleValidationResult(
        passed=False,
        results=[
            ValidationResult("RULE-A", False, "reason a"),
            ValidationResult("RULE-B", True, ""),
            ValidationResult("RULE-C", False, "reason c"),
        ],
        failed=[
            ValidationResult("RULE-A", False, "reason a"),
            ValidationResult("RULE-C", False, "reason c"),
        ],
    )
    msg = format_ensemble_failures(result)
    assert "[RULE-A] reason a" in msg
    assert "[RULE-C] reason c" in msg
    assert "RULE-B" not in msg


# ── ValidationOrchestrator + recorder tests ─────────────────────────


class _RecordedCall:
    """Captured record_ensemble_violations invocation."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _StubRecorder:
    """In-memory stub of ValidationEventRecorder.record_ensemble_violations."""

    def __init__(self) -> None:
        self.calls: list[_RecordedCall] = []

    async def record_ensemble_violations(self, **kwargs: Any) -> None:
        self.calls.append(_RecordedCall(**kwargs))


@pytest.mark.unit
def test_orchestrator_records_pc_human_violations_per_ensemble() -> None:
    """validate_input for a human PC records under event_source='pc_human'."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "no good"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore", is_llm_player=False)
        recorder = _StubRecorder()
        orch.attach_recorder(recorder, turn_index_provider=lambda: 7)  # type: ignore[arg-type]

        pc, npc, updater = _make_pc_npc_updater()

        result = asyncio.run(
            orch.validate_input(
                "bad text", source="pc", pc=pc, npc=npc, updater=updater,
                player_action="bad text",
            )
        )

        assert result is not None
        # All three ensembles fail now (role-playing runs regardless of character type).
        assert len(recorder.calls) == 3
        ensembles = {c.kwargs["ensemble_name"] for c in recorder.calls}
        assert ensembles == {"EngineValidator", "ExploreGameValidator", "RolePlayingValidator"}
        for call in recorder.calls:
            assert call.kwargs["event_source"] == "pc_human"
            assert call.kwargs["response"] == "bad text"
            assert call.kwargs["turn_index"] == 7
            assert len(call.kwargs["failed"]) > 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_records_pc_llm_violations_per_ensemble() -> None:
    """validate_input for an LLM PC records under event_source='pc_llm'."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "no good"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore", is_llm_player=True)
        recorder = _StubRecorder()
        orch.attach_recorder(recorder, turn_index_provider=lambda: 2)  # type: ignore[arg-type]

        pc, npc, updater = _make_pc_npc_updater()

        result = asyncio.run(
            orch.validate_input(
                "bad text", source="pc", pc=pc, npc=npc, updater=updater,
                player_action="bad text",
            )
        )

        assert result is not None
        assert {c.kwargs["event_source"] for c in recorder.calls} == {"pc_llm"}
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_records_nothing_when_all_pc_ensembles_pass() -> None:
    """No record_ensemble_violations calls when validation passes cleanly."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        recorder = _StubRecorder()
        orch.attach_recorder(recorder, turn_index_provider=lambda: 1)  # type: ignore[arg-type]

        pc, npc, updater = _make_pc_npc_updater()

        result = asyncio.run(
            orch.validate_input(
                "I wave.", source="pc", pc=pc, npc=npc, updater=updater,
                player_action="I wave.",
            )
        )

        assert result is None
        assert recorder.calls == []
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_records_npc_violations_with_unwrapped_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_validated_npc_response records failures per retry with unwrapped reply and event_source='npc_llm'."""
    ai_client.set_fake_ai_response('{"type":"ai","content":"reply-text"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        recorder = _StubRecorder()
        orch.attach_recorder(recorder, turn_index_provider=lambda: 4)  # type: ignore[arg-type]

        pc, npc, updater = _make_pc_npc_updater()

        fake_failed = [ai_client.ValidationResult(rule="RULE-X", passed=False, reason="bad")]

        async def failing_validate(
            text, *, source, pc, npc, updater, player_action="",
            skip_rules=frozenset(), response_text=None,
        ):
            await recorder.record_ensemble_violations(
                event_source=orch._event_source(source),
                ensemble_name="EngineValidator",
                failed=fake_failed,
                response=response_text if response_text is not None else text,
                turn_index=orch._turn_index(),
            )
            return ai_client.EnsembleValidationResult(
                passed=False, results=fake_failed, failed=fake_failed,
            )

        monkeypatch.setattr(orch, "validate_input", failing_validate)

        reply = asyncio.run(
            orch.generate_validated_npc_response("I wave.", pc=pc, npc=npc, updater=updater)
        )

        assert reply is None  # retry budget exhausted
        assert len(recorder.calls) == ai_client.ValidationOrchestrator.NPC_OUTPUT_RETRY_BUDGET
        for call in recorder.calls:
            assert call.kwargs["event_source"] == "npc_llm"
            assert call.kwargs["response"] == "reply-text"
            assert call.kwargs["turn_index"] == 4
    finally:
        ai_client.set_fake_ai_response(None)


# ── Opening scene skip-rules tests ────────────────────────────────


@pytest.mark.unit
def test_opening_scene_skip_rules_constant() -> None:
    """OPENING_SCENE_SKIP_RULES contains exactly the expected rules."""
    assert ai_client.OPENING_SCENE_SKIP_RULES == frozenset({
        "VALID-FORM",
        "VALID-TEMPORAL-STRUCTURE",
        "INVENTED-PC-ACTION",
        "ADJUDICATED-UNOBSERVABLE",
    })


@pytest.mark.unit
def test_ensemble_validate_skips_rules_in_skip_set() -> None:
    """EnsembleValidator.validate() auto-passes rules listed in skip_rules."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "would fail"}')
    try:
        v = ai_client.RolePlayingValidator.create()
        active_rules = set(ai_client.ROLEPLAYING_VALIDATOR_PROMPTS)
        skip = frozenset(active_rules & {"INVENTED-PC-ACTION", "ADJUDICATED-UNOBSERVABLE"})
        result = asyncio.run(v.validate("some text", skip_rules=skip))
        # Active rules: skipped ones auto-pass, the rest fail.
        assert len(result.results) == len(active_rules)
        skipped = [r for r in result.results if r.rule in skip]
        assert all(r.passed for r in skipped)
        non_skipped = [r for r in result.results if r.rule not in skip]
        assert all(not r.passed for r in non_skipped)
        assert len(result.failed) == len(active_rules) - len(skip)
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_ensemble_validate_skip_rules_empty_runs_all() -> None:
    """EnsembleValidator.validate() runs all rules when skip_rules is empty."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "fail"}')
    try:
        v = ai_client.EngineValidator.create()
        result = asyncio.run(v.validate("some text"))
        assert len(result.failed) == 1  # all 1 engine rule fails
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_validate_input_npc_opening_scene_skips_rules() -> None:
    """validate_input(source='npc') with OPENING_SCENE_SKIP_RULES auto-passes those rules."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "fail"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        pc, npc, updater = _make_pc_npc_updater()
        result = asyncio.run(
            orch.validate_input(
                '{"type": "ai", "content": "You enter a dimly lit room."}',
                source="npc", pc=pc, npc=npc, updater=updater, player_action="",
                skip_rules=ai_client.OPENING_SCENE_SKIP_RULES,
            )
        )
        assert result is not None
        assert result.passed is False
        failed_rules = {r.rule for r in result.failed}
        for skip_rule in ai_client.OPENING_SCENE_SKIP_RULES:
            assert skip_rule not in failed_rules
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_generate_validated_npc_response_passes_opening_scene_skip_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_validated_npc_response(None) forwards OPENING_SCENE_SKIP_RULES to validate_input."""
    ai_client.set_fake_ai_response('{"type":"ai","content":"You enter a room."}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        pc, npc, updater = _make_pc_npc_updater()

        captured: dict[str, Any] = {}

        async def mock_validate(
            text, *, source, pc, npc, updater, player_action="",
            skip_rules=frozenset(), response_text=None,
        ):
            captured["source"] = source
            captured["skip_rules"] = skip_rules
            captured["player_action"] = player_action
            return None  # all pass

        monkeypatch.setattr(orch, "validate_input", mock_validate)

        result = asyncio.run(
            orch.generate_validated_npc_response(None, pc=pc, npc=npc, updater=updater)
        )
        assert result is not None
        assert captured["source"] == "npc"
        assert captured["skip_rules"] == ai_client.OPENING_SCENE_SKIP_RULES
        assert captured["player_action"] == ""
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_generate_validated_npc_response_normal_turn_no_skip_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_validated_npc_response('I wave.') forwards an empty skip_rules set."""
    ai_client.set_fake_ai_response('{"type":"ai","content":"The creature waves back."}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        pc, npc, updater = _make_pc_npc_updater()

        captured: dict[str, Any] = {}

        async def mock_validate(
            text, *, source, pc, npc, updater, player_action="",
            skip_rules=frozenset(), response_text=None,
        ):
            captured["source"] = source
            captured["skip_rules"] = skip_rules
            captured["player_action"] = player_action
            return None

        monkeypatch.setattr(orch, "validate_input", mock_validate)

        result = asyncio.run(
            orch.generate_validated_npc_response("I wave.", pc=pc, npc=npc, updater=updater)
        )
        assert result is not None
        assert captured["source"] == "npc"
        assert captured["skip_rules"] == frozenset()
        assert captured["player_action"] == "I wave."
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_generate_validated_npc_response_records_schema_failure_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When _check_npc_schema reports failure, the response is recorded under NpcSchema and retried."""
    ai_client.set_fake_ai_response('{"type":"ai","content":"ignored"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        recorder = _StubRecorder()
        orch.attach_recorder(recorder, turn_index_provider=lambda: 9)  # type: ignore[arg-type]
        pc, npc, updater = _make_pc_npc_updater()

        forced_failure = ai_client.ValidationResult("VALID-SCHEMA", False, "forced")
        forced = ai_client.EnsembleValidationResult(
            passed=False, results=[forced_failure], failed=[forced_failure],
        )
        monkeypatch.setattr(ai_client, "_check_npc_schema", lambda _text: forced)

        async def should_not_run(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("validate_input should be skipped when schema fails")

        monkeypatch.setattr(orch, "validate_input", should_not_run)

        reply = asyncio.run(
            orch.generate_validated_npc_response("I wave.", pc=pc, npc=npc, updater=updater)
        )
        assert reply is None
        assert len(recorder.calls) == ai_client.ValidationOrchestrator.NPC_OUTPUT_RETRY_BUDGET
        for call in recorder.calls:
            assert call.kwargs["event_source"] == "npc_llm"
            assert call.kwargs["ensemble_name"] == ai_client.NPC_SCHEMA_ENSEMBLE
            assert call.kwargs["failed"][0].rule == "VALID-SCHEMA"
    finally:
        ai_client.set_fake_ai_response(None)


# ── Individual AtomicValidator violation tests ──────────────────────
#
# Each test instantiates one AtomicValidator with the real prompt,
# feeds it an obviously-violating input, and verifies the fail
# response propagates correctly.  The LLM is mocked so these serve
# as specification-by-example tests that document what each rule
# is designed to catch.
# ────────────────────────────────────────────────────────────────────


def _assert_atomic_fail(prompt: str, violation_text: str) -> None:
    """Helper: create an AtomicValidator, assert it returns (False, reason)."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "violation"}')
    try:
        v = ai_client.AtomicValidator(system_prompt=prompt)
        passed, reason = asyncio.run(v.validate(violation_text))
        assert passed is False
        assert reason == "violation"
    finally:
        ai_client.set_fake_ai_response(None)


# ── Engine validator individual rule tests (6 rules) ────────────────


@pytest.mark.unit
def test_engine_valid_form_rejects_internal_decision() -> None:
    """VALID-FORM rejects purely internal actions (deciding, wishing)."""
    _assert_atomic_fail(
        P.VALID_FORM_PROMPT,
        "I decide to be more careful next time.",
    )


@pytest.mark.unit
def test_engine_valid_observability_rejects_internal_inference() -> None:
    """VALID-OBSERVABILITY rejects unobservable mental conclusions."""
    _assert_atomic_fail(
        P.VALID_OBSERVABILITY_PROMPT,
        "I realize the door is locked.",
    )


@pytest.mark.unit
def test_engine_valid_outcome_control_rejects_decided_npc_reaction() -> None:
    """VALID-OUTCOME-CONTROL rejects player dictating NPC reactions."""
    _assert_atomic_fail(
        P.VALID_OUTCOME_CONTROL_PROMPT,
        "I look at the man. He looks back at me and smiles.",
    )


@pytest.mark.unit
def test_engine_valid_character_ability_rejects_impossible_action() -> None:
    """VALID-CHARACTER-ABILITY rejects actions beyond character capacity."""
    _assert_atomic_fail(
        P.VALID_CHARACTER_ABILITY_PROMPT,
        "I listen carefully for footsteps.",
    )


@pytest.mark.unit
def test_engine_valid_scene_plausibility_rejects_implausible_object() -> None:
    """VALID-SCENE-PLAUSIBILITY rejects clearly implausible objects."""
    _assert_atomic_fail(
        P.VALID_SCENE_PLAUSIBILITY_PROMPT,
        "I grab my lightsaber from the kitchen counter.",
    )


@pytest.mark.unit
def test_engine_valid_temporal_structure_rejects_time_compression() -> None:
    """VALID-TEMPORAL-STRUCTURE rejects multi-step time skips."""
    _assert_atomic_fail(
        P.VALID_TEMPORAL_STRUCTURE_PROMPT,
        "I spend the next hour searching every room in the building.",
    )


# ── RolePlayingLLM validator individual rule tests (11 LLM rules) ───


@pytest.mark.unit
def test_rp_role_break_meta_leakage_rejects_assistant_preamble() -> None:
    """ROLE-BREAK-META-LEAKAGE rejects meta-commentary / assistant preamble."""
    _assert_atomic_fail(
        P.ROLE_BREAK_META_LEAKAGE_PROMPT,
        "Sure! Here's the next scene: You see a faint glow emanating from the doorway.",
    )


@pytest.mark.unit
def test_rp_adjudicated_unobservable_rejects_resolved_thoughts() -> None:
    """ADJUDICATED-UNOBSERVABLE rejects resolving the player's internal thoughts."""
    _assert_atomic_fail(
        P.ADJUDICATED_UNOBSERVABLE_PROMPT,
        "You look around and conclude there's no trap here.",
    )


@pytest.mark.unit
def test_rp_invented_pc_action_rejects_added_actions() -> None:
    """INVENTED-PC-ACTION rejects the scene-advancer adding PC actions."""
    _assert_atomic_fail(
        P.INVENTED_PC_ACTION_PROMPT,
        "You knock on the door and then step back cautiously.",
    )


@pytest.mark.unit
def test_rp_invented_pc_internal_rejects_narrated_feelings() -> None:
    """INVENTED-PC-INTERNAL rejects narrating PC thoughts/feelings."""
    _assert_atomic_fail(
        P.INVENTED_PC_INTERNAL_PROMPT,
        "You open the chest excitedly, feeling a rush of anticipation.",
    )


@pytest.mark.unit
def test_rp_multi_step_advancement_rejects_chained_outcomes() -> None:
    """MULTI-STEP-ADVANCEMENT rejects multiple sequential outcomes."""
    _assert_atomic_fail(
        P.MULTI_STEP_ADVANCEMENT_PROMPT,
        "The creature lunges forward, misses, stumbles into the wall, and collapses unconscious.",
    )


@pytest.mark.unit
def test_rp_npc_perception_violation_rejects_impossible_perception() -> None:
    """NPC-PERCEPTION-VIOLATION rejects blind NPC seeing a visual gesture."""
    _assert_atomic_fail(
        P.NPC_PERCEPTION_VIOLATION_PROMPT,
        "The creature notices your wave and turns toward you.",
    )


@pytest.mark.unit
def test_rp_sense_boundary_violation_rejects_narrating_beyond_pc_senses() -> None:
    """SENSE-BOUNDARY-VIOLATION rejects narrating what a deaf PC hears."""
    _assert_atomic_fail(
        P.SENSE_BOUNDARY_VIOLATION_PROMPT,
        "The creature lets out a piercing shriek.",
    )


@pytest.mark.unit
def test_rp_referential_boundary_violation_rejects_hidden_identity() -> None:
    """REFERENTIAL-BOUNDARY-VIOLATION rejects revealing NPC's hidden species/identity."""
    _assert_atomic_fail(
        P.REFERENTIAL_BOUNDARY_VIOLATION_PROMPT,
        "The flatworm extends its body toward you.",
    )


@pytest.mark.unit
def test_rp_scene_continuity_violation_rejects_contradicted_state() -> None:
    """SCENE-CONTINUITY-VIOLATION rejects output contradicting established facts."""
    _assert_atomic_fail(
        P.SCENE_CONTINUITY_VIOLATION_PROMPT,
        "You see a painting hanging on the wall.",
    )


@pytest.mark.unit
def test_rp_physical_feasibility_violation_rejects_impossible_outcome() -> None:
    """PHYSICAL-FEASIBILITY-VIOLATION rejects physically impossible outcomes."""
    _assert_atomic_fail(
        P.PHYSICAL_FEASIBILITY_VIOLATION_PROMPT,
        "You lift the massive boulder over your head effortlessly.",
    )


@pytest.mark.unit
def test_rp_point_in_time_leakage_rejects_future_knowledge() -> None:
    """POINT-IN-TIME-LEAKAGE rejects revealing unavailable future information."""
    _assert_atomic_fail(
        P.POINT_IN_TIME_LEAKAGE_PROMPT,
        "The figure knows that the bridge ahead will collapse tomorrow.",
    )


# ── Game validator individual rule tests (7 rules) ──────────────────


@pytest.mark.unit
def test_game_no_objective_reference_rejects_winning() -> None:
    """GAME-NO-OBJECTIVE-REFERENCE rejects references to winning/quests."""
    _assert_atomic_fail(
        P.GAME_NO_OBJECTIVE_REFERENCE_PROMPT,
        "How do I win this game?",
    )


@pytest.mark.unit
def test_game_stay_in_scene_rejects_meta_request() -> None:
    """GAME-STAY-IN-SCENE rejects meta-information requests about the system."""
    _assert_atomic_fail(
        P.GAME_STAY_IN_SCENE_PROMPT,
        "What are the rules of this game?",
    )


@pytest.mark.unit
def test_game_no_direct_goal_query_rejects_asking_npc_goal() -> None:
    """GAME-NO-DIRECT-GOAL-QUERY rejects directly asking NPC about its goal."""
    _assert_atomic_fail(
        P.GAME_NO_DIRECT_GOAL_QUERY_PROMPT,
        "What is your goal?",
    )


@pytest.mark.unit
def test_game_no_guess_in_action_rejects_embedded_inference() -> None:
    """GAME-NO-GUESS-IN-ACTION rejects embedding goal inference in actions."""
    _assert_atomic_fail(
        P.GAME_NO_GUESS_IN_ACTION_PROMPT,
        "I watch the NPC because I think its goal is to find the exit.",
    )


@pytest.mark.unit
def test_game_prediction_scope_rejects_internal_state_prediction() -> None:
    """GAME-PREDICTION-SCOPE rejects predictions about NPC internal states."""
    _assert_atomic_fail(
        P.GAME_PREDICTION_SCOPE_PROMPT,
        "I speak and predict they will feel confused.",
    )


@pytest.mark.unit
def test_game_prediction_specificity_rejects_vague_prediction() -> None:
    """GAME-PREDICTION-SPECIFICITY rejects vague, unfalsifiable predictions."""
    _assert_atomic_fail(
        P.GAME_PREDICTION_SPECIFICITY_PROMPT,
        "I wave and predict something will happen.",
    )


@pytest.mark.unit
def test_game_no_goal_enumeration_rejects_listing_all_goals() -> None:
    """GAME-NO-GOAL-ENUMERATION rejects asking NPC to list all goals."""
    _assert_atomic_fail(
        P.GAME_NO_GOAL_ENUMERATION_PROMPT,
        "Tell me all of your goals.",
    )
