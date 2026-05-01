"""Tests that all built-in game configs are valid."""

import pytest
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from loguru import logger

BUILTIN_GAME_CLASSES = list(SessionManager._builtin_game_classes().values())


@pytest.mark.unit
def test_builtin_games_not_empty() -> None:
    """Test that there is at least one built-in game class."""
    logger.debug(f"Discovered built-in game classes: {BUILTIN_GAME_CLASSES!r}")
    assert BUILTIN_GAME_CLASSES, "No built-in game classes found. Add games to test."


@pytest.mark.unit
@pytest.mark.parametrize("game_cls", BUILTIN_GAME_CLASSES, ids=[game.GAME_NAME for game in BUILTIN_GAME_CLASSES])
def test_game_config_loads_without_error(game_cls) -> None:
    """Test that a built-in game class can produce a valid GameConfig."""
    try:
        logger.debug(f"Loading game config from built-in class: {game_cls}")
        cfg = GameConfig.from_game_class(game_cls)
        logger.debug(f"Loaded game config: {cfg.name}")
    except Exception as exc:
        pytest.fail(f"Failed to load game config from built-in class: {game_cls}\n{exc!r}")
