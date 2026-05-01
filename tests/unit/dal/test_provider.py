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

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_get_character_returns_record(async_mongo_provider):
    """get_character returns a CharacterRecord for a seeded character."""
    # The mongomock DB is seeded from database_seeds/dev at test time (autouse fixture).
    # Use a known hid from the seed data.
    db = async_mongo_provider.get_db()
    db["characters"].insert_one({"hid": "test-char", "name": "Test", "short_description": "A test character"})

    record = await async_mongo_provider.get_character(hid="test-char")

    assert isinstance(record, CharacterRecord)
    assert record.hid == "test-char"
    assert record.name == "Test"
    assert record.short_description == "A test character"


async def test_get_character_not_found_raises(async_mongo_provider):
    """get_character raises ValueError for an unknown hid."""
    with pytest.raises(ValueError, match="not found"):
        await async_mongo_provider.get_character(hid="nonexistent-hid")


async def test_create_player_returns_record(async_mongo_provider):
    """create_player returns a PlayerRecord."""
    record, raw_key = await async_mongo_provider.create_player(player_data={"name": "Alice"})

    assert isinstance(record, PlayerRecord)
    assert record.id  # non-empty string id
    assert raw_key is None  # no access key by default


async def test_create_player_with_access_key(async_mongo_provider):
    """create_player with issue_access_key=True returns a raw key."""
    record, raw_key = await async_mongo_provider.create_player(player_data={"name": "Bob"}, issue_access_key=True)

    assert isinstance(record, PlayerRecord)
    assert raw_key is not None
    assert raw_key.startswith("dcs-ak-")
    assert record.access_key == raw_key


async def test_create_player_with_explicit_access_key(async_mongo_provider):
    """create_player accepts an explicitly provided deployment admin key."""
    explicit_key = "dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU"
    record, raw_key = await async_mongo_provider.create_player(player_data={"name": "Dana"}, access_key=explicit_key)

    assert isinstance(record, PlayerRecord)
    assert raw_key == explicit_key
    assert record.access_key == explicit_key


async def test_create_player_stores_in_db(async_mongo_provider):
    """create_player actually inserts the player into the DB."""
    record, _ = await async_mongo_provider.create_player(player_data={"name": "Charlie"})

    db = async_mongo_provider.get_db()
    from bson import ObjectId

    doc = db[MongoColumns.PLAYERS].find_one({"_id": ObjectId(record.id)})
    assert doc is not None


async def test_get_players_by_access_key_returns_record(async_mongo_provider):
    """get_players(access_key=...) finds a player by their raw key."""
    _, raw_key = await async_mongo_provider.create_player(player_data={"name": "Diana"}, issue_access_key=True)

    result = await async_mongo_provider.get_players(access_key=raw_key)

    assert result is not None
    assert isinstance(result, PlayerRecord)


async def test_get_players_by_access_key_wrong_key_returns_none(async_mongo_provider):
    """get_players(access_key=...) returns None for an invalid key."""
    result = await async_mongo_provider.get_players(access_key="ak-not-a-real-key")
    assert result is None


async def test_get_players_by_access_key_empty_returns_none(async_mongo_provider):
    """get_players(access_key=...) returns None for empty input."""
    assert await async_mongo_provider.get_players(access_key="") is None


async def test_get_players_returns_records(async_mongo_provider):
    """get_players returns PlayerRecords."""
    await async_mongo_provider.create_player(player_data={"name": "Eve"})
    await async_mongo_provider.create_player(player_data={"name": "Frank"})

    players = await async_mongo_provider.get_players()

    assert len(players) >= 2
    assert all(isinstance(p, PlayerRecord) for p in players)


async def test_get_session_returns_session_record(async_mongo_provider):
    """get_session returns a SessionRecord when the session exists."""
    db = async_mongo_provider.get_db()
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

    session = await async_mongo_provider.get_session(session_id="s-1", player_id="p-1")
    assert isinstance(session, SessionRecord)
    assert session.session_id == "s-1"
    assert session.player_id == "p-1"
    assert session.data["source"] == "test"


