"""Helpers for database operations."""

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from bson import ObjectId, json_util
from dotenv import load_dotenv
from loguru import logger
from mnemonic import Mnemonic
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from pymongo.errors import CollectionInvalid, OperationFailure

from dcs_simulation_engine.helpers.docker_helpers import (
    ensure_mongo_running,
    get_mongodb_ip,
)

load_dotenv()

# Collections / fields
PLAYERS_COL = "players"
RUNS_COL = "runs"
PII_COL = "pii"
# Mongo doesn't handle created_at or updated_at automatically.
DEFAULT_CREATEDAT_FIELD = "created_at"
DEFAULT_UPDATEDAT_FIELD = "updated_at"
DEFAULT_DB_NAME: str = "dcs-db"
DEFAULT_MONGO_URI = "mongodb://mongo:27017/"
SEEDS_DIR_DEFAULT = Path("database_seeds")
DEFAULT_PII_KEYS = {
    "full_name",
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "phone_number",
}
PII_META_KEYS = {
    "access_key",
    "access_key_hash",
    "access_key_prefix",
    "access_key_revoked",
    "created_at",
    "last_key_issued_at",
}

_DELTA_DAYS_RE = re.compile(r"__delta_days(-?\d+)__\Z")

# Key settings
ACCESS_KEY_PEPPER = os.getenv("ACCESS_KEY_PEPPER", "")
DEFAULT_KEY_PREFIX = "ak-"

_client: Optional[MongoClient[Any]] = None
_db = None

_NOW_TOKEN = re.compile(r"^__now([+-]\d+)([smdwy])__$", re.IGNORECASE)

SUPPORTED_EXTS = {".json", ".ndjson"}

INDEX_DEFS: dict[str, list[dict[str, Any]]] = {
    "characters": [{"fields": [("hid", 1)], "unique": True}],
}


def get_db() -> Database[Any]:
    """Return a MongoDB database handle.

    Looks for MONGO_URI in env; falls back to localhost default.
    """
    global _client, _db
    if _db is not None:
        return _db

    uri = os.getenv("MONGO_URI")
    if not uri:
        ensure_mongo_running()
        # TODO: IP addresses can change if docker services restart, etc, this
        # may not always work as expected in all environments.
        ip = get_mongodb_ip()
        uri = f"mongodb://{ip}:27017/"
        logger.debug(f"MONGO_URI not set in env; defaulting to local db ({uri})")

    _client = MongoClient(uri, tz_aware=True)
    # make sure mongo is reachable
    _client.admin.command("ping")

    # TODO: move to proper migration system
    _db = _client[DEFAULT_DB_NAME]
    _db[PLAYERS_COL].create_index("access_key_hash")
    _db[PLAYERS_COL].create_index(
        [("access_key_revoked", ASCENDING), ("access_key_prefix", ASCENDING)]
    )
    _db[RUNS_COL].create_index(
        [
            ("player_id", ASCENDING),
            (DEFAULT_CREATEDAT_FIELD, DESCENDING),
            (DEFAULT_UPDATEDAT_FIELD, DESCENDING),
        ]
    )
    _db[RUNS_COL].create_index([("player_id", ASCENDING), ("played_at", DESCENDING)])
    _db[RUNS_COL].create_index(
        [("game_config.name", ASCENDING), ("player_id", ASCENDING)]
    )

    return _db


