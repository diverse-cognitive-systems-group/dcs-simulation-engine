"""MongoDB constants: collection names, column names, and index definitions."""

from pathlib import Path
from typing import Any

DEFAULT_DB_NAME: str = "dcs-db"
DEFAULT_SEEDS_DIR = Path("database_seeds/dev")
DEFAULT_MONGO_URI = "mongodb://127.0.0.1:27017/"
INDEX_DEFS: dict[str, list[dict[str, Any]]] = {
    "characters": [{"fields": [("hid", 1)], "unique": True}],
}


class MongoColumns:
    """Namespace for MongoDB collection and field name constants."""

    CHARACTERS = "characters"
    PLAYERS = "players"
    RUNS = "runs"
    PII = "pii"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"

    PII_KEYS = {
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
        "access_key_revoked",
        "created_at",
        "last_key_issued_at",
    }
