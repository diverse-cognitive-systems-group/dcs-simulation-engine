"""MongoDB administrative operations for CLI bootstrap and teardown."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from bson import json_util
from dcs_simulation_engine.dal.mongo.const import (
    DEFAULT_SEEDS_DIR,
    INDEX_DEFS,
)
from loguru import logger
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import CollectionInvalid


class MongoAdmin:
    """Administrative operations over a specific Mongo DB handle."""

    def __init__(self, db: Database[Any]) -> None:
        """Bind admin operations to the given database handle."""
        self._db = db

    def init_or_seed_database(
        self,
        *,
        seeds_dir: Path | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Seed configured DB from seed files, optionally replacing existing data."""
        db = self._db

        if seeds_dir is None:
            seeds_dir = DEFAULT_SEEDS_DIR

        if not seeds_dir.exists() or not seeds_dir.is_dir():
            raise ValueError(f"Seeds directory not found: {seeds_dir}")

        seed_paths = self.discover_seed_files(seeds_dir)
        if not seed_paths:
            raise ValueError(f"No seed files found in {seeds_dir} (expected *.json or *.ndjson).")

        existing = db.list_collection_names()
        if existing and not force:
            return {
                "seeded": False,
                "reason": "db_not_empty",
                "db_name": db.name,
                "existing_collections": existing,
                "seeds_dir": str(seeds_dir),
                "seed_files": [p.name for p in seed_paths],
            }

        self.seed_database(db, seed_paths)
        return {
            "seeded": True,
            "db_name": db.name,
            "existing_collections": existing,
            "seeds_dir": str(seeds_dir),
            "seed_files": [p.name for p in seed_paths],
        }

    def backup_db(self, outdir: Path, *, append_ts: bool = True) -> Path:
        """Backup entire DB to a directory. Returns the path written."""
        db = self._db

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = Path(outdir) / (f"{ts}" if append_ts else "db")
        root.mkdir(parents=True, exist_ok=False)

        collections = sorted(db.list_collection_names())

        for coll_name in collections:
            self.backup_collection(db, coll_name, root)

        manifest = {
            "db_name": db.name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "collections": collections,
            "format": {
                "collection_dump": "<collection>.ndjson",
                "indexes_dump": "<collection>.__indexes__.json",
                "ndjson_encoding": "bson.json_util extended json",
            },
        }
        (root / "__manifest__.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        return root

    def discover_seed_files(self, seeds_dir: Path) -> list[Path]:
        """Return sorted .json/.ndjson files found directly in seeds_dir."""
        return [p for p in sorted(seeds_dir.iterdir()) if p.is_file() and p.suffix.lower() in {".json", ".ndjson"}]

    def load_seed_documents(self, path: Path) -> list[dict[str, Any]]:
        """Parse a seed file (.json or .ndjson) and return a list of documents."""
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            logger.debug(f"{path} is empty; skipping.")
            return []

        if path.suffix.lower() == ".ndjson":
            docs: list[dict[str, Any]] = []
            for i, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                obj = json_util.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError(f"Line {i} in {path} is not a JSON object.")
                docs.append(obj)
            return docs

        data = json_util.loads(text)
        if isinstance(data, list):
            if not all(isinstance(x, dict) for x in data):
                raise ValueError(f"Array in {path} must contain only objects.")
            return data

        if isinstance(data, dict) and "documents" in data and isinstance(data["documents"], list):
            docs = data["documents"]
            if not all(isinstance(x, dict) for x in docs):
                raise ValueError(f"'documents' in {path} must be an array of objects.")
            return docs

        raise ValueError(f"Unsupported JSON structure in {path}. Expected array, NDJSON, or object with 'documents'.")

    def backup_root_dir(self, db_name: str) -> Path:
        """Return a timestamped backup root path and create the directory."""
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        root = Path("database_backups") / f"{db_name}-{ts}"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def backup_collection(self, db: Database[Any], coll_name: str, root: Path) -> None:
        """Dump a single collection to ndjson and write its index metadata."""
        coll = db[coll_name]
        out_path = root / f"{coll_name}.ndjson"
        idx_path = root / f"{coll_name}.__indexes__.json"

        with out_path.open("w", encoding="utf-8") as f:
            cursor = coll.find({}).batch_size(1000)
            try:
                for doc in cursor:
                    f.write(json_util.dumps(doc))
                    f.write("\n")
            finally:
                cursor.close()

        with idx_path.open("w", encoding="utf-8") as f:
            json.dump(coll.index_information(), f, default=json_util.default, indent=2)

    def seed_collection(self, coll: Collection[Any], docs: Sequence[dict[str, Any]]) -> int:
        """Drop and repopulate a collection with docs. Returns inserted count."""
        coll.drop()
        if not docs:
            logger.info("Dropped '%s'; creating empty collection.", coll.name)
            try:
                coll.database.create_collection(coll.name)
            except CollectionInvalid:
                pass
            return 0

        result = coll.insert_many(list(docs), ordered=False)
        return len(result.inserted_ids)

    def create_indices(self, coll: Collection[Any]) -> None:
        """Create any configured indexes for the given collection."""
        defs = INDEX_DEFS.get(coll.name)
        if not defs:
            return
        for spec in defs:
            fields = spec["fields"]
            unique = spec.get("unique", False)
            coll.create_index(fields, unique=unique)
            logger.info("Created index on %s: %s (unique=%s)", coll.name, fields, unique)

    def seed_database(self, db: Database[Any], seed_files: Sequence[Path]) -> None:
        """Seed all collections from seed_files, backing up any that already exist."""
        existing = set(db.list_collection_names())
        backup_root: Path | None = None

        for f in seed_files:
            collection_name = f.stem

            if collection_name in existing:
                if backup_root is None:
                    backup_root = self.backup_root_dir(db.name)
                    logger.info(f"Backing up existing collections to {backup_root}")
                logger.info(f"Backing up existing '{collection_name}'...")
                self.backup_collection(db, collection_name, backup_root)

            logger.info(f"Seeding collection '{collection_name}' from {f.name}")
            docs = self.load_seed_documents(f)
            inserted = self.seed_collection(db[collection_name], docs)
            logger.info(f"Inserted {inserted} document(s) into '{collection_name}'")
            self.create_indices(db[collection_name])
