"""Functional tests for example run config files."""

from pathlib import Path

import pytest
from dcs_simulation_engine.core.run_config import RunConfig, validate_run_config_references

pytestmark = pytest.mark.functional

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_FILES = sorted((_REPO_ROOT / "examples" / "run_configs").glob("*.yml"))


@pytest.mark.parametrize("config_path", _CONFIG_FILES, ids=lambda p: p.stem)
def test_example_run_config_is_parseable(config_path: Path) -> None:
    """Each example run config YAML should load and parse without error."""
    assert RunConfig.load(config_path).name


@pytest.mark.parametrize("config_path", _CONFIG_FILES, ids=lambda p: p.stem)
def test_example_run_config_references_are_valid(config_path: Path) -> None:
    """Each example should reference known games, strategies, and game overrides."""
    validate_run_config_references(RunConfig.load(config_path))


def test_demo_run_config_is_anonymous() -> None:
    """Demo is intentionally configured as a no-registration human run."""
    config = RunConfig.load(_REPO_ROOT / "examples" / "run_configs" / "demo.yml")

    assert config.registration_required is False


def test_benchmark_ai_run_config_has_model_players() -> None:
    """Benchmark AI config should expose configured model players."""
    config = RunConfig.load(_REPO_ROOT / "examples" / "run_configs" / "benchmark-ai.yml")

    assert config.has_model_players is True


def test_run_config_game_names_preserve_config_order() -> None:
    """Game order should match the source config declaration order."""
    config = RunConfig.load(_REPO_ROOT / "examples" / "run_configs" / "demo.yml")

    assert config.game_names == [
        "Explore",
        "Infer Intent",
        "Foresight",
        "Goal Horizon",
        "Teamwork",
    ]
