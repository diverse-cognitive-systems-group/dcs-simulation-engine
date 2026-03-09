"""Mongo DAL utility helpers.

This module is intentionally stateless. Connection ownership is handled by
bootstrap/runtime wiring and passed into DAL objects explicitly.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from dcs_simulation_engine.dal.base import PlayerRecord
from dcs_simulation_engine.dal.mongo.const import (
    DEFAULT_DB_NAME,
    INDEX_DEFS,
    MongoColumns,
)
from loguru import logger
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


def now(delta: str | int = 0) -> datetime:
    """UTC now, with +/- flexible units if delta is a string."""
    base = datetime.now(timezone.utc)

    if isinstance(delta, int):
        return base + timedelta(days=delta)

    if not isinstance(delta, str):
        raise TypeError(f"delta must be str or int, got {type(delta).__name__}")

    m = re.fullmatch(r"\s*([+-]\d+)([smdwy])\s*", delta)
    if not m:
        raise ValueError(f"bad delta: {delta!r}")

    n = int(m.group(1))
    u = m.group(2).lower()
    if u == "y":
        return base + timedelta(days=365 * n)  # rough year

    unit_to_kwarg = {
        "s": "seconds",
        "m": "minutes",
        "d": "days",
        "w": "weeks",
    }
    return base + timedelta(**{unit_to_kwarg[u]: n})


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
    db[MongoColumns.PLAYERS].create_index("access_key_hash")
    db[MongoColumns.PLAYERS].create_index([("access_key_revoked", ASCENDING), ("access_key_prefix", ASCENDING)])
    db[MongoColumns.RUNS].create_index(
        [
            ("player_id", ASCENDING),
            (MongoColumns.CREATED_AT, DESCENDING),
            (MongoColumns.UPDATED_AT, DESCENDING),
        ]
    )
    db[MongoColumns.RUNS].create_index([("player_id", ASCENDING), ("played_at", DESCENDING)])
    db[MongoColumns.RUNS].create_index([("game_name", ASCENDING), ("player_id", ASCENDING)])
    db[MongoColumns.RUNS].create_index([("game_config.name", ASCENDING), ("player_id", ASCENDING)])

    for collection_name, defs in INDEX_DEFS.items():
        coll = db[collection_name]
        for spec in defs:
            coll.create_index(spec["fields"], unique=spec.get("unique", False))


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


def sanitize_player_data(player_data: dict[str, Any]) -> dict[str, Any]:
    """Remove access-key fields from player_data and set a default created_at."""
    data = dict(player_data)

    for k in (
        "access_key",
        "access_key_hash",
        "access_key_prefix",
        "access_key_revoked",
    ):
        data.pop(k, None)

    data.setdefault(MongoColumns.CREATED_AT, now())
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
        {"player_id": player_id},
        {
            "$set": {
                "player_id": player_id,
                "fields": pii_fields,
                "updated_at": now(),
            },
            "$setOnInsert": {"created_at": now()},
        },
        upsert=True,
    )


def save_run_data(
    db: Database[Any],
    player_id: str | Any,
    run_data: dict[str, Any],
    *,
    run_id: str | Any | None = None,
    timestamp_field: str = MongoColumns.CREATED_AT,
) -> str:
    """Persist run_data for a player; upsert if run_id is given, else insert. Returns run id."""
    if not isinstance(run_data, dict):
        raise ValueError("run_data must be a dict")

    data = dict(run_data)
    data["player_id"] = player_id
    data.setdefault(timestamp_field, now())

    coll: Collection[Any] = db[MongoColumns.RUNS]
    if run_id is not None:
        coll.update_one({"_id": run_id}, {"$set": data}, upsert=True)
        rid = str(run_id)
    else:
        rid = str(coll.insert_one(data).inserted_id)

    logger.debug(f"Saved run {rid} for player {player_id}")
    return rid


def player_doc_to_record(doc: dict[str, Any]) -> PlayerRecord:
    """Convert a raw MongoDB player document to a PlayerRecord."""
    known = {"id", "_id", "created_at", "access_key_hash", "access_key_prefix"}
    return PlayerRecord(
        id=doc.get("id") or str(doc.get("_id", "")),
        created_at=doc.get("created_at"),
        access_key_hash=doc.get("access_key_hash"),
        access_key_prefix=doc.get("access_key_prefix"),
        data={k: v for k, v in doc.items() if k not in known},
    )
