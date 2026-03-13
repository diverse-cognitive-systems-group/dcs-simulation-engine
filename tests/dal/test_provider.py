"""Unit tests for MongoProvider."""

from datetime import datetime, timezone

import pytest
from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    PlayerRecord,
    SessionEventRecord,
    SessionRecord,
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
    assert record.access_key == raw_key


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
def test_get_players_returns_records(mongo_provider):
    """get_players returns PlayerRecords."""
    mongo_provider.create_player(player_data={"name": "Eve"})
    mongo_provider.create_player(player_data={"name": "Frank"})

    players = mongo_provider.get_players()

    assert len(players) >= 2
    assert all(isinstance(p, PlayerRecord) for p in players)


@pytest.mark.unit
def test_get_session_returns_session_record(mongo_provider):
    """get_session returns a SessionRecord when the session exists."""
    db = mongo_provider.get_db()
    db[MongoColumns.SESSIONS].insert_one(
        {
            "session_id": "s-1",
            "player_id": "p-1",
            "game_name": "Explore",
            "status": "active",
            "created_at": datetime.now(timezone.utc),
            "source": "test",
        }
    )

    session = mongo_provider.get_session(session_id="s-1", player_id="p-1")
    assert isinstance(session, SessionRecord)
    assert session.session_id == "s-1"
    assert session.player_id == "p-1"
    assert session.data["source"] == "test"


@pytest.mark.unit
def test_list_session_events_returns_session_event_records(mongo_provider):
    """list_session_events returns ordered SessionEventRecord rows."""
    db = mongo_provider.get_db()
    db[MongoColumns.SESSION_EVENTS].insert_many(
        [
            {
                "session_id": "s-2",
                "seq": 2,
                "event_id": "e-2",
                "event_ts": datetime.now(timezone.utc),
                "direction": "outbound",
                "kind": "assistant_message",
                "role": "assistant",
                "content": "two",
            },
            {
                "session_id": "s-2",
                "seq": 1,
                "event_id": "e-1",
                "event_ts": datetime.now(timezone.utc),
                "direction": "inbound",
                "kind": "user_input",
                "role": "user",
                "content": "one",
            },
        ]
    )

    events = mongo_provider.list_session_events(session_id="s-2")
    assert isinstance(events, list)
    assert all(isinstance(event, SessionEventRecord) for event in events)
    assert [event.seq for event in events] == [1, 2]
