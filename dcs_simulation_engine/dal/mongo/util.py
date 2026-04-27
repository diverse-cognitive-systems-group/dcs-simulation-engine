"""Mongo DAL utility helpers.

This module is intentionally stateless. Connection ownership is handled by
bootstrap/runtime wiring and passed into DAL objects explicitly.
"""

import json
from pathlib import Path
from typing import Any

from bson import ObjectId, json_util
from dcs_simulation_engine.dal.base import PlayerRecord
from dcs_simulation_engine.dal.mongo.const import (
    DEFAULT_DB_NAME,
    INDEX_DEFS,
    MongoColumns,
)
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.time import utc_now
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, MongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.database import Database


def player_id_variants(player_id: str | Any | None) -> list[Any]:
    """Return equivalent player id values (string and ObjectId variants)."""
    if player_id is None:
        return []

    variants: list[Any] = [player_id]
    if isinstance(player_id, str):
        try:
            variants.append(ObjectId(player_id))
        except Exception:
            pass

    out: list[Any] = []
    seen: set[str] = set()
    for value in variants:
        key = repr(value)
        if key not in seen:
            out.append(value)
            seen.add(key)
    return out


def ensure_default_indexes(db: Database[Any]) -> None:
    """Create baseline indexes used by runtime and tests."""
    db[MongoColumns.PLAYERS].create_index("access_key", unique=True, sparse=True)
    db[MongoColumns.PII].create_index(MongoColumns.PLAYER_ID, unique=True)
    db[MongoColumns.SESSIONS].create_index(MongoColumns.SESSION_ID, unique=True)
    db[MongoColumns.SESSIONS].create_index([(MongoColumns.PLAYER_ID, ASCENDING), (MongoColumns.SESSION_STARTED_AT, DESCENDING)])
    db[MongoColumns.SESSIONS].create_index([(MongoColumns.STATUS, ASCENDING), (MongoColumns.UPDATED_AT, DESCENDING)])
    db[MongoColumns.SESSIONS].create_index([(MongoColumns.BRANCH_FROM_SESSION_ID, ASCENDING), (MongoColumns.UPDATED_AT, DESCENDING)])
    db[MongoColumns.SESSION_EVENTS].create_index(
        [(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.SEQ, ASCENDING)],
        unique=True,
    )
    db[MongoColumns.SESSION_EVENTS].create_index(MongoColumns.EVENT_ID, unique=True)
    db[MongoColumns.SESSION_EVENTS].create_index([(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.EVENT_TS, ASCENDING)])
    db[MongoColumns.EXPERIMENTS].create_index(MongoColumns.NAME, unique=True)
    db[MongoColumns.ASSIGNMENTS].create_index(MongoColumns.ASSIGNMENT_ID, unique=True)
    db[MongoColumns.ASSIGNMENTS].create_index(
        [
            (MongoColumns.EXPERIMENT_NAME, ASCENDING),
            (MongoColumns.PLAYER_ID, ASCENDING),
            (MongoColumns.UPDATED_AT, DESCENDING),
        ]
    )
    db[MongoColumns.ASSIGNMENTS].create_index(
        [
            (MongoColumns.EXPERIMENT_NAME, ASCENDING),
            (MongoColumns.STATUS, ASCENDING),
            (MongoColumns.UPDATED_AT, DESCENDING),
        ]
    )
    db[MongoColumns.ASSIGNMENTS].create_index(
        [
            (MongoColumns.EXPERIMENT_NAME, ASCENDING),
            (MongoColumns.GAME_NAME, ASCENDING),
            (MongoColumns.STATUS, ASCENDING),
        ]
    )
    db[MongoColumns.ASSIGNMENTS].create_index(MongoColumns.ACTIVE_SESSION_ID, sparse=True)
    db[MongoColumns.FORMS].create_index(
        [(MongoColumns.PLAYER_ID, ASCENDING), (MongoColumns.EXPERIMENT_NAME, ASCENDING)],
        unique=True,
    )

    for collection_name, defs in INDEX_DEFS.items():
        coll = db[collection_name]
        for spec in defs:
            coll.create_index(spec["fields"], unique=spec.get("unique", False))


