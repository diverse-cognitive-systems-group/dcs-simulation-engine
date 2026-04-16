"""Fingerprinting utilities for character evaluation QC."""

import hashlib
import json
from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games.ai_client import DEFAULT_MODEL
from dcs_simulation_engine.games.prompts import CHARACTER_UPDATER_PROMPTS, SCENE_UPDATER_PROMPTS

DEFAULT_SIMULATOR_PROMPT_BUNDLE: dict[str, str] = {
    "scene_updater_name": "default",
    "scene_updater_template": SCENE_UPDATER_PROMPTS["default"],
    "character_updater_name": "default",
    "character_updater_template": CHARACTER_UPDATER_PROMPTS["default"],
}


def compute_character_evaluation_fingerprint(
    character: CharacterRecord,
    model: str = DEFAULT_MODEL,
    simulator_prompt_bundle: dict[str, Any] | None = None,
) -> str:
    """Return a SHA-256 hex fingerprint of a character + model + simulator prompt bundle.

    Defaults to the current simulator model and default scene/character updater prompt
    bundle, so callers typically only need to pass the character:

        fingerprint = compute_character_evaluation_fingerprint(character)

    The fingerprint is deterministic: same inputs always produce the same value.
    Any change to the character sheet, model name, or selected prompt bundle changes it.
    """
    payload = {
        "character": character._asdict(),
        "model": model,
        "simulator_prompt_bundle": simulator_prompt_bundle or DEFAULT_SIMULATOR_PROMPT_BUNDLE,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
