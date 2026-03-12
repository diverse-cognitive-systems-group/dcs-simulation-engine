"""Tests for database helpers."""



import time
from typing import Any, Dict, List

import dcs_simulation_engine.helpers.database_helpers as dbh
import pytest
from bson import ObjectId
from loguru import logger


@pytest.mark.unit
def test_database_is_seeded() -> None:
    """Verify that the database is seeded with initial data."""
    db = dbh.get_db()
    # TODO: verify db is mocked or test db
    collections = db.list_collection_names()
    logger.debug(f"Database collections: {collections}")
    assert "characters" in collections
    assert "players" in collections
    assert "runs" in collections
    # make sure characters collection has some entries
    count = db["characters"].count_documents({})
    logger.debug(f"Characters collection document count: {count}")
    assert count > 3


@pytest.mark.unit
def test_create_player() -> None:
    """Create a player document and verify persisted fields.

    Verifies:
        - Document exists in PLAYERS collection.
        - Email, access_key_hash, access_key_revoked, and created timestamp fields.
    """
    player_data: Dict[str, Any] = {"email": "alice@example.com"}
    created_id, raw_key = dbh.create_player(
        player_data=player_data, issue_access_key=True
    )

    logger.debug(f"Created player: id={created_id}, raw_key={raw_key}")
    assert isinstance(created_id, str)
    assert raw_key is not None

    db = dbh.get_db()
    doc = db[dbh.PLAYERS_COL].find_one({"_id": ObjectId(created_id)})
    assert doc is not None
    assert doc.get("access_key_hash") == dbh._hash_key(raw_key)
    assert doc.get("access_key_revoked") is False
    assert dbh.DEFAULT_CREATEDAT_FIELD in doc


@pytest.mark.unit
def test_get_player_id_from_api_key() -> None:
    """SShould generate an access key and resolve the owner.

    Generate an access key and resolve the owning player via
    `get_player_id_from_access_key`.

    Verifies:
        - The resolved ID matches the inserted player's ID.
    """
    player_data: Dict[str, Any] = {"email": "bob@example.com"}
    created_id, raw_key = dbh.create_player(
        player_data=player_data, issue_access_key=True
    )

    got = dbh.get_player_id_from_access_key(raw_key)
    logger.debug(f"Resolved player id: {got}")
    assert got == created_id


@pytest.mark.unit
def test_save_run_data() -> None:
    """Should save a run for a player and read it back.

    Verifies:
        - Run document exists and matches the provided payload.
        - The helper's created-at field is present.
    """
    player_id, _ = dbh.create_player(
        {"email": "carry@example.com"}, issue_access_key=True
    )
    assert isinstance(player_id, str)

    run_data: Dict[str, Any] = {
        "score": 100,
        "duration": 3600,
        "completed": True,
        "game_config": {"name": "Test Game", "version": "1.0"},
    }
    run_id: str = dbh.save_run_data(player_id, run_data)
    assert isinstance(run_id, str)

    db = dbh.get_db()
    doc = db[dbh.RUNS_COL].find_one({"_id": ObjectId(run_id)})
    assert doc is not None

    assert doc["player_id"] == player_id
    assert doc["score"] == 100
    assert doc["duration"] == 3600
    assert doc["completed"] is True
    assert dbh.DEFAULT_CREATEDAT_FIELD in doc


@pytest.mark.skip(reason="FIX ME")
@pytest.mark.slow
@pytest.mark.unit
def test_list_characters_where() -> None:
    """Should filter characters based on various criteria.

    Exercise `list_characters_where` across:
      1) Filter by game_config.name.
      2) Filter by start_ts < threshold.
      3) No filter (all).
      4) Ordered and limited query.

    Note:
        The helper expects a flat character field (default: "hid"). The test mirrors
        the nested state.npc.hid into a top-level "hid" to match the helper contract.
    """
    player_id, _ = dbh.create_player(
        {"email": "dave@example.com"}, issue_access_key=True
    )
    assert isinstance(player_id, str)

    now: int = int(time.time())
    runs: List[Dict[str, Any]] = [
        {
            "name": "Test Run1",
            "game_config": {"name": "Test Game"},
            "game_finished": False,
            "start_ts": now - 5 * 24 * 3600,
            "state": {"pc": {"hid": "human-normative"}, "npc": {"hid": "flatworm"}},
            "hid": "flatworm",
        },
        {
            "name": "Test Run2",
            "game_config": {"name": "Test Game"},
            "game_finished": False,
            "start_ts": now - 10 * 24 * 3600,
            "state": {
                "pc": {"hid": "human-normative"},
                "npc": {"hid": "human-low-vision"},
            },
            "hid": "human-low-vision",
        },
        {
            "name": "Test Run3",
            "game_config": {"name": "Test Game"},
            "game_finished": True,
            "start_ts": now - 15 * 24 * 3600,
            "state": {
                "pc": {"hid": "human-normative"},
                "npc": {"hid": "human-multi-divergent"},
            },
            "hid": "human-multi-divergent",
        },
    ]

    for run in runs:
        time.sleep(0.01)  # keep insertion order stable
        dbh.save_run_data(player_id, run)

    # 1) Characters in "Test Game"
    chars: List[str] = dbh.list_characters_where(
        player_id=player_id,
        query={"game_config.name": "Test Game"},
        collection=dbh.RUNS_COL,
    )
    logger.debug(f"chars by game_config.name: {chars}")

    assert set(chars) == {"flatworm", "human-low-vision", "human-multi-divergent"}

    # 2) Characters where start_ts < 7 days ago
    chars = dbh.list_characters_where(
        player_id=player_id,
        query={"start_ts": {"$lt": now - 7 * 24 * 3600}},
        collection=dbh.RUNS_COL,
    )
    logger.debug(f"chars older than 7 days: {chars}")
    assert set(chars) == {"human-low-vision", "human-multi-divergent"}

    # 3) Characters ever played
    chars = dbh.list_characters_where(
        player_id=player_id,
        query={},
        collection=dbh.RUNS_COL,
    )
    logger.debug(f"chars ever played: {chars}")
    assert set(chars) == {"flatworm", "human-low-vision", "human-multi-divergent"}

    # 4) Most recently played in unfinished game
    chars = dbh.list_characters_where(
        player_id=player_id,
        query={
            "where": {"game_finished": False},
            "order_by": ["start_ts", "desc"],
            "limit": 1,
        },
        collection=dbh.RUNS_COL,
    )
    logger.debug(f"most recent unfinished: {chars}")
    assert chars == ["flatworm"]
