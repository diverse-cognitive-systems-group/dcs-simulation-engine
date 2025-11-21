"""Graph context schema definition."""

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from loguru import logger
from typing_extensions import TypedDict

from dcs_simulation_engine.helpers import database_helpers as dbh


class ContextSchema(TypedDict, total=True):
    """Static context for simulation graph."""

    pc: dict[str, Any]
    npc: dict[str, Any]
    # retry_limits: dict[str, int]
    models: dict[str, BaseChatModel]
    additional_validator_rules: str | None
    additional_updater_rules: str | None


def make_context() -> ContextSchema:
    """Create a ContextSchema with provided overrides."""
    logger.debug("Creating default context with temp characters.")
    character = None
    character = dbh.get_character_from_hid("human-normative")
    if character is None:
        raise ValueError("Failed to load default character 'human-normative'")
    # update hid to temp value to avoid confusion
    character["hid"] = "temp-character-for-validation"
    context: ContextSchema = {
        "pc": character,
        "npc": character,
        "models": {},
    }
    return context
