"""API contract tests for every real example run config."""

import asyncio
from pathlib import Path

import pytest
from dcs_simulation_engine.core.run_config import RunConfig, validate_run_config_references
from tests.functional.example_run_config_helpers import (
    RUN_CONFIG_FILES,
    example_client,
    load_run_config,
    run_config_ids,
)

pytestmark = pytest.mark.functional


@pytest.mark.parametrize("config_path", RUN_CONFIG_FILES, ids=run_config_ids)
def test_example_run_config_boots_api_and_persists_run(config_path: Path, async_mongo_provider) -> None:
    """Every example config should load, validate, boot the API, and persist its run snapshot."""
    config = RunConfig.load(config_path)
    validate_run_config_references(config)

    with example_client(async_mongo_provider, config) as client:
        response = client.get("/api/server/config")
        assert response.status_code == 200, response.text
        server_config = response.json()

    assert server_config["default_experiment_name"] == config.name
    assert server_config["registration_enabled"] is config.registration_required
    assert server_config["authentication_required"] is config.registration_required

    persisted = asyncio.run(async_mongo_provider.get_experiment(experiment_name=config.name))
    assert persisted is not None
    config_snapshot = persisted.data["config_snapshot"]
    assert config_snapshot["name"] == config.name
    assert [game["name"] for game in config_snapshot["games"]] == config.game_names


def test_demo_run_config_contract() -> None:
    """Demo is anonymous, form-free, and exposes full character access."""
    config = load_run_config("demo")

    assert config.registration_required is False
    assert config.forms == []
    assert config.assignment_strategy.strategy == "full_character_access"
    assert config.assignment_strategy.allow_choice_if_multiple is True
    assert config.assignment_strategy.require_completion is False
    assert config.game_names == ["Explore", "Infer Intent", "Foresight", "Goal Horizon", "Teamwork"]


def test_benchmark_ai_run_config_contract() -> None:
    """Benchmark AI is a headless model-player run, not a human participant flow."""
    config = load_run_config("benchmark-ai")

    assert config.has_model_players is True
    assert config.players.humans.all is False
    assert config.ui.launch_gui is False
    assert config.forms == []
    assert config.assignment_strategy.strategy == "next_incomplete_combination"


def test_benchmark_humans_run_config_contract() -> None:
    """Benchmark humans requires registration and entry/outtake forms."""
    config = load_run_config("benchmark-humans")

    assert config.registration_required is True
    assert config.forms_for_trigger(event="before_all_assignments")
    assert config.forms_for_trigger(event="after_all_assignments")
    assert config.assignment_strategy.strategy == "next_incomplete_combination"
    assert config.assignment_strategy.require_completion is True


def test_usability_run_config_contract() -> None:
    """Usability includes entry, per-assignment, and outtake feedback."""
    config = load_run_config("usability")

    assert config.registration_required is True
    assert config.forms_for_trigger(event="before_all_assignments")
    assert config.forms_for_trigger(event="after_assignment")
    assert config.forms_for_trigger(event="after_all_assignments")
    assert config.assignment_strategy.strategy == "full_character_access"
    assert config.assignment_strategy.allow_choice_if_multiple is True


def test_expert_evaluation_run_config_contract() -> None:
    """Expert evaluation must collect expertise before resolving matched assignments."""
    config = load_run_config("expert-evaluation")

    initial_forms = config.forms_for_trigger(event="before_all_assignments")
    question_keys = {question.key for form in initial_forms for question in form.questions}

    assert "expertise" in question_keys
    assert config.assignment_strategy.strategy == "expertise_matched_character_batch"
    assert config.assignment_strategy.require_completion is True


def test_training_run_config_contract() -> None:
    """Training is a registered Teamwork-only run with entry consent."""
    config = load_run_config("training")

    assert config.registration_required is True
    assert config.game_names == ["Teamwork"]
    assert config.forms_for_trigger(event="before_all_assignments")
    assert config.assignment_strategy.strategy == "unplayed_combination_choice"
    assert config.assignment_strategy.allow_choice_if_multiple is True


def test_select_characters_run_config_contract() -> None:
    """Select Characters is anonymous and constrains character filters through overrides."""
    config = load_run_config("select-characters")

    assert config.registration_required is False
    assert config.assignment_strategy.strategy == "full_character_access"
    assert config.assignment_strategy.allow_choice_if_multiple is True
    assert {game.overrides.get("pcs_allowed") for game in config.games} == {"human-normative"}
    assert {game.overrides.get("npcs_allowed") for game in config.games} == {"neurodivergent"}
