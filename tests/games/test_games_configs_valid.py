"""Tests that all game configs in the games/ directory are valid.

This module discovers every YAML file under ./games and verifies that each
one can be loaded by `GameConfig.load_from_yaml(...)`. Each file is shown
as a separate pytest case (pass/fail) via parametrization.
"""

from pathlib import Path

import pytest
from dcs_simulation_engine.core.game_config import (
    GameConfig,
)
from helpers import discover_yaml_files
from loguru import logger

YAML_FILES = discover_yaml_files()


@pytest.mark.unit
def test_games_directory_not_empty() -> None:
    """Test that there is at least one YAML file under ./games."""
    logger.debug(f"Discovered game config files: {YAML_FILES!r}")
    assert YAML_FILES, "No YAML files found under ./games. Add configs to test."


@pytest.mark.unit
@pytest.mark.parametrize("cfg_path", YAML_FILES, ids=[p.name for p in YAML_FILES])
def test_game_config_loads_without_error(cfg_path: Path) -> None:
    """Test that a game config YAML file can be loaded without error."""
    try:
        logger.debug(f"Loading game config from: {cfg_path}")
        cfg = GameConfig.load(str(cfg_path))
        logger.debug(f"Loaded game config: {cfg.name}")
    except Exception as exc:
        pytest.fail(f"Failed to load game config: {cfg_path}\n{exc!r}")
