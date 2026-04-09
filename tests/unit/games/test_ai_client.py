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


# ── GameValidator tests ─────────────────────────────────────────────


@pytest.mark.unit
def test_game_validator_for_game_returns_correct_class() -> None:
    """GameValidator.for_game returns the right subclass for each game."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        assert isinstance(ai_client.GameValidator.for_game("Explore"), ai_client.ExploreGameValidator)
        assert isinstance(ai_client.GameValidator.for_game("infer intent"), ai_client.InferIntentGameValidator)
        assert isinstance(ai_client.GameValidator.for_game("Foresight"), ai_client.ForesightGameValidator)
        assert isinstance(ai_client.GameValidator.for_game("goal horizon"), ai_client.GoalHorizonGameValidator)
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_game_validator_for_game_unknown_raises() -> None:
    """GameValidator.for_game raises ValueError for unknown game names."""
    with pytest.raises(ValueError, match="No GameValidator registered"):
        ai_client.GameValidator.for_game("nonexistent game")


@pytest.mark.unit
def test_explore_game_validator_all_pass() -> None:
    """ExploreGameValidator reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.ExploreGameValidator.create()
        result = asyncio.run(v.validate("I wave at the creature."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_infer_intent_game_validator_all_pass() -> None:
    """InferIntentGameValidator reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.InferIntentGameValidator.create()
        result = asyncio.run(v.validate("I watch the creature carefully."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_foresight_game_validator_all_pass() -> None:
    """ForesightGameValidator reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.ForesightGameValidator.create()
        result = asyncio.run(v.validate("I wave and predict they will wave back."))
        assert result.passed is True
        assert len(result.results) == 2
        assert len(result.failed) == 0
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_goal_horizon_game_validator_all_pass() -> None:
    """GoalHorizonGameValidator reports passed=True when all 2 rules pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        v = ai_client.GoalHorizonGameValidator.create()
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
        v = ai_client.ExploreGameValidator.create()
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
        assert isinstance(orch._game, ai_client.ExploreGameValidator)
        assert isinstance(orch._roleplaying, ai_client.RolePlayingLLMValidator)
        assert orch.is_llm_player is False
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_pc_input_all_pass() -> None:
    """validate_pc_input returns None when all validators pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        from dcs_simulation_engine.dal.base import CharacterRecord

        pc = CharacterRecord(hid="pc1", name="PC", short_description="a player", data={"abilities": "can see"})
        npc = CharacterRecord(hid="npc1", name="NPC", short_description="a creature", data={"abilities": "can move"})
        updater = ai_client.UpdaterClient(system_prompt="test")
        result = asyncio.run(orch.validate_pc_input("I wave.", pc=pc, npc=npc, updater=updater))
        assert result is None
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_pc_input_fail_propagates() -> None:
    """validate_pc_input returns merged failures when validators fail."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "invalid"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        from dcs_simulation_engine.dal.base import CharacterRecord

        pc = CharacterRecord(hid="pc1", name="PC", short_description="a player", data={"abilities": "can see"})
        npc = CharacterRecord(hid="npc1", name="NPC", short_description="a creature", data={"abilities": "can move"})
        updater = ai_client.UpdaterClient(system_prompt="test")
        result = asyncio.run(orch.validate_pc_input("bad input", pc=pc, npc=npc, updater=updater))
        assert result is not None
        assert result.passed is False
        # Engine (6 rules) + Game (2 rules) = 8 failures
        assert len(result.failed) == 8
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_pc_rp_skipped_for_human() -> None:
    """RolePlayingLLMValidator is NOT invoked for human players (is_llm_player=False)."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "fail"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore", is_llm_player=False)
        from dcs_simulation_engine.dal.base import CharacterRecord

        pc = CharacterRecord(hid="pc1", name="PC", short_description="a player", data={"abilities": "can see"})
        npc = CharacterRecord(hid="npc1", name="NPC", short_description="a creature", data={"abilities": "can move"})
        updater = ai_client.UpdaterClient(system_prompt="test")
        result = asyncio.run(orch.validate_pc_input("x", pc=pc, npc=npc, updater=updater))
        assert result is not None
        # Only Engine (6) + Game (2) = 8, NOT 8 + 11 roleplaying
        assert len(result.failed) == 8
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_pc_rp_included_for_llm() -> None:
    """RolePlayingLLMValidator IS invoked for LLM players (is_llm_player=True)."""
    ai_client.set_fake_ai_response('{"pass": false, "reason": "fail"}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore", is_llm_player=True)
        from dcs_simulation_engine.dal.base import CharacterRecord

        pc = CharacterRecord(hid="pc1", name="PC", short_description="a player", data={"abilities": "can see"})
        npc = CharacterRecord(hid="npc1", name="NPC", short_description="a creature", data={"abilities": "can move"})
        updater = ai_client.UpdaterClient(system_prompt="test")
        result = asyncio.run(orch.validate_pc_input("x", pc=pc, npc=npc, updater=updater))
        assert result is not None
        # Engine (6) + Game (2) + RolePlayingLLM (11 LLM + 1 schema) = 20
        # But schema is a pre-check on the raw text "x", which will fail too
        assert len(result.failed) == 20
    finally:
        ai_client.set_fake_ai_response(None)


@pytest.mark.unit
def test_orchestrator_npc_output_all_pass() -> None:
    """validate_npc_output returns None when all validators pass."""
    ai_client.set_fake_ai_response('{"pass": true}')
    try:
        orch = ai_client.ValidationOrchestrator.create("explore")
        from dcs_simulation_engine.dal.base import CharacterRecord

        pc = CharacterRecord(hid="pc1", name="PC", short_description="a player", data={"abilities": "can see"})
        npc = CharacterRecord(hid="npc1", name="NPC", short_description="a creature", data={"abilities": "can move"})
        updater = ai_client.UpdaterClient(system_prompt="test")
        result = asyncio.run(
            orch.validate_npc_output(
                '{"type": "ai", "content": "hello"}',
                pc=pc, npc=npc, updater=updater, player_action="I wave.",
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
