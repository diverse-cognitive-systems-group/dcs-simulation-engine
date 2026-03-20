"""Conftest fixtures for core tests."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator

import pytest
from dcs_simulation_engine.core.experiment_config import ExperimentConfig
from dcs_simulation_engine.core.experiment_manager import ExperimentManager


@pytest.fixture
def game_config_minimal(
    write_yaml: Callable[[Path, str], Path], tmp_path_factory: pytest.TempPathFactory
) -> SimpleNamespace:
    """Fixture for a minimal base GameConfig."""
    base = tmp_path_factory.mktemp("cfg_minimal")
    game_config_yaml = """
    name: Minimal Test Game Config
    version: 1.0.0
    description: A minimal game config for testing.
    game_class: dcs_simulation_engine.games.explore.ExploreGame
    """
    game_config_path = base / "game_config_minimal.yaml"
    write_yaml(game_config_path, game_config_yaml)
    return SimpleNamespace(path=game_config_path)


@pytest.fixture
def usability_experiment_config_path(write_yaml: Callable[[str, str], Path]) -> Path:
    """Create a stable experiment config fixture for core tests."""
    return write_yaml(
        "test-usability-experiment.yaml",
        """
        name: test-usability-exp
        description: Stable fixture for experiment tests.
        assignment_strategy:
          strategy: random_unique
          games:
            - Explore
            - Infer Intent
            - Foresight
            - Goal Horizon
          quota_per_game: 5
          max_assignments_per_player: 1
          seed: test-usability-seed
        forms:
          - name: intake
            before_or_after: before
            questions:
              - prompt: Please complete the intake form.
              - key: age
                prompt: Age
                answer_type: number
                required: true
              - key: technical_experience
                prompt: Technical Experience
                answer_type: multi_choice
                options:
                  - Casual computer user
                  - Regular gamer
                  - Competitive / experienced gamer
                  - Programming or scripting experience
                  - Software engineer / developer
                  - Data science / machine learning
                  - IT / system administration
                  - Technical researcher or engineer
                  - Other technical background
              - key: technical_savviness
                prompt: How technically savvy do you consider yourself?
                answer_type: single_choice
                required: true
                options:
                  - Low
                  - Medium
                  - High
              - key: technical_experience_details
                prompt: Briefly describe your technical experience
                answer_type: string
          - name: usability_feedback
            before_or_after: after
            questions:
              - prompt: Please share any usability feedback.
              - key: usability_issues
                prompt: Were any parts of the interface confusing or difficult to use?
                answer_type: string
              - key: positive_usability
                prompt: Were there parts of the interface that worked especially well?
                answer_type: string
              - key: bugs_or_issues
                prompt: Did you encounter any bugs or technical issues?
                answer_type: string
              - key: experience_preferences
                prompt: What did you enjoy or dislike about the overall experience?
                answer_type: string
              - key: additional_feedback
                prompt: Anything else you would like to share?
                answer_type: string
        """,
    )


@pytest.fixture
def usability_experiment_config(usability_experiment_config_path: Path) -> ExperimentConfig:
    """Load the stable experiment config fixture."""
    return ExperimentConfig.load(usability_experiment_config_path)


@pytest.fixture
def cached_usability_experiment(usability_experiment_config: ExperimentConfig) -> Iterator[ExperimentConfig]:
    """Register the stable experiment config in the ExperimentManager cache."""
    original_cache = ExperimentManager._experiment_config_cache.copy()
    ExperimentManager._experiment_config_cache = {
        ExperimentManager._cache_key(usability_experiment_config.name): usability_experiment_config
    }
    try:
        yield usability_experiment_config
    finally:
        ExperimentManager._experiment_config_cache = original_cache
