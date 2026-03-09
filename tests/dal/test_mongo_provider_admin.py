"""Unit tests for MongoProvider admin/database methods."""

import json

import pytest
from bson import ObjectId
from dcs_simulation_engine.dal.mongo import MongoAdmin
from dcs_simulation_engine.dal.mongo.const import (
    MongoColumns,
)
from dcs_simulation_engine.utils.auth import verify_key


@pytest.mark.unit
def test_database_is_seeded(mongo_provider):
    """Database includes seeded core collections."""
    db = mongo_provider.get_db()
    collections = db.list_collection_names()

    assert "characters" in collections
    assert MongoColumns.PLAYERS in collections
    assert MongoColumns.RUNS in collections
    assert db["characters"].count_documents({}) > 3


@pytest.mark.unit
def test_create_player_persists_fields(mongo_provider):
    """create_player persists data and hashed access key fields."""
    record, raw_key = mongo_provider.create_player(
        player_data={"email": "alice@example.com"},
        issue_access_key=True,
    )

    assert isinstance(record.id, str)
    assert raw_key is not None

    db = mongo_provider.get_db()
    doc = db[MongoColumns.PLAYERS].find_one({"_id": ObjectId(record.id)})

    assert doc is not None
    assert verify_key(raw_key, doc.get("access_key_hash"))
    assert doc.get("access_key_revoked") is False
    assert MongoColumns.CREATED_AT in doc


@pytest.mark.unit
def test_save_run_persists_fields(mongo_provider):
    """save_run stores run payload and created-at timestamp."""
    player_record, _ = mongo_provider.create_player(
        player_data={"email": "carry@example.com"},
        issue_access_key=True,
    )

    run_data = {
        "score": 100,
        "duration": 3600,
        "completed": True,
        "game_config": {"name": "Test Game", "version": "1.0"},
    }
    run_record = mongo_provider.save_run(player_record.id, run_data)

    db = mongo_provider.get_db()
    doc = db[MongoColumns.RUNS].find_one({"_id": ObjectId(run_record.id)})

    assert doc is not None
    assert str(doc["player_id"]) == player_record.id
    assert doc["score"] == 100
    assert doc["duration"] == 3600
    assert doc["completed"] is True
    assert MongoColumns.CREATED_AT in doc


@pytest.mark.unit
def test_init_or_seed_database_non_empty_returns_not_seeded(mongo_provider):
    """init_or_seed_database reports no-op when DB already has collections and force=False."""
    result = MongoAdmin(db=mongo_provider.get_db()).init_or_seed_database(force=False)

    assert result["seeded"] is False
    assert result["reason"] == "db_not_empty"
    assert result["db_name"]


@pytest.mark.unit
def test_backup_db_writes_manifest_and_collection_backups(mongo_provider, tmp_path):
    """backup_db writes manifest and ndjson/index files for each collection."""
    db = mongo_provider.get_db()
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
