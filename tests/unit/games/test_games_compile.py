"""Tests that all built-in games compile without errors."""

import pytest
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from loguru import logger

BUILTIN_GAME_CLASSES = list(SessionManager._builtin_game_classes().values())


@pytest.mark.unit
def test_builtin_games_not_empty() -> None:
    """Ensure there is at least one built-in game class."""
    logger.debug(f"Discovered built-in game classes: {BUILTIN_GAME_CLASSES!r}")
    assert BUILTIN_GAME_CLASSES, "No built-in game classes found. Add games to test."


@pytest.mark.compile
@pytest.mark.anyio
@pytest.mark.parametrize("game_cls", BUILTIN_GAME_CLASSES, ids=[game.GAME_NAME for game in BUILTIN_GAME_CLASSES])
async def test_all_games_compile(game_cls, async_mongo_provider) -> None:
    """For each built-in game, ensure a SessionManager can be created successfully."""
    try:
        game_config = GameConfig.from_game_class(game_cls)
        await SessionManager.create_async(
            game=game_config,
            provider=async_mongo_provider,
            source="pytest",
            pc_choice=None,
            npc_choice=None,
            player_id=None,
        )
        logger.debug("SessionManager created successfully")
    except PermissionError:
        # Access-restricted games raise PermissionError when no player_id is provided.
        # This is expected — the config compiled fine.
        logger.debug(f"PermissionError (expected for consent-gated games): {game_cls.GAME_NAME}")
    except Exception as exc:
        pytest.fail(f"Failed to compile game from built-in class: {game_cls.GAME_NAME}\n{exc!r}")