async def test_branch_session_clones_snapshot_and_events(async_mongo_provider):
    """branch_session creates a paused child with copied snapshot and transcript rows."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            MongoColumns.SESSION_ID: "root-1",
            MongoColumns.PLAYER_ID: "player-1",
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.STATUS: "paused",
            MongoColumns.CREATED_AT: created_at,
            MongoColumns.UPDATED_AT: created_at,
            MongoColumns.SESSION_STARTED_AT: created_at,
            MongoColumns.TURNS_COMPLETED: 2,
            MongoColumns.LAST_SEQ: 3,
            MongoColumns.SOURCE: "hitl",
            MongoColumns.RUNTIME_STATE: {"snapshot_version": 1, "turns": 2},
        }
    )
    db[MongoColumns.SESSION_EVENTS].insert_many(
        [
            {
                MongoColumns.SESSION_ID: "root-1",
                MongoColumns.SEQ: 1,
                MongoColumns.EVENT_ID: "evt-root-1",
                MongoColumns.EVENT_TS: created_at,
                MongoColumns.DIRECTION: "outbound",
                MongoColumns.EVENT_TYPE: "ai",
                MongoColumns.EVENT_SOURCE: "npc",
                MongoColumns.CONTENT: "opening",
            },
            {
                MongoColumns.SESSION_ID: "root-1",
                MongoColumns.SEQ: 2,
                MongoColumns.EVENT_ID: "evt-root-2",
                MongoColumns.EVENT_TS: created_at,
                MongoColumns.DIRECTION: "inbound",
                MongoColumns.EVENT_TYPE: "message",
                MongoColumns.EVENT_SOURCE: "user",
                MongoColumns.CONTENT: "hello",
            },
        ]
    )

    child = await async_mongo_provider.branch_session(
        session_id="root-1",
        player_id="player-1",
        branched_at=created_at,
    )

    assert isinstance(child, SessionRecord)
    assert child.session_id != "root-1"
    assert child.player_id == "player-1"
    assert child.status == "paused"
    assert child.data[MongoColumns.BRANCH_FROM_SESSION_ID] == "root-1"
    assert child.data[MongoColumns.RUNTIME_STATE] == {"snapshot_version": 1, "turns": 2}
    assert child.data[MongoColumns.LAST_SEQ] == 3
    assert child.data[MongoColumns.TURNS_COMPLETED] == 2

    child_doc = db[MongoColumns.SESSIONS].find_one({MongoColumns.SESSION_ID: child.session_id})
    assert child_doc is not None
    assert child_doc[MongoColumns.BRANCH_FROM_SESSION_ID] == "root-1"
    assert child_doc[MongoColumns.STATUS] == "paused"

    copied_events = list(
        db[MongoColumns.SESSION_EVENTS]
        .find({MongoColumns.SESSION_ID: child.session_id})
        .sort(MongoColumns.SEQ, 1)
    )
    assert [event[MongoColumns.SEQ] for event in copied_events] == [1, 2]
    assert [event[MongoColumns.CONTENT] for event in copied_events] == ["opening", "hello"]
    assert {event[MongoColumns.EVENT_ID] for event in copied_events}.isdisjoint({"evt-root-1", "evt-root-2"})

    root_doc = db[MongoColumns.SESSIONS].find_one({MongoColumns.SESSION_ID: "root-1"})
    assert root_doc is not None
    assert MongoColumns.BRANCH_FROM_SESSION_ID not in root_doc


async def test_list_session_events_returns_session_event_records(async_mongo_provider):
    """list_session_events returns ordered SessionEventRecord rows."""
    db = async_mongo_provider.get_db()
    db[MongoColumns.SESSION_EVENTS].insert_many(
        [
            {
                "session_id": "s-2",
                "seq": 2,
                "event_id": "e-2",
                "event_ts": datetime.now(timezone.utc),
                "direction": "outbound",
                "event_type": "message",
                "event_source": "npc",
                "content": "two",
            },
            {
                "session_id": "s-2",
                "seq": 1,
                "event_id": "e-1",
                "event_ts": datetime.now(timezone.utc),
                "direction": "inbound",
                "event_type": "message",
                "event_source": "user",
                "content": "one",
            },
        ]
    )

    events = await async_mongo_provider.list_session_events(session_id="s-2")
    assert isinstance(events, list)
    assert all(isinstance(event, SessionEventRecord) for event in events)
    assert [event.seq for event in events] == [1, 2]
    assert events[0].event_type == "message"
    assert events[0].event_source == "user"
    assert events[1].event_type == "message"
    assert events[1].event_source == "npc"


async def test_append_session_event_persists_hidden_internal_json_event_and_advances_last_seq(async_mongo_provider):
    """append_session_event adds a hidden internal JSON row and updates the parent session sequence counter."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            MongoColumns.SESSION_ID: "s-eval",
            MongoColumns.PLAYER_ID: "p-eval",
            MongoColumns.GAME_NAME: "Infer Intent",
            MongoColumns.STATUS: "closed",
            MongoColumns.CREATED_AT: created_at,
            MongoColumns.UPDATED_AT: created_at,
            MongoColumns.LAST_SEQ: 3,
            MongoColumns.TURNS_COMPLETED: 4,
        }
    )

    appended = await async_mongo_provider.append_session_event(
        session_id="s-eval",
        player_id="p-eval",
        direction="internal",
        event_type="score_cache",
        event_source="system",
        content='{"tier": 3, "score": 95, "reasoning": "Strong match."}',
        content_format="json",
        turn_index=4,
        visible_to_user=False,
    )

    assert isinstance(appended, SessionEventRecord)
    assert appended.seq == 4
    assert appended.event_type == "score_cache"
    assert appended.event_source == "system"

    event_doc = db[MongoColumns.SESSION_EVENTS].find_one({MongoColumns.EVENT_ID: appended.event_id})
    assert event_doc is not None
    assert event_doc[MongoColumns.SEQ] == 4
    assert event_doc[MongoColumns.DIRECTION] == "internal"
    assert event_doc[MongoColumns.CONTENT_FORMAT] == "json"
    assert event_doc[MongoColumns.VISIBLE_TO_USER] is False
    assert event_doc[MongoColumns.TURN_INDEX] == 4

    session_doc = db[MongoColumns.SESSIONS].find_one({MongoColumns.SESSION_ID: "s-eval"})
    assert session_doc is not None
    assert session_doc[MongoColumns.LAST_SEQ] == 4
    assert session_doc[MongoColumns.UPDATED_AT] is not None


