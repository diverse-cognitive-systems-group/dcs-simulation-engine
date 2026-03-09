"""Unit tests for MongoProvider."""

from datetime import datetime, timezone

import pytest
from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    PlayerRecord,
    RunRecord,
)
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)


@pytest.mark.unit
def test_get_character_returns_record(mongo_provider):
    """get_character returns a CharacterRecord for a seeded character."""
    # The mongomock DB is seeded from database_seeds/dev at test time (autouse fixture).
    # Use a known hid from the seed data.
    db = mongo_provider.get_db()
    db["characters"].insert_one({"hid": "test-char", "name": "Test", "short_description": "A test character"})

    record = mongo_provider.get_character(hid="test-char")

    assert isinstance(record, CharacterRecord)
    assert record.hid == "test-char"
    assert record.name == "Test"
    assert record.short_description == "A test character"


@pytest.mark.unit
def test_get_character_not_found_raises(mongo_provider):
    """get_character raises ValueError for an unknown hid."""
    with pytest.raises(ValueError, match="not found"):
        mongo_provider.get_character(hid="nonexistent-hid")


@pytest.mark.unit
def test_create_player_returns_record(mongo_provider):
    """create_player returns a PlayerRecord."""
    record, raw_key = mongo_provider.create_player(player_data={"name": "Alice"})

    assert isinstance(record, PlayerRecord)
    assert record.id  # non-empty string id
    assert raw_key is None  # no access key by default


@pytest.mark.unit
def test_create_player_with_access_key(mongo_provider):
    """create_player with issue_access_key=True returns a raw key."""
    record, raw_key = mongo_provider.create_player(player_data={"name": "Bob"}, issue_access_key=True)

    assert isinstance(record, PlayerRecord)
    assert raw_key is not None
    assert raw_key.startswith("dcs-ak-")
    assert record.access_key_hash is not None
    assert record.access_key_prefix is not None


@pytest.mark.unit
def test_create_player_stores_in_db(mongo_provider):
    """create_player actually inserts the player into the DB."""
    record, _ = mongo_provider.create_player(player_data={"name": "Charlie"})

    db = mongo_provider.get_db()
    from bson import ObjectId

    doc = db[MongoColumns.PLAYERS].find_one({"_id": ObjectId(record.id)})
    assert doc is not None


@pytest.mark.unit
def test_get_players_by_access_key_returns_record(mongo_provider):
    """get_players(access_key=...) finds a player by their raw key."""
    _, raw_key = mongo_provider.create_player(player_data={"name": "Diana"}, issue_access_key=True)

    result = mongo_provider.get_players(access_key=raw_key)

    assert result is not None
    assert isinstance(result, PlayerRecord)


@pytest.mark.unit
def test_get_players_by_access_key_wrong_key_returns_none(mongo_provider):
    """get_players(access_key=...) returns None for an invalid key."""
    result = mongo_provider.get_players(access_key="ak-not-a-real-key")
    assert result is None


@pytest.mark.unit
def test_get_players_by_access_key_empty_returns_none(mongo_provider):
    """get_players(access_key=...) returns None for empty input."""
    assert mongo_provider.get_players(access_key="") is None


@pytest.mark.unit
def test_save_run_returns_record(mongo_provider):
    """save_run returns a RunRecord with the assigned id."""
    run_data = {
        "name": "test-run",
        "game_config": {"name": "Explore"},
        "events": [],
    }
    record = mongo_provider.save_run("player-1", run_data)

    assert isinstance(record, RunRecord)
    assert record.id
    assert record.game_name == "Explore"
    assert record.player_id == "player-1"


@pytest.mark.unit
def test_get_runs_returns_records(mongo_provider):
    """get_runs returns RunRecords for all saved runs."""
    mongo_provider.save_run("player-1", {"name": "run-a", "game_config": {"name": "Explore"}, "events": []})
    mongo_provider.save_run("player-1", {"name": "run-b", "game_config": {"name": "Foresight"}, "events": []})

    runs = mongo_provider.get_runs()

    assert len(runs) >= 2
    assert all(isinstance(r, RunRecord) for r in runs)


@pytest.mark.unit
def test_get_players_returns_records(mongo_provider):
    """get_players returns PlayerRecords."""
    mongo_provider.create_player(player_data={"name": "Eve"})
    mongo_provider.create_player(player_data={"name": "Frank"})

    players = mongo_provider.get_players()

    assert len(players) >= 2
    assert all(isinstance(p, PlayerRecord) for p in players)


@pytest.mark.unit
def test_list_runs_normalizes_legacy_npc_hid(mongo_provider):
    """list_runs populates npc_hid from legacy context.npc.hid when needed."""
    player, _ = mongo_provider.create_player(player_data={"name": "Legacy"})
    from bson import ObjectId

    db = mongo_provider.get_db()
    db[MongoColumns.RUNS].insert_one(
        {
            "player_id": ObjectId(player.id),
            "game_config": {"name": "Legacy Game"},
            "context": {"npc": {"hid": "flatworm"}},
            "created_at": datetime.now(timezone.utc),
        }
    )

    runs = mongo_provider.list_runs(player_id=player.id, game_name="Legacy Game")
    assert runs
    assert runs[0].data.get("npc_hid") == "flatworm"


@pytest.mark.unit
def test_list_runs_prefers_top_level_npc_hid_over_legacy(mongo_provider):
    """list_runs uses top-level npc_hid when both modern and legacy fields exist."""
    player, _ = mongo_provider.create_player(player_data={"name": "Modern"})
    from bson import ObjectId

    db = mongo_provider.get_db()
    db[MongoColumns.RUNS].insert_one(
        {
            "player_id": ObjectId(player.id),
            "game_name": "Modern Game",
            "npc_hid": "modern-hid",
            "context": {"npc": {"hid": "legacy-hid"}},
            "created_at": datetime.now(timezone.utc),
        }
    )

    runs = mongo_provider.list_runs(player_id=player.id, game_name="Modern Game")
    assert runs
    assert runs[0].data.get("npc_hid") == "modern-hid"
