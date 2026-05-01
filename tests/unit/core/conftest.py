"""Conftest fixtures for core tests."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator

import pytest
from dcs_simulation_engine.core.engine_run_manager import EngineRunManager
from dcs_simulation_engine.core.run_config import RunConfig


@pytest.fixture
def game_config_minimal(write_yaml: Callable[[Path, str], Path], tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
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
def usability_run_config_path(write_yaml: Callable[[str, str], Path]) -> Path:
    """Create a stable run config fixture for core tests."""
    return write_yaml(
        "test-usability-run.yaml",
        """
        name: test-usability-run
        description: Stable fixture for run tests.
        games:
          - name: Explore
          - name: Infer Intent
          - name: Foresight
          - name: Goal Horizon
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 5
            max_assignments_per_player: 1
            seed: test-usability-seed
        forms:
          - name: intake
            trigger:
              event: before_all_assignments
              match: null
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
            trigger:
              event: after_assignment
              match: null
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
def usability_run_config(usability_run_config_path: Path) -> RunConfig:
    """Load the stable run config fixture."""
    return RunConfig.load(usability_run_config_path)


@pytest.fixture
def cached_usability_run(usability_run_config: RunConfig) -> Iterator[RunConfig]:
    """Register the stable run config in the EngineRunManager."""
    original_config = EngineRunManager._run_config
    EngineRunManager._run_config = usability_run_config
    try:
        yield usability_run_config
    finally:
        EngineRunManager._run_config = original_config


@pytest.fixture
def multi_assignment_run_config_path(write_yaml: Callable[[str, str], Path]) -> Path:
    """Run config fixture with max_assignments_per_player: 3."""
    return write_yaml(
        "test-multi-assignment-run.yaml",
        """
        name: test-multi-assignment-run
        description: Fixture for multi-assignment progress tests.
        games:
          - name: Explore
          - name: Infer Intent
          - name: Foresight
        next_game_strategy:
          strategy:
            id: random_unique_game
            quota_per_game: 10
            max_assignments_per_player: 3
            seed: test-multi-seed
        forms:
          - name: intake
            trigger:
              event: before_all_assignments
              match: null
            questions:
              - key: age
                prompt: Age
                answer_type: number
                required: true
          - name: usability_feedback
            trigger:
              event: after_assignment
              match: null
            questions:
              - key: usability_issues
                prompt: Any issues?
                answer_type: string
              - key: positive_usability
                prompt: What worked well?
                answer_type: string
              - key: bugs_or_issues
                prompt: Bugs?
                answer_type: string
              - key: experience_preferences
                prompt: Experience?
                answer_type: string
              - key: additional_feedback
                prompt: Other feedback?
                answer_type: string
        """,
    )


@pytest.fixture
def cached_multi_assignment_run(
    multi_assignment_run_config_path: Path,
) -> Iterator[RunConfig]:
    """Register the multi-assignment run config in the EngineRunManager."""
    config = RunConfig.load(multi_assignment_run_config_path)
    original_config = EngineRunManager._run_config
    EngineRunManager._run_config = config
    try:
        yield config
    finally:
        EngineRunManager._run_config = original_config
