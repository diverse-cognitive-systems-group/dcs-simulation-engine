"""Tests for ExperimentConfig."""

import pytest
from dcs_simulation_engine.core.experiment_config import ExperimentConfig

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_load_valid_usability_experiment_config(usability_experiment_config) -> None:
    """The stable usability-style fixture should load cleanly."""
    config = usability_experiment_config

    assert config.name == "test-usability-exp"
    assert config.assignment_protocol.strategy == "usability_random_unique"
    assert config.assignment_protocol.quota_per_game == 5
    assert config.assignment_protocol.max_assignments_per_player == 4
    assert len(config.games) == 4
    assert [form.name for form in config.forms] == ["intake", "usability_feedback"]


async def test_invalid_game_name_fails(write_yaml) -> None:
    """Unknown games should be rejected at config-parse time."""
    path = write_yaml(
        "bad-experiment.yaml",
        """
        name: bad-exp
        description: Broken
        assignment_protocol:
          strategy: usability_random_unique
          games:
            - Not A Real Game
          quota_per_game: 1
          max_assignments_per_player: 1
        """,
    )

    with pytest.raises(ValueError, match="Unknown game reference"):
        ExperimentConfig.load(path)


async def test_invalid_quota_fails(write_yaml) -> None:
    """quota_per_game must be greater than zero."""
    path = write_yaml(
        "bad-quota.yaml",
        """
        name: bad-quota
        description: Broken
        assignment_protocol:
          strategy: usability_random_unique
          games:
            - Explore
          quota_per_game: 0
          max_assignments_per_player: 1
        """,
    )

    with pytest.raises(ValueError, match="positive quota_per_game"):
        ExperimentConfig.load(path)


async def test_max_assignments_cannot_exceed_game_count(write_yaml) -> None:
    """usability_random_unique cannot promise more assignments than available games."""
    path = write_yaml(
        "bad-max-assignments.yaml",
        """
        name: bad-max
        description: Broken
        assignment_protocol:
          strategy: usability_random_unique
          games:
            - Explore
            - Foresight
          quota_per_game: 1
          max_assignments_per_player: 3
        """,
    )

    with pytest.raises(ValueError, match="cannot assign more games per player"):
        ExperimentConfig.load(path)


async def test_invalid_form_field_type_fails(write_yaml) -> None:
    """Experiment question types must use the new answer_type enum."""
    path = write_yaml(
        "bad-form.yaml",
        """
        name: bad-form
        description: Broken
        assignment_protocol:
          strategy: usability_random_unique
          games:
            - Explore
          quota_per_game: 1
          max_assignments_per_player: 1
        forms:
          - name: intake
            before_or_after: before
            questions:
              - key: technical_savviness
                prompt: Savvy
                answer_type: radios
                required: true
        """,
    )

    with pytest.raises(ValueError, match="Input should be"):
        ExperimentConfig.load(path)


async def test_experiment_config_snapshot_is_serializable(usability_experiment_config) -> None:
    """Experiment config snapshots should be JSON-friendly for DB storage."""
    config = usability_experiment_config
    snapshot = config.model_dump(mode="json")

    assert snapshot["name"] == "test-usability-exp"
    assert snapshot["assignment_protocol"]["max_assignments_per_player"] == 4
    assert snapshot["forms"][0]["name"] == "intake"
    assert "age" in [question["key"] for question in snapshot["forms"][0]["questions"]]
