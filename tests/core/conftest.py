"""Conftest fixtures for core tests."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest

from tests.helpers import patch_yaml


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
    access_settings:
      user:
        valid:
          players: {}
    data_collection_settings:
      save_runs: False
    character_settings:
      pc:
        valid:
          characters: {}
      npc:
        valid:
          characters: {}
    game_class: dcs_simulation_engine.games.explore.ExploreGame
    """
    game_config_path = base / "game_config_minimal.yaml"
    write_yaml(game_config_path, game_config_yaml)
    return SimpleNamespace(path=game_config_path)