async def ensure_default_indexes_async(db: AsyncDatabase[Any]) -> None:
    """Create baseline indexes used by async runtime paths."""
    await db[MongoColumns.PLAYERS].create_index("access_key", unique=True, sparse=True)
    await db[MongoColumns.PII].create_index(MongoColumns.PLAYER_ID, unique=True)
    await db[MongoColumns.SESSIONS].create_index(MongoColumns.SESSION_ID, unique=True)
    await db[MongoColumns.SESSIONS].create_index([(MongoColumns.PLAYER_ID, ASCENDING), (MongoColumns.SESSION_STARTED_AT, DESCENDING)])
    await db[MongoColumns.SESSIONS].create_index([(MongoColumns.STATUS, ASCENDING), (MongoColumns.UPDATED_AT, DESCENDING)])
    await db[MongoColumns.SESSIONS].create_index(
        [(MongoColumns.BRANCH_FROM_SESSION_ID, ASCENDING), (MongoColumns.UPDATED_AT, DESCENDING)]
    )
    await db[MongoColumns.SESSION_EVENTS].create_index(
        [(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.SEQ, ASCENDING)],
        unique=True,
    )
    await db[MongoColumns.SESSION_EVENTS].create_index(MongoColumns.EVENT_ID, unique=True)
    await db[MongoColumns.SESSION_EVENTS].create_index([(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.EVENT_TS, ASCENDING)])
    await db[MongoColumns.EXPERIMENTS].create_index(MongoColumns.NAME, unique=True)
    await db[MongoColumns.ASSIGNMENTS].create_index(MongoColumns.ASSIGNMENT_ID, unique=True)
    await db[MongoColumns.ASSIGNMENTS].create_index(
        [
            (MongoColumns.EXPERIMENT_NAME, ASCENDING),
            (MongoColumns.PLAYER_ID, ASCENDING),
            (MongoColumns.UPDATED_AT, DESCENDING),
        ]
    )
    await db[MongoColumns.ASSIGNMENTS].create_index(
        [
            (MongoColumns.EXPERIMENT_NAME, ASCENDING),
            (MongoColumns.STATUS, ASCENDING),
            (MongoColumns.UPDATED_AT, DESCENDING),
        ]
    )
    await db[MongoColumns.ASSIGNMENTS].create_index(
        [
            (MongoColumns.EXPERIMENT_NAME, ASCENDING),
            (MongoColumns.GAME_NAME, ASCENDING),
            (MongoColumns.STATUS, ASCENDING),
        ]
    )
    await db[MongoColumns.ASSIGNMENTS].create_index(MongoColumns.ACTIVE_SESSION_ID, sparse=True)
    await db[MongoColumns.FORMS].create_index(
        [(MongoColumns.PLAYER_ID, ASCENDING), (MongoColumns.EXPERIMENT_NAME, ASCENDING)],
        unique=True,
    )

    for collection_name, defs in INDEX_DEFS.items():
        coll = db[collection_name]
        for spec in defs:
            await coll.create_index(spec["fields"], unique=spec.get("unique", False))


def connect_db(
    *,
    uri: str,
    db_name: str = DEFAULT_DB_NAME,
    client_factory: Any | None = None,
) -> Database[Any]:
    """Create a MongoDB DB handle from an explicit URI."""
    factory = client_factory or MongoClient
    client = factory(uri, tz_aware=True)
    client.admin.command("ping")
    db = client[db_name]
    ensure_default_indexes(db)
    return db


async def connect_db_async(
    *,
    uri: str,
    db_name: str = DEFAULT_DB_NAME,
    client_factory: Any | None = None,
) -> AsyncDatabase[Any]:
    """Create an async MongoDB DB handle from an explicit URI."""
    factory = client_factory or AsyncMongoClient
    client = factory(uri, tz_aware=True)
    await client.admin.command("ping")
    db = client[db_name]
    await ensure_default_indexes_async(db)
    return db


def _make_dump_root(path: str | Path) -> Path:
    """Create and return the timestamped dump directory."""
    base_path = Path(path)
    root = base_path / utc_now().strftime("%Y_%m_%d_%H_%M_%S")
    root.mkdir(parents=True, exist_ok=False)
    return root


