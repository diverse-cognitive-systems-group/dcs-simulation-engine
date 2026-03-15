"""Mongo DAL utility helpers.

This module is intentionally stateless. Connection ownership is handled by
bootstrap/runtime wiring and passed into DAL objects explicitly.
"""

from typing import Any

from bson import ObjectId
from dcs_simulation_engine.dal.base import PlayerRecord
from dcs_simulation_engine.dal.mongo.const import (
    DEFAULT_DB_NAME,
    INDEX_DEFS,
    MongoColumns,
)
from dcs_simulation_engine.utils.time import utc_now
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient, MongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.collection import Collection
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
    db[MongoColumns.SESSIONS].create_index(
        [(MongoColumns.PLAYER_ID, ASCENDING), (MongoColumns.SESSION_STARTED_AT, DESCENDING)]
    )
    db[MongoColumns.SESSIONS].create_index([(MongoColumns.STATUS, ASCENDING), (MongoColumns.UPDATED_AT, DESCENDING)])
    db[MongoColumns.SESSION_EVENTS].create_index(
        [(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.SEQ, ASCENDING)],
        unique=True,
    )
    db[MongoColumns.SESSION_EVENTS].create_index(MongoColumns.EVENT_ID, unique=True)
    db[MongoColumns.SESSION_EVENTS].create_index(
        [(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.EVENT_TS, ASCENDING)]
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
    await db[MongoColumns.SESSIONS].create_index(
        [(MongoColumns.PLAYER_ID, ASCENDING), (MongoColumns.SESSION_STARTED_AT, DESCENDING)]
    )
    await db[MongoColumns.SESSIONS].create_index(
        [(MongoColumns.STATUS, ASCENDING), (MongoColumns.UPDATED_AT, DESCENDING)]
    )
    await db[MongoColumns.SESSION_EVENTS].create_index(
        [(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.SEQ, ASCENDING)],
        unique=True,
    )
    await db[MongoColumns.SESSION_EVENTS].create_index(MongoColumns.EVENT_ID, unique=True)
    await db[MongoColumns.SESSION_EVENTS].create_index(
        [(MongoColumns.SESSION_ID, ASCENDING), (MongoColumns.EVENT_TS, ASCENDING)]
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


def write_pii_fields(db: Database[Any], player_id: str, pii_fields: dict[str, Any]) -> None:
    """Upsert PII fields for a player into the dedicated PII collection."""
    if not pii_fields:
        return

    pii_coll: Collection[Any] = db[MongoColumns.PII]
    pii_coll.update_one(
        {MongoColumns.PLAYER_ID: player_id},
        {
            "$set": {
                MongoColumns.PLAYER_ID: player_id,
                MongoColumns.FIELDS: pii_fields,
                MongoColumns.UPDATED_AT: utc_now(),
            },
            "$setOnInsert": {MongoColumns.CREATED_AT: utc_now()},
        },
        upsert=True,
    )


def player_doc_to_record(doc: dict[str, Any]) -> PlayerRecord:
    """Convert a raw MongoDB player document to a PlayerRecord."""
    known = {"id", "_id", "created_at", "access_key"}
    return PlayerRecord(
        id=doc.get("id") or str(doc.get("_id", "")),
        created_at=doc.get("created_at"),
        access_key=doc.get("access_key"),
        data={k: v for k, v in doc.items() if k not in known},
    )
