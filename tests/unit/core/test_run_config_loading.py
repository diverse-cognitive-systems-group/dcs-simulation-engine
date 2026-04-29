"""Tests for RunConfig."""

import pytest
from dcs_simulation_engine.core.run_config import RunConfig, validate_run_config_references

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_load_valid_usability_experiment_config(usability_experiment_config) -> None:
    """The stable usability-style fixture should load cleanly."""
    config = usability_experiment_config

    assert config.name == "test-usability-exp"
    assert config.assignment_strategy.strategy == "random_unique_game"
    assert config.assignment_strategy.quota_per_game == 5
    assert config.assignment_strategy.max_assignments_per_player == 1
    assert config.assignment_strategy.allow_choice_if_multiple is False
    assert config.assignment_strategy.require_completion is True
    assert len(config.games) == 4
    assert [form.name for form in config.forms] == ["intake", "usability_feedback"]
    assert config.forms[0].trigger.event == "before_all_assignments"
    assert config.forms[1].trigger.event == "after_assignment"


async def test_legacy_assignment_protocol_key_is_rejected(write_yaml) -> None:
    """Configs must use next_game_strategy and should not accept the old key."""
    path = write_yaml(
        "legacy-experiment.yaml",
        """
        name: legacy-exp
        description: Broken
        assignment_protocol:
          strategy: random_unique_game
          games:
            - Explore
          quota_per_game: 1
          max_assignments_per_player: 1
        """,
    )

    with pytest.raises(ValueError, match="Unknown field at `assignment_protocol`"):
        RunConfig.load(path)


async def test_invalid_game_name_fails(write_yaml) -> None:
    """Unknown games should be rejected by static reference validation."""
    path = write_yaml(
        "bad-experiment.yaml",
        """
        name: bad-exp
        description: Broken
        games:
          - name: Not A Real Game
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 1
            max_assignments_per_player: 1
        """,
    )

    config = RunConfig.load(path)
    with pytest.raises(FileNotFoundError, match="No game config matching"):
        validate_run_config_references(config)


async def test_assignment_policy_fields_use_run_config_names(write_yaml) -> None:
    """Configs should expose require_completion and allow_choice_if_multiple."""
    path = write_yaml(
        "assignment-policy-fields.yaml",
        """
        name: assignment-policy-fields
        description: Policy field fixture
        games:
          - name: Explore
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 1
            max_assignments_per_player: 1
            allow_choice_if_multiple: true
            require_completion: false
        """,
    )

    config = RunConfig.load(path)

    assert config.assignment_strategy.allow_choice_if_multiple is True
    assert config.assignment_strategy.require_completion is False


async def test_invalid_quota_fails(write_yaml) -> None:
    """quota_per_game must be greater than zero."""
    path = write_yaml(
        "bad-quota.yaml",
        """
        name: bad-quota
        description: Broken
        games:
          - name: Explore
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 0
            max_assignments_per_player: 1
        """,
    )

    config = RunConfig.load(path)
    with pytest.raises(ValueError, match="positive quota_per_game"):
        validate_run_config_references(config)


async def test_max_assignments_cannot_exceed_game_count(write_yaml) -> None:
    """random_unique_game cannot promise more assignments than available games."""
    path = write_yaml(
        "bad-max-assignments.yaml",
        """
        name: bad-max
        description: Broken
        games:
          - name: Explore
          - name: Foresight
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 1
            max_assignments_per_player: 3
        """,
    )

    config = RunConfig.load(path)
    with pytest.raises(ValueError, match="cannot assign more games per player"):
        validate_run_config_references(config)


async def test_invalid_form_field_type_fails(write_yaml) -> None:
    """Experiment question types must use the new answer_type enum."""
    path = write_yaml(
        "bad-form.yaml",
        """
        name: bad-form
        description: Broken
        games:
          - name: Explore
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 1
            max_assignments_per_player: 1
        forms:
          - name: intake
            trigger:
              event: before_all_assignments
              match: null
            questions:
              - key: technical_savviness
                prompt: Savvy
                answer_type: radios
                required: true
        """,
    )

    with pytest.raises(ValueError, match="Input should be"):
        RunConfig.load(path)


async def test_unknown_form_trigger_event_is_rejected(write_yaml) -> None:
    """Only registered form trigger events are accepted."""
    path = write_yaml(
        "unknown-form-trigger.yaml",
        """
        name: unknown-form-trigger
        description: Broken
        games:
          - name: Explore
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 1
            max_assignments_per_player: 1
        forms:
          - name: intake
            trigger:
              event: before_everything
              match: null
            questions: []
        """,
    )

    with pytest.raises(ValueError, match="before_all_assignments"):
        RunConfig.load(path)


async def test_form_trigger_match_must_be_null(write_yaml) -> None:
    """Current built-in triggers do not accept match filters."""
    path = write_yaml(
        "matched-form-trigger.yaml",
        """
        name: matched-form-trigger
        description: Broken
        games:
          - name: Explore
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 1
            max_assignments_per_player: 1
        forms:
          - name: intake
            trigger:
              event: before_all_assignments
              match:
                game: Explore
            questions: []
        """,
    )

    with pytest.raises(ValueError, match="match must be null"):
        RunConfig.load(path)


async def test_experiment_config_snapshot_is_serializable(usability_experiment_config) -> None:
    """Experiment config snapshots should be JSON-friendly for DB storage."""
    config = usability_experiment_config
    snapshot = config.model_dump(mode="json")

    assert snapshot["name"] == "test-usability-exp"
    assert snapshot["next_game_strategy"]["strategy"]["max_assignments_per_player"] == 1
    assert snapshot["forms"][0]["name"] == "intake"
    assert snapshot["forms"][0]["trigger"] == {"event": "before_all_assignments", "match": None}
    assert "age" in [question["key"] for question in snapshot["forms"][0]["questions"]]