def init_or_seed_database(
    *,
    seeds_dir: Optional[Path] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Seed the configured database from seed files.

    Uses get_db() for connection (MONGO_URI).

    Backs up any existing collections before replacing them.

    Returns a small summary dict so the CLI can print friendly output.
    """
    if _client is None:
        db = get_db()
    else:
        db = _client[DEFAULT_DB_NAME]

    if seeds_dir is None:
        seeds_dir = SEEDS_DIR_DEFAULT

    if not seeds_dir.exists() or not seeds_dir.is_dir():
        raise ValueError(f"Seeds directory not found: {seeds_dir}")

    seed_paths = discover_seed_files(seeds_dir)
    if not seed_paths:
        raise ValueError(
            f"No seed files found in {seeds_dir} (expected *.json or *.ndjson)."
        )

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

    seed_database(db, seed_paths)
    return {
        "seeded": True,
        "db_name": db.name,
        "existing_collections": existing,
        "seeds_dir": str(seeds_dir),
        "seed_files": [p.name for p in seed_paths],
    }


def warn_if_db_name_exists(db_name: str) -> bool:
    """Best-effort: return True if server reports db_name exists, else False.

    If the user lacks privileges to list DBs, this returns False (no warning).
    """
    # Ensure client/db initialized
    db = get_db()  # noqa
    client = _client
    if client is None:
        return False

    try:
        names = client.list_database_names()
    except OperationFailure:
        # Common with least-privilege Atlas users
        return False
    except Exception:
        return False

    return db_name in names


def database_has_data(db: Optional[Database[Any]] = None) -> bool:
    """Return True if the database appears non-empty (has any collections)."""
    db = db or get_db()
    return bool(db.list_collection_names())


def backup_root_dir(db_name: str) -> Path:
    """Create and return a timestamped backup root directory."""
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    root = Path("database_backups") / f"{db_name}-{ts}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def backup_collection(db: Database, coll_name: str, root: Path) -> None:
    """Dump an existing collection to NDJSON + save index info."""
    coll = db[coll_name]
    out_path = root / f"{coll_name}.ndjson"
    idx_path = root / f"{coll_name}.__indexes__.json"

    with out_path.open("w", encoding="utf-8") as f:
        # Note: Atlas doesn't allow noTimeout cursor on free tiers (eg. for dev work)
        # switching to a normal cursor but if/when dbs grow large we may need to revisit
        # cursor = coll.find({}, no_cursor_timeout=True).batch_size(1000)
        cursor = coll.find({}).batch_size(1000)

        try:
            for doc in cursor:
                f.write(json_util.dumps(doc))
                f.write("\n")
        finally:
            cursor.close()

    with idx_path.open("w", encoding="utf-8") as f:
        json.dump(coll.index_information(), f, default=json_util.default, indent=2)


def load_seed_documents(path: Path) -> List[Dict[str, Any]]:
    """Load documents from a seed file."""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        logger.warning(f"{path} is empty; skipping.")
        return []

    if path.suffix.lower() == ".ndjson":
        docs: List[Dict[str, Any]] = []
        for i, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"Line {i} in {path} is not a JSON object.")
            docs.append(obj)
        return docs

    data = json.loads(text)
    if isinstance(data, list):
        if not all(isinstance(x, dict) for x in data):
            raise ValueError(f"Array in {path} must contain only objects.")
        return data  # type: ignore[return-value]

    if (
        isinstance(data, dict)
        and "documents" in data
        and isinstance(data["documents"], list)
    ):
        docs = data["documents"]
        if not all(isinstance(x, dict) for x in docs):
            raise ValueError(f"'documents' in {path} must be an array of objects.")
        return docs  # type: ignore[return-value]

    raise ValueError(
        f"Unsupported JSON structure in {path}. Expected array"
        ", NDJSON, or object with 'documents'."
    )


def discover_seed_files(seeds_dir: Path) -> List[Path]:
    """Return list of seed files in the given directory."""
    return [
        p
        for p in sorted(seeds_dir.iterdir())
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]


def seed_collection(coll: Collection, docs: Sequence[Dict[str, Any]]) -> int:
    """Seed a collection with the given documents (after dropping existing data)."""
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


def create_indices(coll: Collection) -> None:
    """Create indices for a collection based on predefined index definitions."""
    defs = INDEX_DEFS.get(coll.name)
    if not defs:
        return
    for spec in defs:
        fields = spec["fields"]
        unique = spec.get("unique", False)
        coll.create_index(fields, unique=unique)
        logger.info("Created index on %s: %s (unique=%s)", coll.name, fields, unique)


def seed_database(db: Database, seed_files: Iterable[Path]) -> None:
    """Seed a database from the given seed files, backing up existing collections."""
    existing = set(db.list_collection_names())
    backup_root: Path | None = None

    for f in seed_files:
        collection_name = f.stem

        if collection_name in existing:
            if backup_root is None:
                backup_root = backup_root_dir(db.name)
                logger.info(f"Backing up existing collections to {backup_root}")
            logger.info(f"Backing up existing '{collection_name}'...")
            backup_collection(db, collection_name, backup_root)

        logger.info(f"Seeding collection '{collection_name}' from {f.name}")
        docs = load_seed_documents(f)
        inserted = seed_collection(db[collection_name], docs)
        logger.info(f"Inserted {inserted} document(s) into '{collection_name}'")
        create_indices(db[collection_name])


def now(delta: Union[str, int] = 0) -> datetime:
    """UTC now, with +/- flexible units if delta is a string."""
    base = datetime.now(timezone.utc)
    if isinstance(delta, int):
        return base + timedelta(days=delta)

    m = re.fullmatch(r"\s*([+-]\d+)([smdwy])\s*", delta)
    if not m:
        raise ValueError(f"bad delta: {delta!r}")

    n = int(m.group(1))
    u = m.group(2).lower()

    if u == "s":
        dt = timedelta(seconds=n)
    elif u == "m":
        dt = timedelta(minutes=n)
    elif u == "d":
        dt = timedelta(days=n)
    elif u == "w":
        dt = timedelta(weeks=n)
    elif u == "y":
        dt = timedelta(days=365 * n)  # rough year
    else:
        raise AssertionError

    return base + dt


def _resolve_magic_tokens(obj: Any) -> Any:
    """Resolve __now±N<unit>__ tokens recursively."""
    if isinstance(obj, Mapping):
        return {k: _resolve_magic_tokens(v) for k, v in obj.items()}
    # if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
    #     return [_resolve_magic_tokens(x) for x in obj]
    if isinstance(obj, str):
        m = _NOW_TOKEN.fullmatch(obj)
        if m:
            return now(m.group(1) + m.group(2))
    return obj


def _hash_key(raw: str) -> str:
    return (
        hmac.new(ACCESS_KEY_PEPPER.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if ACCESS_KEY_PEPPER
        else hashlib.sha256(raw.encode()).hexdigest()
    )


def _new_access_key_bip39(
    *,
    prefix: str = DEFAULT_KEY_PREFIX,
    words: Literal[12, 15, 18, 21, 24] = 12,
    language: Literal[
        "english",
        "spanish",
        "french",
        "italian",
        "japanese",
        "korean",
        "chinese_simplified",
        "chinese_traditional",
    ] = "english",
    delimiter: str = "-",
) -> Tuple[str, str, str]:
    """Generate a human-readable access key using a BIP-39 mnemonic.

    The mnemonic encodes cryptographically strong entropy with a built-in checksum,
    making it easy to read/record while retaining strong security.

    Args:
        prefix: String prepended to the key (e.g., "ak-").
        words:  Number of BIP-39 words. 12 ≈ 128-bit entropy; 24 ≈ 256-bit.
        language: BIP-39 wordlist language.
        delimiter: Separator used between words (e.g., "-" for URLs and easy typing).

    Returns:
        (raw_key, prefix_fragment, digest_hex)
            raw_key         -> e.g., "ak-apple-bridge-...-zone"
            prefix_fragment -> the first 8 chars of the raw key (for display/lookup)
            digest_hex      -> SHA-256 (or HMAC-SHA256) digest of raw_key

    Notes:
        • Store only `digest_hex`; show `raw_key` exactly once to the user.
        • BIP-39 checksum detects common typos/transpositions.
        • For long-term tokens, prefer 12 words (128-bit) or higher.
    """
    if words not in (12, 15, 18, 21, 24):
        raise ValueError("`words` must be one of: 12, 15, 18, 21, 24")

    m = Mnemonic(language)
    # Mnemonic library accepts strength in bits (128, 160, 192, 224, 256).
    strength_map = {12: 128, 15: 160, 18: 192, 21: 224, 24: 256}
    phrase: str = m.generate(strength=strength_map[words])

    # Normalize: join with chosen delimiter and prepend your key prefix.
    human = phrase.replace("  ", " ").strip().replace(" ", delimiter)
    raw_key = f"{prefix}{human}"

    # Keep a short prefix fragment for quick identification (matches your prior API).
    prefix_fragment = raw_key[:8]
    digest = _hash_key(raw_key)
    return raw_key, prefix_fragment, digest


def validate_access_key_bip39(
    raw_key: str,
    *,
    prefix: str = DEFAULT_KEY_PREFIX,
    language: Literal[
        "english",
        "spanish",
        "french",
        "italian",
        "japanese",
        "korean",
        "chinese_simplified",
        "chinese_traditional",
    ] = "english",
    delimiter: str = "-",
) -> bool:
    """Validate a presented access key’s mnemonic checksum (format + BIP-39).

    This does NOT authenticate (you still compare digests in DB); it only verifies
    that the human-readable part is a valid BIP-39 phrase with the right checksum.

    Args:
        raw_key: The user-presented key (e.g., "ak-apple-bridge-...-zone").
        prefix:  Expected prefix (e.g., "ak-").
        language: Wordlist language used when generating the key.
        delimiter: Separator used between words during generation.

    Returns:
        True if the mnemonic portion is well-formed and checksum-valid; else False.
    """
    if not raw_key.startswith(prefix):
        return False
    mnemonic_part = raw_key[len(prefix) :].replace(delimiter, " ").strip()
    return Mnemonic(language).check(mnemonic_part)


def get_player_id_from_access_key(access_key: str) -> Optional[str]:
    """Look up player by access key (hash match, not revoked)."""
    key = (access_key or "").strip()
    if not key:
        return None
    try:
        doc = get_db()[PLAYERS_COL].find_one(
            {"access_key_hash": _hash_key(key), "access_key_revoked": False},
            projection={"_id": 1},
        )
        return str(doc["_id"]) if doc else None
    except Exception as e:
        logger.error(f"get_player_id_from_access_key failed: {e}")
        return None


def _sanitize_player_data(player_data: Dict[str, Any]) -> Dict[str, Any]:
    """Prepare player data for the main players collection.

    Steps:
    - Clone the dict (so we don't mutate caller data)
    - Strip access-key-like fields
    - Ensure created-at timestamp is present
    """
    data = dict(player_data)

    for k in (
        "access_key",
        "access_key_hash",
        "access_key_prefix",
        "access_key_revoked",
    ):
        data.pop(k, None)

    data.setdefault(DEFAULT_CREATEDAT_FIELD, now())
    return data


def _split_pii(player_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Split 'player_data' into two non-pii and pii data.

    Behavior:
    - If a field is plain (email="x") and is PII → omit from non_pii_data.
    - If a field is schema-style and marked pii:true OR in DEFAULT_PII_KEYS:
         → keep the field shell in non_pii_data but strip its answer
         → store only the answer in pii_fields.
    - Non-PII fields pass through untouched.
    """
    non_pii: Dict[str, Any] = {}
    pii: Dict[str, Any] = {}

    for key, value in player_data.items():
        if key in PII_META_KEYS or key == DEFAULT_CREATEDAT_FIELD:
            non_pii[key] = value
            continue

        # Schema-style
        if isinstance(value, dict):
            field_key = value.get("key", key)
            answer = value.get("answer")

            is_pii = (
                bool(value.get("pii"))
                or field_key in DEFAULT_PII_KEYS
                or key in DEFAULT_PII_KEYS
            )

            if not is_pii:
                # Not PII → pass through unchanged
                non_pii[key] = value
            else:
                # PII → keep structure but remove answer
                v_clean = dict(value)
                v_clean.pop("answer", None)
                non_pii[key] = v_clean

                # Only store non-empty answers
                if answer not in (None, "", [], {}):
                    pii[field_key] = answer

        else:
            # Plain value
            if key in DEFAULT_PII_KEYS:
                # Completely omit from non_pii, store only in PII
                if value not in (None, "", [], {}):
                    pii[key] = value
            else:
                non_pii[key] = value

    return non_pii, pii


def _write_pii_fields(player_id: str, pii_fields: Dict[str, Any]) -> None:
    """Upsert PII into a separate collection.

    Keyed by player_id.
    Failure here should never prevent player creation.
    """
    if not pii_fields:
        return

    pii_coll: Collection = get_db()[PII_COL]
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


def list_players() -> List[Dict[str, Any]]:
    """Return list of all players (non-PII fields only)."""
    coll: Collection = get_db()[PLAYERS_COL]
    cursor = coll.find({}, projection={"_id": 1, "access_key_hash": 0})
    players = []
    for doc in cursor:
        doc["id"] = str(doc.pop("_id"))
        players.append(doc)
    return players


def create_player(
    player_data: Dict[str, Any],
    *,
    player_id: Optional[Union[str, Any]] = None,
    issue_access_key: bool = False,
) -> Tuple[str, Optional[str]]:
    """Insert or upsert a player and persist any PII in a separate collection."""
    if not isinstance(player_data, dict):
        raise ValueError("player_data must be a dict")

    # 1) Sanitize access-key-related fields & created_at
    sanitized = _sanitize_player_data(player_data)

    # 2) Add access key data if needed
    raw_key: Optional[str] = None
    if issue_access_key:
        raw_key, prefix_fragment, digest = _new_access_key_bip39(
            words=12, language="english"
        )
        sanitized.update(
            {
                "access_key_hash": digest,
                "access_key_prefix": prefix_fragment,
                "access_key_revoked": False,
                "last_key_issued_at": now(),
            }
        )

    # 3) Split sanitized fields into: (non_pii, pii)
    non_pii_data, pii_fields = _split_pii(sanitized)

    # 4) Upsert the main non-PII record
    coll: Collection = get_db()[PLAYERS_COL]
    if player_id is not None:
        coll.update_one({"_id": player_id}, {"$set": non_pii_data}, upsert=True)
        created_id = str(player_id)
    else:
        created_id = str(coll.insert_one(non_pii_data).inserted_id)

    # 5) Persist PII separately
    try:
        if pii_fields:
            _write_pii_fields(created_id, pii_fields)
    except Exception:
        logger.exception("Failed to write PII fields for player %s", created_id)

    logger.info(f"Created/updated player: {created_id} (issued_key={bool(raw_key)})")
    return created_id, raw_key


def save_run_data(
    player_id: Union[str, Any],
    run_data: Dict[str, Any],
    *,
    run_id: Optional[Union[str, Any]] = None,
    timestamp_field: str = DEFAULT_CREATEDAT_FIELD,
) -> str:
    """Insert or upsert a run."""
    if not isinstance(run_data, dict):
        raise ValueError("run_data must be a dict")

    data = dict(run_data)
    data["player_id"] = player_id
    data.setdefault(timestamp_field, now())

    coll: Collection = get_db()[RUNS_COL]
    if run_id is not None:
        coll.update_one({"_id": run_id}, {"$set": data}, upsert=True)
        rid = str(run_id)
    else:
        rid = str(coll.insert_one(data).inserted_id)

    logger.debug(f"Saved run {rid} for player {player_id}")
    return rid


def list_characters() -> List[Dict[str, Any]]:
    """Return list of all characters (non-PII fields only)."""
    coll: Collection = get_db()["characters"]
    cursor = coll.find(
        {},
        projection={
            "_id": 0,
            "hid": 1,
            "short_description": 1,
        },
    )
    return list(cursor)


def list_characters_where(
    query: Mapping[str, Any],
    collection: str,
    player_id: Optional[Union[str, Any]] = None,
    # TODO: add optional what keys to return...all or a list? default to just hid
) -> List[str]:
    """Returns distinct character HIDs using a Mongo query dict.

    Accepts either:
      • bare mapping treated as 'where', or
      • {"where": {...}, "order_by": ["field", "asc|desc"], "limit": N}
    """
    if not player_id and collection in {RUNS_COL, PLAYERS_COL}:
        raise ValueError("player_id is required to query runs or players collection")
    logger.debug(
        f"Listing character hids from collection={collection} with query={query}"
    )
    if not isinstance(query, Mapping):
        raise TypeError("query must be a mapping")

    # Enforce presence of player_id only for scoped collections
    if collection == RUNS_COL and not player_id:
        raise ValueError("player_id is required to query 'runs' collection")

    spec = dict(query)
    where = spec.get("where", spec)

    # if query contains __delta_days-N__, replace with datetime logic
    where = _resolve_magic_tokens(where)

    # Only inject player_id for scoped collections
    if collection == RUNS_COL:
        logger.debug(
            f"Injecting player_id={player_id} into query for collection={collection}"
        )
        pid_clause = {"player_id": ObjectId(player_id)}
        where = {"$and": [where, pid_clause]} if where else pid_clause

    # Optional sort
    projection = {"_id": 0}
    if collection == RUNS_COL:
        projection["npc.hid"] = 1
    else:
        projection["hid"] = 1

    coll: Collection = get_db()[collection]
    logger.debug(f"Final query where={where} projection={projection}")
    cursor = coll.find(where, projection=projection)

    docs = list(cursor)
    logger.debug(f"Found {len(docs)} documents matching.")

    order_by = spec.get("order_by")
    if isinstance(order_by, (list, tuple)) and order_by:
        field = str(order_by[0])
        direction = (
            DESCENDING
            if len(order_by) > 1 and str(order_by[1]).lower().startswith("d")
            else ASCENDING
        )
        docs.sort(key=lambda d: d.get(field), reverse=(direction == DESCENDING))

    # Optional limit
    if spec.get("limit") is not None:
        docs = docs[: int(spec["limit"])]

    # Distinct HIDs
    seen: set[str] = set()
    out: List[str] = []
    for d in docs:
        hid = (d.get("npc") or {}).get("hid") or d.get("hid")
        if hid and hid not in seen:
            seen.add(hid := str(hid))
            out.append(hid)
    return out


def get_character_from_hid(
    hid: str,
    *,
    collection: str = "characters",
) -> Dict[str, Any]:
    """Load a character dict from MongoDB by unique `hid`.

    Args:
        hid: The unique HID to look up.
        collection: Primary MongoDB collection name to query.

    Returns:
        A character dict hydrated from the matching document.

    Raises:
        ValueError: If no document with the given `hid` is found in the collection.
    """
    logger.debug(f"Loading character by hid='{hid}' from collection='{collection}'")

    db = get_db()

    doc: Optional[Dict[str, Any]] = db[collection].find_one(
        {"hid": hid}, projection={"_id": 0}
    )
    if not doc:
        raise ValueError(f"Character with hid='{hid}' not found")

    return doc


def validate_query_against_server(collection: str, query: Dict[str, Any]) -> None:
    """Validate a MongoDB query dict against the server (or mongomock).

    Prefer a parse-only plan via explain(); fall back to a cheap find_one
    to trigger query parsing on engines without explain().
    """
    db = get_db()
    try:
        cursor = db[collection].find(query).limit(0)
        explain = getattr(cursor, "explain", None)

        if callable(explain):
            explain()  # real Mongo / PyMongo supports this
        else:
            # Fallback (mongomock etc.): run a minimal query to force parsing.
            # Returns at most one _id; okay if None.
            db[collection].find_one(query, projection={"_id": 1})

    except Exception as exc:
        # Wrap with your project’s error type if you have one
        raise RuntimeError(
            f"Invalid query for collection '{collection}': {query!r}"
        ) from exc


def user_matches_where(
    *,
    player_id: Optional[Union[str, Any]],
    query: Mapping[str, Any],
    collection: str,
) -> bool:
    """Return True if there exists a document matching the where-clause for this user.

    Rules:
      - players: require player_id; AND with {"_id": ObjectId(player_id)}
      - runs:    require player_id; AND with {"player_id": ObjectId(player_id)}
      - characters: no implicit player filter
    """
    logger.debug(
        "Checking user_matches_where for "
        f"player_id={player_id}, collection={collection}, query={query}"
    )
    if not isinstance(query, Mapping):
        raise TypeError("query must be a mapping")

    spec = dict(query)
    where = spec.get("where", spec)
    where = _resolve_magic_tokens(where)

    coll: Collection = get_db()[collection]

    if collection == PLAYERS_COL:
        if not player_id:
            # Without a concrete player, cannot possibly match a player-scoped rule.
            return False
        pid_clause = {"_id": ObjectId(player_id)}
        where = {"$and": [where, pid_clause]} if where else pid_clause

    elif collection == RUNS_COL:
        if not player_id:
            return False
        pid_clause = {"player_id": ObjectId(player_id)}
        where = {"$and": [where, pid_clause]} if where else pid_clause

    # characters: no automatic player filter

    try:
        logger.debug(f"Final user_matches_where query where={where}")
        doc = coll.find_one(where, projection={"_id": 1})
        return bool(doc)
    except Exception as e:
        logger.error(f"user_matches_where failed: {e}")
        return False