async def test_set_session_event_feedback_overwrites_existing_value(async_mongo_provider):
    """set_session_event_feedback stores one top-level boolean-feedback object per NPC message event."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            "session_id": "s-feedback",
            "player_id": "p-feedback",
            "game_name": "Explore",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    db[MongoColumns.SESSION_EVENTS].insert_one(
        {
            "session_id": "s-feedback",
            "seq": 1,
            "event_id": "evt-ai-1",
            "event_ts": created_at,
            "direction": "outbound",
            "event_type": "message",
            "event_source": "npc",
            "content": "hello",
        }
    )

    first = {
        "liked": False,
        "comment": "The reply was confusing.",
        "doesnt_make_sense": True,
        "out_of_character": False,
        "submitted_at": created_at,
    }
    second = {
        "liked": False,
        "comment": "The reply felt off character.",
        "doesnt_make_sense": False,
        "out_of_character": True,
        "submitted_at": created_at,
    }

    stored_first = await async_mongo_provider.set_session_event_feedback(
        session_id="s-feedback",
        player_id="p-feedback",
        event_id="evt-ai-1",
        feedback=first,
    )
    stored_second = await async_mongo_provider.set_session_event_feedback(
        session_id="s-feedback",
        player_id="p-feedback",
        event_id="evt-ai-1",
        feedback=second,
    )

    assert stored_first == first
    assert stored_second == second

    event_doc = db[MongoColumns.SESSION_EVENTS].find_one({"event_id": "evt-ai-1"})
    assert event_doc[MongoColumns.FEEDBACK]["liked"] is False
    assert event_doc[MongoColumns.FEEDBACK]["comment"] == "The reply felt off character."
    assert event_doc[MongoColumns.FEEDBACK]["doesnt_make_sense"] is False
    assert event_doc[MongoColumns.FEEDBACK]["out_of_character"] is True
    assert event_doc[MongoColumns.FEEDBACK]["submitted_at"] is not None
    assert event_doc[MongoColumns.UPDATED_AT] is not None


async def test_set_session_event_feedback_rejects_non_npc_message_target(async_mongo_provider):
    """set_session_event_feedback ignores non-NPC-message session events."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            "session_id": "s-feedback-2",
            "player_id": "p-feedback-2",
            "game_name": "Explore",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    db[MongoColumns.SESSION_EVENTS].insert_one(
        {
            "session_id": "s-feedback-2",
            "seq": 1,
            "event_id": "evt-user-1",
            "event_ts": created_at,
            "direction": "inbound",
            "event_type": "message",
            "event_source": "user",
            "content": "hello",
        }
    )

    stored = await async_mongo_provider.set_session_event_feedback(
        session_id="s-feedback-2",
        player_id="p-feedback-2",
        event_id="evt-user-1",
        feedback={
            "liked": False,
            "comment": "This should be rejected.",
            "doesnt_make_sense": True,
            "out_of_character": False,
            "submitted_at": created_at,
        },
    )

    assert stored is None
    event_doc = db[MongoColumns.SESSION_EVENTS].find_one({"event_id": "evt-user-1"})
    assert MongoColumns.FEEDBACK not in event_doc


