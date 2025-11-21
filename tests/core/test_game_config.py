"""Tests for GameConfig."""

from types import SimpleNamespace
from typing import Any, Dict

import pytest
from loguru import logger
from mongomock import ObjectId

from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.helpers import database_helpers as dbh
from tests.helpers import patch_yml

# TODO: update these tests to run the test the following character selectors instead of the ones they are currently using. Continue to use patch to modify the minimal config for each test.
# - any pc/npc
# - specific hid
# - descriptors/abilities regex (e.g. human-like-cognition, human-like-form, animal, service-animal, etc.)
# - not recently played
# - not played by this player before
# - not finished from previous started game
# - distinct npc and pc (must be different)
# - characters player has expertise in
# - characters with simple goals
# - charaters short long_descriptors


@pytest.mark.unit
def test_load_minimal_game_config(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load a minimal valid GameConfig from YAML."""
    cfg = GameConfig.from_yaml(game_config_minimal.path)
    assert cfg.name == "Minimal Test Game Config"


@pytest.mark.unit
def test_regex_and_ne(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load human-like chars."""
    # Patch minimal config to include simple valid character selectors
    patch = """
    character_settings:
      pc:
        valid:
          characters: 
            where:
              common_descriptors:
                "$regex": "human-?like"
                "$options": "i"
      npc:
        valid:
          characters:
            where:
              hid:
                "$ne": "human-normative"
    """
    patched_yml = patch_yml(game_config_minimal.path, patch)
    logger.debug(f"Patched YAML path: {patched_yml.path}")
    logger.debug(f"Patched YAML content:\n{patched_yml.data}")
    cfg = GameConfig.from_yaml(patched_yml.path)
    assert cfg.name == "Minimal Test Game Config"

    # make sure human-normative is included in valid PCs
    valid_pcs, _ = cfg.get_valid_characters()
    valid_pcs = [value for _, value in valid_pcs]
    logger.debug(f"Valid PCs: {valid_pcs}")
    assert "human-normative" in valid_pcs


@pytest.mark.unit
def test_select_characters_valid(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should load valid characters from minimal config."""
    # Patch minimal config to include simple valid character selectors
    patch = """
    character_settings:
      pc:
        valid:
          characters:
            where:
                hid: 'human-normative'
      npc:
        valid:
          characters: { 'where': { hid: { $ne : 'human-normative' } } }
    """
    patched_yml = patch_yml(game_config_minimal.path, patch)
    logger.debug(f"Patched YAML path: {patched_yml.path}")
    logger.debug(f"Patched YAML content:\n{patched_yml.data}")
    cfg = GameConfig.from_yaml(patched_yml.path)
    assert cfg.name == "Minimal Test Game Config"


@pytest.mark.unit
def test_get_valid_chars_with_valid_minus_invalid(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should compute V - I for PCs and NPCs with single-source valid/invalid.

    - PCs: V={'human-normative'}, I=∅ → ['human-normative']
    - NPCs: V={'a','b','c'}, I={'b'} → ['a','c']
    """
    patch = """
    character_settings:
      pc:
        valid: 
          # where hid includes 'human'
          characters: { 'where': { hid: { $regex: 'human' } } }
      npc:
        valid:
          # where hid is in this set
          characters: { 'where': { hid: { $in: ['algorithm-sort', 'human-multi-divergent-complex', 'llm-gpt5', 'thermostat', 'flatworm'] } } }
        invalid:
          # where player has played this character in a previous run of this game
          runs: { 'where': { "game_config.name": "Test Game" } }
    """
    patched_yml = patch_yml(game_config_minimal.path, patch)
    logger.debug(f"Patched YAML path: {patched_yml.path}")
    logger.debug(f"Patched YAML content:\n{patched_yml.data}")
    cfg = GameConfig.from_yaml(patched_yml.path)

    db = dbh.get_db()

    # Create a player in the database
    player_data: Dict[str, Any] = {"email": "alice@example.com"}
    player_id, _ = dbh.create_player(player_data, issue_access_key=True)
    player_doc = db.players.find_one({"_id": ObjectId(player_id)})
    assert player_doc is not None
    assert db.characters.count_documents({}) > 5  # sanity check
    # Add a run for this player with game_config name "Test Game"
    db.runs.insert_one(
        {
            "player_id": ObjectId(player_id),
            "game_config": {"name": "Test Game"},
            "npc": {"hid": "flatworm"},
            "timestamp": dbh.now(),
        }
    )
    # make sure it exists
    doc = db.runs.find_one(
        {"player_id": ObjectId(player_id), "game_config.name": "Test Game"}
    )
    logger.debug(f"Inserted run doc: {doc}")
    assert doc is not None
    assert doc["game_config"]["name"] == "Test Game"

    pcs, npcs = cfg.get_valid_characters(player_id=player_id)
    pcs = [value for _, value in pcs]
    npcs = [value for _, value in npcs]
    logger.debug(f"Valid PCs: {pcs}, Valid NPCs: {npcs}")

    # get all characters from db then remove invalids to compare
    all_chars = list(db.characters.find({}))
    assert all_chars is not None

    expected_valid_pcs = [c for c in all_chars if c["hid"] in pcs]
    expected_valid_npcs = [c for c in all_chars if c["hid"] in npcs]

    # compare sets of HIDs
    assert set(c["hid"] for c in expected_valid_pcs) == set(pcs)
    assert set(c["hid"] for c in expected_valid_npcs) == set(npcs)


@pytest.mark.unit
def test_get_valid_chars_older_than(
    game_config_minimal: SimpleNamespace,
) -> None:
    """Should compute valid characters filtering runs by created_at."""
    patch = """
    character_settings:
      pc:
        valid:
          characters: { 'where': { 'hid': 'human-normative' } }
      npc:
        valid:
          characters: { 'where': { 'hid': { $ne: 'human-normative' } } }
        invalid: # older than 1 day
          runs: { 'where': { '_created_at': { '$lt': __delta_days-1__ } } }
    """
    patched_yml = patch_yml(game_config_minimal.path, patch)
    logger.debug(f"Patched YAML path: {patched_yml.path}")
    logger.debug(f"Patched YAML content:\n{patched_yml.data}")
    cfg = GameConfig.from_yaml(patched_yml.path)

    db = dbh.get_db()
    assert db.characters.count_documents({}) > 5  # sanity check

    # create a player, insert two runs: one old, one recent
    player_data: Dict[str, Any] = {"email": "bob@example.com"}
    player_id, _ = dbh.create_player(player_data, issue_access_key=True)
    player_doc = db.players.find_one({"_id": ObjectId(player_id)})
    assert player_doc is not None

    runs = [
        # old run (invalid)
        {
            "player_id": ObjectId(player_id),
            "game_config": {"name": "Any"},
            "npc": {"hid": "algorithm-sort"},
            "_created_at": dbh.now(delta=-2),
        },
        # recent run (valid)
        {
            "player_id": ObjectId(player_id),
            "game_config": {"name": "Any"},
            "npc": {"hid": "llm-gpt5"},
            "_created_at": dbh.now(),
        },
    ]
    db.runs.insert_many(runs)
    assert db.runs.count_documents({"player_id": ObjectId(player_id)}) == 2
    logger.debug(
        f"Inserted runs for player_id={player_id}: {list(db.runs.find({'player_id': ObjectId(player_id)}))}"
    )

    pcs, npcs = cfg.get_valid_characters(player_id=player_id)
    pcs = [value for _, value in pcs]
    npcs = [value for _, value in npcs]
    logger.debug(f"Valid PCs: {pcs}, Valid NPCs: {npcs}")

    # get all characters from db then remove invalids to compare
    all_chars = list(db.characters.find({}))
    assert all_chars is not None
    expected_valid_pcs = [c for c in all_chars if c["hid"] in pcs]
    expected_valid_npcs = [c for c in all_chars if c["hid"] in npcs]

    assert set(c["hid"] for c in expected_valid_pcs) == set(pcs)
    assert set(c["hid"] for c in expected_valid_npcs) == set(npcs)
