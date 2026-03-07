"""Conftest fixtures for core tests."""

from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import pytest
from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.helpers import database_helpers as dbh
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
    game_class: tests.fixtures.test_games.MinimalTestGame
    """
    game_config_path = base / "game_config_minimal.yaml"
    write_yaml(game_config_path, game_config_yaml)
    return SimpleNamespace(path=game_config_path)


@pytest.fixture
def game_config_with_branching_graph(
    game_config_minimal: SimpleNamespace,
) -> SimpleNamespace:
    """Fixture for a game config with a branching graph."""
    patch = """
    character_settings:
      pc:
        valid:
          characters: { hid: 'human-normative' }
      npc:
        valid:
          characters: { hid: 'flatworm' }
    game_class: tests.fixtures.test_games.BranchingTestGame
    """
    patched_yaml = patch_yaml(game_config_minimal.path, patch)
    return SimpleNamespace(path=patched_yaml.path)


@pytest.fixture
def run(game_config_with_branching_graph: SimpleNamespace) -> RunManager:
    """Fresh RunManager instance built from the reusable YAML files.

    Kept function-scoped so each test gets a clean instance.
    """
    rm = RunManager.create(
        game=Path(game_config_with_branching_graph.path),
        source="pytest",
        pc_choice="human-normative",
        # npc_choice="flatworm"
    )
    return rm


@pytest.fixture
def game_config_with_player_persistence(
    game_config_minimal: SimpleNamespace,
) -> SimpleNamespace:
    """Fixture for a game config with player persistence."""
    patch = """
    data_collection_settings:
      save_runs: True
    character_settings:
      pc:
        valid:
          characters: { hid: 'human-normative' }
      npc:
        valid:
          characters: { hid: 'flatworm' }
    """
    patched_yaml = patch_yaml(game_config_minimal.path, patch)
    return SimpleNamespace(path=patched_yaml.path)


@pytest.fixture
def persistent_run(game_config_with_player_persistence: SimpleNamespace) -> RunManager:
    """Fresh RunManager instance with player persistence enabled."""
    # create player in db and get access key
    player_data = {
        "name": "Persistent Test Player",
        "email": "persistant_test_player@example.com",
    }
    player_id, access_key = dbh.create_player(
        player_data=player_data, issue_access_key=True
    )
    rm = RunManager.create(
        game=Path(game_config_with_player_persistence.path),
        source="pytest",
        access_key=access_key,
    )
    return rm
