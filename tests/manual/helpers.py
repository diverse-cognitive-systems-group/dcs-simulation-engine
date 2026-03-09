"""Helpers for manual tests (notebooks)."""

import os
import uuid
from pathlib import Path
from typing import Any

import dcs_simulation_engine.dal.mongo as mongo
import mongomock
from dcs_simulation_engine.dal.mongo.util import (
    ensure_default_indexes,
)
from loguru import logger
from pymongo.database import Database

_manual_client: mongomock.MongoClient | None = None
_manual_db: Database[Any] | None = None


def _collection_name_from_stem(stem: str) -> str:
    """Map a file stem.

    Eg. 'runs' to a collection name.
    If mongo exposes a constant like RUNS_COL, prefer that.
    """
    const = f"{stem.upper()}_COL"
    return getattr(mongo, const, stem)


def _load_json_file(path: Path) -> list[dict]:
    """Load JSON or NDJSON into a list of dicts."""
    import json

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Try standard JSON first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            # filter only dict-like items
            return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        # Fallback: NDJSON (one JSON object per line)
        objs: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if isinstance(obj, dict):
                objs.append(obj)
        return objs

    return []


def _seed_from_dir(db: Database[Any], seed_dir: Path) -> None:
    """Insert documents from all JSON files in seed_dir."""
    if not seed_dir.exists():
        raise FileNotFoundError(f"Seed directory not found: {seed_dir}")

    # Deterministic order
    files = sorted([p for p in seed_dir.glob("*.json") if p.is_file()])
    for file in files:
        docs = _load_json_file(file)
        if not docs:
            logger.debug(f"No documents found in {file.name}; skipping.")
            continue

        colname = _collection_name_from_stem(file.stem)
        logger.debug(f"Seeding {len(docs)} docs into collection '{colname}' from {file.name} to run tests.")
        db[colname].insert_many(docs)


def use_mongomock_for_db(seed_data: bool = False) -> None:
    """A helper to call in manual nb tests to make sure they use mongomock."""
    global _manual_client, _manual_db

    os.environ["MONGO_URI"] = f"mongodb://localhost:27017/testdb_{uuid.uuid4().hex}"
    os.environ["ACCESS_KEY_PEPPER"] = ""

    dbname = os.environ["MONGO_URI"].rsplit("/", 1)[-1]
    _manual_client = mongomock.MongoClient(tz_aware=True)
    _manual_db = _manual_client[dbname]
    ensure_default_indexes(_manual_db)

    if seed_data:
        seed_path = Path(__file__).parent.parent.parent / "database_seeds" / "dev"
        if seed_path.exists():
            _seed_from_dir(_manual_db, seed_path)
        else:
            raise FileNotFoundError(f"Seed data directory not found: {seed_path}")