async def test_clear_session_event_feedback_removes_existing_feedback(async_mongo_provider):
    """clear_session_event_feedback unsets the feedback field on the NPC message event."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            "session_id": "s-feedback-3",
            "player_id": "p-feedback-3",
            "game_name": "Explore",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    db[MongoColumns.SESSION_EVENTS].insert_one(
        {
            "session_id": "s-feedback-3",
            "seq": 1,
            "event_id": "evt-ai-3",
            "event_ts": created_at,
            "direction": "outbound",
            "event_type": "message",
            "event_source": "npc",
            "content": "hello",
            "feedback": {
                "liked": False,
                "comment": "This felt off.",
                "doesnt_make_sense": False,
                "out_of_character": True,
                "submitted_at": created_at,
            },
        }
    )

    cleared = await async_mongo_provider.clear_session_event_feedback(
        session_id="s-feedback-3",
        player_id="p-feedback-3",
        event_id="evt-ai-3",
    )

    assert cleared is True
    event_doc = db[MongoColumns.SESSION_EVENTS].find_one({"event_id": "evt-ai-3"})
    assert MongoColumns.FEEDBACK not in event_doc
    assert event_doc[MongoColumns.UPDATED_AT] is not None


async def test_set_session_event_feedback_accepts_legacy_owner_none(async_mongo_provider):
    """Historical ownerless sessions should still accept NPC message feedback."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            "session_id": "s-feedback-ownerless",
            "player_id": None,
            "game_name": "Explore",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    db[MongoColumns.SESSION_EVENTS].insert_one(
        {
            "session_id": "s-feedback-ownerless",
            "seq": 1,
            "event_id": "evt-ai-ownerless",
            "event_ts": created_at,
            "direction": "outbound",
            "event_type": "message",
            "event_source": "npc",
            "content": "hello",
        }
    )

    stored = await async_mongo_provider.set_session_event_feedback(
        session_id="s-feedback-ownerless",
        player_id=None,
        event_id="evt-ai-ownerless",
        feedback={
            "liked": False,
            "comment": "Anonymous ownerless feedback.",
            "doesnt_make_sense": True,
            "out_of_character": False,
            "submitted_at": created_at,
        },
    )

    assert stored is not None
    event_doc = db[MongoColumns.SESSION_EVENTS].find_one({"event_id": "evt-ai-ownerless"})
    assert event_doc[MongoColumns.FEEDBACK]["comment"] == "Anonymous ownerless feedback."
    assert event_doc[MongoColumns.FEEDBACK]["doesnt_make_sense"] is True


@pytest.mark.parametrize(
    ("direction", "event_type", "event_source"),
    [
        ("inbound", "message", "user"),
        ("inbound", "command", "user"),
        ("outbound", "command", "system"),
        ("outbound", "info", "system"),
        ("outbound", "error", "system"),
        ("internal", "session_start", "system"),
        ("internal", "session_end", "system"),
    ],
)
async def test_feedback_is_rejected_for_non_npc_message_events(
    async_mongo_provider,
    direction: str,
    event_type: str,
    event_source: str,
):
    """Feedback is only accepted for outbound NPC message rows."""
    db = async_mongo_provider.get_db()
    created_at = datetime.now(timezone.utc)
    db[MongoColumns.SESSIONS].insert_one(
        {
            "session_id": "s-feedback-matrix",
            "player_id": "p-feedback-matrix",
            "game_name": "Explore",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        }
    )
    db[MongoColumns.SESSION_EVENTS].insert_one(
        {
            "session_id": "s-feedback-matrix",
            "seq": 1,
            "event_id": f"evt-{direction}-{event_type}-{event_source}",
            "event_ts": created_at,
            "direction": direction,
            "event_type": event_type,
            "event_source": event_source,
            "content": "nope",
        }
    )

    stored = await async_mongo_provider.set_session_event_feedback(
        session_id="s-feedback-matrix",
        player_id="p-feedback-matrix",
        event_id=f"evt-{direction}-{event_type}-{event_source}",
        feedback={
            "liked": False,
            "comment": "Matrix test.",
            "doesnt_make_sense": True,
            "out_of_character": False,
            "submitted_at": created_at,
        },
    )

    assert stored is None
