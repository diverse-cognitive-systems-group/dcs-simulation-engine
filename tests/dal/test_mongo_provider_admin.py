"""Unit tests for MongoProvider admin/database methods."""

import json

import pytest
from bson import ObjectId
from dcs_simulation_engine.dal.mongo import MongoAdmin
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


async def test_database_is_seeded(async_mongo_provider):
    """Database includes seeded core collections."""
    db = async_mongo_provider.get_db()
    collections = db.list_collection_names()

    assert "characters" in collections
    assert MongoColumns.PLAYERS in collections
    assert "runs" not in collections
    assert db["characters"].count_documents({}) > 3


async def test_default_indexes_include_pii_and_exclude_removed_indexes(async_mongo_provider):
    """Default index set includes new pii index and drops obsolete indexes."""
    db = async_mongo_provider.get_db()

    players_idx = db[MongoColumns.PLAYERS].index_information()
    pii_idx = db[MongoColumns.PII].index_information()
    sessions_idx = db[MongoColumns.SESSIONS].index_information()
    session_events_idx = db[MongoColumns.SESSION_EVENTS].index_information()

    assert "access_key_1" in players_idx
    assert players_idx["access_key_1"].get("unique") is True
    assert players_idx["access_key_1"].get("sparse") is True
    assert "access_key_revoked_1" not in players_idx

    assert "player_id_1" in pii_idx
    assert pii_idx["player_id_1"].get("unique") is True
    assert "session_id_1" in sessions_idx
    assert sessions_idx["session_id_1"].get("unique") is True
    assert "player_id_1_session_started_at_-1" in sessions_idx
    assert "status_1_updated_at_-1" in sessions_idx
    assert "session_id_1_seq_1" in session_events_idx
    assert session_events_idx["session_id_1_seq_1"].get("unique") is True
    assert "event_id_1" in session_events_idx
    assert session_events_idx["event_id_1"].get("unique") is True
    assert "session_id_1_event_ts_1" in session_events_idx


async def test_create_player_persists_fields(async_mongo_provider):
    """create_player persists data and raw access key fields."""
    record, raw_key = await async_mongo_provider.create_player(
        player_data={"email": "alice@example.com"},
        issue_access_key=True,
    )

    assert isinstance(record.id, str)
    assert raw_key is not None

    db = async_mongo_provider.get_db()
    doc = db[MongoColumns.PLAYERS].find_one({"_id": ObjectId(record.id)})

    assert doc is not None
    assert doc.get("access_key") == raw_key
    assert doc.get("access_key_revoked") is False
    assert MongoColumns.CREATED_AT in doc


async def test_seed_database_drops_and_replaces_collections(async_mongo_provider, tmp_path):
    """seed_database drops existing collections and inserts documents from seed files."""
    db = async_mongo_provider.get_db()
    db["widgets"].insert_many([{"x": 1}, {"x": 2}])
    assert db["widgets"].count_documents({}) == 2

    seed_file = tmp_path / "widgets.json"
    seed_file.write_text('[{"x": 99}]', encoding="utf-8")

    total = MongoAdmin(db=db).seed_database(seed_dir=tmp_path)

    assert total == 1
    assert db["widgets"].count_documents({}) == 1
    assert db["widgets"].find_one({})["x"] == 99


async def test_seed_database_restores_default_indexes_after_drop(async_mongo_provider, tmp_path):
    """seed_database reapplies baseline indexes after collection drops."""
    db = async_mongo_provider.get_db()

    (tmp_path / "characters.json").write_text('[{"hid": "seed-char", "name": "Seed Character"}]', encoding="utf-8")
    (tmp_path / "players.json").write_text('[{"name": "Seed Player", "access_key": "seed-ak"}]', encoding="utf-8")
    (tmp_path / "pii.json").write_text(
        '[{"player_id": "seed-player-id", "fields": {"email": "seed@example.com"}}]',
        encoding="utf-8",
    )
    (tmp_path / "sessions.json").write_text(
        '[{"session_id": "seed-session", "player_id": "seed-player-id", "status": "active"}]',
        encoding="utf-8",
    )
    (tmp_path / "session_events.json").write_text(
        '[{"session_id": "seed-session", "seq": 1, "event_id": "seed-event"}]',
        encoding="utf-8",
    )

    MongoAdmin(db=db).seed_database(seed_dir=tmp_path)

    players_idx = db[MongoColumns.PLAYERS].index_information()
    pii_idx = db[MongoColumns.PII].index_information()
    chars_idx = db[MongoColumns.CHARACTERS].index_information()
    sessions_idx = db[MongoColumns.SESSIONS].index_information()
    session_events_idx = db[MongoColumns.SESSION_EVENTS].index_information()

    assert "access_key_1" in players_idx
    assert "access_key_revoked_1" not in players_idx
    assert "player_id_1" in pii_idx
    assert pii_idx["player_id_1"].get("unique") is True
    assert "hid_1" in chars_idx
    assert chars_idx["hid_1"].get("unique") is True
    assert "session_id_1" in sessions_idx
    assert sessions_idx["session_id_1"].get("unique") is True
    assert "player_id_1_session_started_at_-1" in sessions_idx
    assert "status_1_updated_at_-1" in sessions_idx
    assert "session_id_1_seq_1" in session_events_idx
    assert session_events_idx["session_id_1_seq_1"].get("unique") is True
    assert "event_id_1" in session_events_idx
    assert session_events_idx["event_id_1"].get("unique") is True
    assert "session_id_1_event_ts_1" in session_events_idx
    assert "runs" not in db.list_collection_names()


async def test_backup_db_writes_manifest_and_collection_backups(async_mongo_provider, tmp_path):
    """backup_db writes manifest and ndjson/index files for each collection."""
    db = async_mongo_provider.get_db()
    db[MongoColumns.PLAYERS].insert_one({"name": "backup-test"})

    root = MongoAdmin(db=db).backup_db(tmp_path, append_ts=False)

    assert root.exists()
    manifest_path = root / "__manifest__.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["db_name"] == db.name
    assert MongoColumns.PLAYERS in manifest["collections"]

    players_dump = root / f"{MongoColumns.PLAYERS}.ndjson"
    players_indexes = root / f"{MongoColumns.PLAYERS}.__indexes__.json"
    assert players_dump.exists()
    assert players_indexes.exists()
