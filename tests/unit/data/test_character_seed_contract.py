"""Contract checks for character seed data used by gameplay."""

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
CHARACTER_SEED_PATHS = (
    REPO_ROOT / "database_seeds" / "dev" / "characters.json",
    REPO_ROOT / "database_seeds" / "prod" / "characters.json",
)
CHARACTER_DIMENSIONS_PATH = REPO_ROOT / "database_seeds" / "dev" / "character_dimensions.json"

REQUIRED_CHARACTER_FIELDS = {
    "hid",
    "short_description",
    "long_description",
    "abilities",
    "goals",
    "common_labels",
    "authors",
    "dimensions",
    "hsn_divergence",
    "is_human",
    "pc_eligible",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_string_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_is_non_empty_string(item) for item in value)


def _character_label(character: Any, index: int) -> str:
    if isinstance(character, dict) and _is_non_empty_string(character.get("hid")):
        return str(character["hid"])
    return f"index {index}"


def _dimension_keys() -> set[str]:
    dimensions_data = _load_json(CHARACTER_DIMENSIONS_PATH)
    dimensions = dimensions_data[0]["dimensions"]
    return {key for key in dimensions if key != "description"}


def _validate_character(path: Path, character: Any, index: int, dimension_keys: set[str]) -> list[str]:
    label = _character_label(character, index)
    prefix = f"{path.relative_to(REPO_ROOT)} character {label}"
    failures: list[str] = []

    if not isinstance(character, dict):
        return [f"{prefix}: must be a JSON object"]

    missing_fields = sorted(REQUIRED_CHARACTER_FIELDS - set(character))
    if missing_fields:
        failures.append(f"{prefix}: missing required fields {missing_fields}")

    for field in ("hid", "short_description", "long_description"):
        if field in character and not _is_non_empty_string(character[field]):
            failures.append(f"{prefix}: {field} must be a non-empty string")

    for field in ("abilities", "goals", "common_labels", "authors"):
        if field in character and not _is_non_empty_string_list(character[field]):
            failures.append(f"{prefix}: {field} must be a non-empty list of non-empty strings")

    for field in ("is_human", "pc_eligible"):
        if field in character and not isinstance(character[field], bool):
            failures.append(f"{prefix}: {field} must be a boolean")

    is_human = character.get("is_human")
    dimensions = character.get("dimensions")
    hsn_divergence = character.get("hsn_divergence")

    if is_human is True:
        if not isinstance(hsn_divergence, dict) or not hsn_divergence:
            failures.append(f"{prefix}: human characters must have non-empty hsn_divergence")
        if dimensions is not None:
            failures.append(f"{prefix}: human characters should use dimensions=null")

    if is_human is False:
        if hsn_divergence is not None:
            failures.append(f"{prefix}: non-human characters should use hsn_divergence=null")
        failures.extend(_validate_dimensions(prefix, dimensions, dimension_keys))

    return failures


def _validate_dimensions(prefix: str, dimensions: Any, dimension_keys: set[str]) -> list[str]:
    if not isinstance(dimensions, dict) or not dimensions:
        return [f"{prefix}: non-human characters must have non-empty dimensions"]

    failures: list[str] = []
    missing_dimensions = sorted(dimension_keys - set(dimensions))
    if missing_dimensions:
        failures.append(f"{prefix}: dimensions missing required keys {missing_dimensions}")

    for dimension_name in sorted(set(dimensions) & dimension_keys):
        dimension = dimensions[dimension_name]
        if not isinstance(dimension, dict):
            failures.append(f"{prefix}: dimensions.{dimension_name} must be an object")
            continue
        if not _is_non_empty_string_list(dimension.get("value")):
            failures.append(f"{prefix}: dimensions.{dimension_name}.value must be a non-empty list of non-empty strings")
        if not _is_non_empty_string(dimension.get("explanation")):
            failures.append(f"{prefix}: dimensions.{dimension_name}.explanation must be a non-empty string")

    return failures


def test_character_seed_files_satisfy_gameplay_contract() -> None:
    """Characters should provide the fields prompts, commands, and validators rely on."""
    dimension_keys = _dimension_keys()
    failures: list[str] = []

    for path in CHARACTER_SEED_PATHS:
        characters = _load_json(path)
        if not isinstance(characters, list) or not characters:
            failures.append(f"{path.relative_to(REPO_ROOT)} must contain a non-empty list of character objects")
            continue

        hids = [character.get("hid") for character in characters if isinstance(character, dict)]
        duplicate_hids = sorted({hid for hid in hids if _is_non_empty_string(hid) and hids.count(hid) > 1})
        if duplicate_hids:
            failures.append(f"{path.relative_to(REPO_ROOT)} has duplicate hid values {duplicate_hids}")

        for index, character in enumerate(characters):
            failures.extend(_validate_character(path, character, index, dimension_keys))

    if failures:
        pytest.fail("\n".join(failures))
