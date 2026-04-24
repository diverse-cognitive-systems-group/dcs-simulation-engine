"""Functional tests for example run config files.

All tests in this file are xfailed pending run config refactoring.

Once the run config refactor is complete, these tests should:
- Parse every YAML in examples/run_configs/ without error
- Validate player filtering (all players, specific human players, AI models)
- Validate per-game overrides are applied correctly

The parametrized test_example_run_config_is_parseable test is structured
to automatically pick up any new configs added to examples/run_configs/.
"""

import glob
from pathlib import Path

import pytest

pytestmark = [pytest.mark.functional, pytest.mark.xfail(reason="pending run config refactor — not yet implemented")]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_GLOB = str(_REPO_ROOT / "examples" / "run_configs" / "*.yml")
_CONFIG_FILES = sorted(glob.glob(_CONFIG_GLOB))


# @pytest.mark.parametrize(
#     "config_path",
#     _CONFIG_FILES,
#     ids=lambda p: Path(p).stem,
# )
# def test_example_run_config_is_parseable(config_path):
#     """Each example run config YAML should load and parse without error."""
#     ...


# @pytest.mark.parametrize(
#     "config_path",
#     _CONFIG_FILES,
#     ids=lambda p: Path(p).stem,
# )
# def test_run_config_allows_all_players(config_path):
#     """Run config with no player filter should allow any registered player."""
#     ...


# @pytest.mark.parametrize(
#     "config_path",
#     _CONFIG_FILES,
#     ids=lambda p: Path(p).stem,
# )
# def test_run_config_allows_only_specific_human_players(config_path):
#     """Run config with a player allowlist should restrict access correctly."""
#     ...

# @pytest.mark.parametrize(
#     "config_path",
#     _CONFIG_FILES,
#     ids=lambda p: Path(p).stem,
# )
# def test_run_config_runs_specific_ai_players(config_path):
#     """Run config that specifies AI model players should execute them correctly."""
#     ...

# @pytest.mark.parametrize(
#     "config_path",
#     _CONFIG_FILES,
#     ids=lambda p: Path(p).stem,
# )
# def test_run_config_per_game_overrides(config_path):
#     """Per-game overrides in run config should be applied to the session."""
#     ...