def _write_dump_manifest(root: Path, *, db_name: str, collections: list[str]) -> None:
    """Write dump metadata alongside collection payloads."""
    manifest = {
        "db_name": db_name,
        "created_at": utc_now().isoformat(),
        "collections": collections,
        "format": {
            "collection_dump": "<collection>.json",
            "indexes_dump": "<collection>.__indexes__.json",
            "json_encoding": "bson.json_util extended json",
        },
    }
    (root / "__manifest__.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_collection_indexes(root: Path, *, collection_name: str, index_info: dict[str, Any]) -> None:
    """Write one collection's index metadata to disk."""
    (root / f"{collection_name}.__indexes__.json").write_text(
        json.dumps(index_info, default=json_util.default, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_all_collections_to_json(db: Database[Any], path: str | Path) -> Path:
    """Dump every collection to JSON plus backup metadata files."""
    root = _make_dump_root(path)
    collection_names = sorted(db.list_collection_names())

    for collection_name in collection_names:
        out_path = root / f"{collection_name}.json"
        cursor = db[collection_name].find({})
        with out_path.open("w", encoding="utf-8") as f:
            f.write("[\n")
            first = True
            try:
                for doc in cursor:
                    if not first:
                        f.write(",\n")
                    f.write(json_util.dumps(doc))
                    first = False
            finally:
                cursor.close()
            f.write("\n]\n")
        _write_collection_indexes(root, collection_name=collection_name, index_info=db[collection_name].index_information())

    _write_dump_manifest(root, db_name=db.name, collections=collection_names)

    return root


async def dump_all_collections_to_json_async(db: AsyncDatabase[Any] | Database[Any] | Any, path: str | Path) -> Path:
    """Dump every collection to JSON plus backup metadata files."""
    root = _make_dump_root(path)
    collection_names = sorted(await maybe_await(db.list_collection_names()))

    for collection_name in collection_names:
        out_path = root / f"{collection_name}.json"
        cursor = db[collection_name].find({})
        with out_path.open("w", encoding="utf-8") as f:
            f.write("[\n")
            first = True
            try:
                if hasattr(cursor, "__aiter__"):
                    async for doc in cursor:
                        if not first:
                            f.write(",\n")
                        f.write(json_util.dumps(doc))
                        first = False
                else:
                    for doc in cursor:
                        if not first:
                            f.write(",\n")
                        f.write(json_util.dumps(doc))
                        first = False
            finally:
                await maybe_await(cursor.close())
            f.write("\n]\n")
        _write_collection_indexes(
            root,
            collection_name=collection_name,
            index_info=await maybe_await(db[collection_name].index_information()),
        )

    db_name = getattr(db, "name", "")
    _write_dump_manifest(root, db_name=db_name, collections=collection_names)

    return root


def sanitize_player_data(player_data: dict[str, Any]) -> dict[str, Any]:
    """Remove access-key fields from player_data and set a default created_at."""
    data = dict(player_data)

    for k in (
        "access_key",
        "access_key_revoked",
    ):
        data.pop(k, None)

    data.setdefault(MongoColumns.CREATED_AT, utc_now())
    return data


def split_pii(player_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split player_data into (non_pii, pii) dicts based on PII field definitions."""
    non_pii: dict[str, Any] = {}
    pii: dict[str, Any] = {}

    for key, value in player_data.items():
        if key in MongoColumns.PII_META_KEYS or key == MongoColumns.CREATED_AT:
            non_pii[key] = value
            continue

        if isinstance(value, dict):
            field_key = value.get("key", key)
            answer = value.get("answer")

            is_pii = bool(value.get("pii")) or field_key in MongoColumns.PII_KEYS or key in MongoColumns.PII_KEYS

            if not is_pii:
                non_pii[key] = value
            else:
                v_clean = dict(value)
                v_clean.pop("answer", None)
                non_pii[key] = v_clean

                if answer not in (None, "", [], {}):
                    pii[field_key] = answer
        else:
            if key in MongoColumns.PII_KEYS:
                if value not in (None, "", [], {}):
                    pii[key] = value
            else:
                non_pii[key] = value

    return non_pii, pii


def player_doc_to_record(doc: dict[str, Any]) -> PlayerRecord:
    """Convert a raw MongoDB player document to a PlayerRecord."""
    known = {"id", "_id", "created_at", "access_key"}
    return PlayerRecord(
        id=doc.get("id") or str(doc.get("_id", "")),
        created_at=doc.get("created_at"),
        access_key=doc.get("access_key"),
        data={k: v for k, v in doc.items() if k not in known},
    )
