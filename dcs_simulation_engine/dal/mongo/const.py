"""MongoDB constants: collection names, column names, and index definitions."""

from pathlib import Path
from typing import Any

DEFAULT_DB_NAME: str = "dcs-db"
DEFAULT_SEEDS_DIR = Path("database_seeds/dev")
DEFAULT_MONGO_URI = "mongodb://127.0.0.1:27017/"
INDEX_DEFS: dict[str, list[dict[str, Any]]] = {
    "characters": [{"fields": [("hid", 1)], "unique": True}],
    "experiments": [{"fields": [("name", 1)], "unique": True}],
    "assignments": [{"fields": [("assignment_id", 1)], "unique": True}],
}


class MongoColumns:
    """Namespace for MongoDB collection and field name constants."""

    CHARACTERS = "characters"
    PLAYERS = "players"
    PII = "pii"
    SESSIONS = "sessions"
    SESSION_EVENTS = "session_events"
    EXPERIMENTS = "experiments"
    ASSIGNMENTS = "assignments"
    FORMS = "forms"

    ID = "_id"
    ASSIGNMENT_ID = "assignment_id"
    PLAYER_ID = "player_id"
    SESSION_ID = "session_id"
    EVENT_ID = "event_id"
    GAME_NAME = "game_name"
    EXPERIMENT_NAME = "experiment_name"
    ACTIVE_SESSION_ID = "active_session_id"
    BRANCH_FROM_SESSION_ID = "branch_from_session_id"
    FORM_RESPONSES = "form_responses"
    CONFIG_SNAPSHOT = "config_snapshot"
    PROGRESS = "progress"
    NAME = "name"
    STATUS = "status"
    SOURCE = "source"
    PC_HID = "pc_hid"
    NPC_HID = "npc_hid"
    SESSION_STARTED_AT = "session_started_at"
    SESSION_ENDED_AT = "session_ended_at"
    TERMINATION_REASON = "termination_reason"
    TURNS_COMPLETED = "turns_completed"
    MODEL_PROFILE = "model_profile"
    GAME_CONFIG_SNAPSHOT = "game_config_snapshot"
    LAST_SEQ = "last_seq"
    SEQ = "seq"
    EVENT_TS = "event_ts"
    DIRECTION = "direction"
    EVENT_TYPE = "event_type"
    EVENT_SOURCE = "event_source"
    CONTENT = "content"
    FEEDBACK = "feedback"
    CONTENT_FORMAT = "content_format"
    TURN_INDEX = "turn_index"
    COMMAND_NAME = "command_name"
    COMMAND_ARGS = "command_args"
    VISIBLE_TO_USER = "visible_to_user"
    METADATA = "metadata"
    RUNTIME_STATE = "runtime_state"
    PERSISTED_AT = "persisted_at"
    FIELDS = "fields"
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
