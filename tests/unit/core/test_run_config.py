"""Unit tests for run config schema behavior."""

import pytest
from dcs_simulation_engine.core.run_config import RunConfig, validate_run_config_references
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def _minimal_config() -> dict:
    return {
        "name": "Test Run",
        "next_game_strategy": {
            "strategy": {
                "id": "full_character_access",
            }
        },
    }


def test_run_config_rejects_unknown_top_level_fields() -> None:
    """Run config schema should fail loudly on unknown top-level keys."""
    payload = {**_minimal_config(), "not_a_real_field": True}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunConfig.model_validate(payload)


def test_run_config_rejects_unknown_nested_fields() -> None:
    """Nested sections should forbid unknown keys except strategy params."""
    payload = _minimal_config()
    payload["ui"] = {"launch_gui": True, "theme": "dark"}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RunConfig.model_validate(payload)


def test_run_config_preserves_strategy_specific_params() -> None:
    """Assignment strategy params should flow through the strategy object."""
    payload = _minimal_config()
    payload["next_game_strategy"]["strategy"]["allow_choice_if_multiple"] = True
    payload["next_game_strategy"]["strategy"]["require_completion"] = False

    config = RunConfig.model_validate(payload)

    dumped = config.next_game_strategy.strategy.model_dump()
    assert dumped["allow_choice_if_multiple"] is True
    assert dumped["require_completion"] is False


def test_run_config_null_forms_normalize_to_empty_list() -> None:
    """forms: null should mean no configured forms."""
    payload = {**_minimal_config(), "forms": None}

    config = RunConfig.model_validate(payload)

    assert config.forms == []


def test_run_config_rejects_duplicate_form_names() -> None:
    """Duplicate form names should fail after form-name normalization."""
    payload = {
        **_minimal_config(),
        "forms": [
            {
                "name": "Intake",
                "trigger": {"event": "before_all_assignments", "match": None},
                "questions": [{"prompt": "First message."}],
            },
            {
                "name": "intake",
                "trigger": {"event": "after_all_assignments", "match": None},
                "questions": [{"prompt": "Second message."}],
            },
        ],
    }

    with pytest.raises(ValidationError, match="form names must be unique"):
        RunConfig.model_validate(payload)


def test_run_config_reference_validation_rejects_invalid_override_keys() -> None:
    """Static validation should delegate override key validation to each game."""
    config = RunConfig.model_validate(
        {
            **_minimal_config(),
            "games": [
                {
                    "name": "Explore",
                    "overrides": {"not_a_real_override": True},
                }
            ],
        }
    )

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_run_config_references(config)


def test_run_config_reference_validation_rejects_unknown_games() -> None:
    """Static validation should reject game names that do not resolve."""
    config = RunConfig.model_validate(
        {
            **_minimal_config(),
            "games": [{"name": "No Such Game"}],
        }
    )

    with pytest.raises(FileNotFoundError, match="No game config matching"):
        validate_run_config_references(config)


def test_run_config_reference_validation_rejects_unknown_strategies() -> None:
    """Static validation should reject strategy ids that do not resolve."""
    payload = _minimal_config()
    payload["next_game_strategy"]["strategy"]["id"] = "no_such_strategy"
    config = RunConfig.model_validate(payload)

    with pytest.raises(ValueError, match="Unknown assignment strategy"):
        validate_run_config_references(config)
