"""Fingerprinting utilities for character evaluation QC."""

import hashlib
import json

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import DEFAULT_MODEL
from dcs_simulation_engine.games.prompts import UPDATER_SYSTEM_TEMPLATE


def compute_character_evaluation_fingerprint(
    character: CharacterRecord,
    model: str = DEFAULT_MODEL,
    updater_system_prompt_template: str = UPDATER_SYSTEM_TEMPLATE,
) -> str:
    """Return a SHA-256 hex fingerprint of a character + model + prompt template.

    Defaults to the current UpdaterClient model and updater system prompt template,
    so callers typically only need to pass the character:

        fingerprint = compute_character_evaluation_fingerprint(character)

    The fingerprint is deterministic: same inputs always produce the same value.
    Any change to the character sheet, model name, or updater template changes it.
    """
    payload = {
        "character": character._asdict(),
        "model": model,
        "updater_system_prompt_template": updater_system_prompt_template,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
