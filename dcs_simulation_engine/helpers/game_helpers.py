"""Helpers for games."""

from pathlib import Path

import yaml
from loguru import logger
from packaging.version import InvalidVersion, Version  # type: ignore[import-untyped]


def get_game_config(game: str, version: str = "latest") -> str:
    """Return the path to a YAML game config.

    Accepts either:
      - A game name (matched against built-in configs in games/)
      - A filesystem path to a custom YAML config

    The optional `version` argument controls which config is selected when
    multiple configs share the same `name` field:

      - "latest" (default): pick the latest stable release by the `version`
        field in the YAML (using PEP 440 / semantic version ordering and
        preferring non-prerelease, non-dev versions).
      - Any other string: pick the config whose `version` field exactly
        matches that string.

    If `version` is not "latest" and no matching version is found, a
    FileNotFoundError is raised listing available versions.
    """
    # First: treat `game` as a path
    possible_path = Path(game).expanduser()
    if possible_path.is_file() and possible_path.suffix.lower() in {".yml", ".yaml"}:
        return str(possible_path)

    # Otherwise: treat it as a built-in game name
    games_dir = Path(__file__).parent.parent.parent / "games"

    names_found = []
    matches = []  # List[tuple[Path, dict]]

    for path in games_dir.glob("*.y*ml"):
        try:
            with path.open("r", encoding="utf-8") as f:
                doc = yaml.safe_load(f) or {}
            doc_name = doc.get("name")

            if not doc_name:
                logger.warning(
                    f"Game config {path} has no top-level 'name' field. Skipping."
                )
                continue

            names_found.append(doc_name)

            if doc_name.strip().lower() == game.strip().lower():
                matches.append((path, doc))

        except Exception:
            logger.warning(
                f"Failed to load game config from {path}. Maybe syntax error? Skipping."
            )
            continue

    if not matches:
        raise FileNotFoundError(
            f"No game config matching {game!r} found. Found built-ins: {names_found}"
        )

    # If a specific version was requested, honor it exactly.
    if version != "latest":
        matching_versions = [
            p for p, doc in matches if str(doc.get("version", "")).strip() == version
        ]
        if matching_versions:
            chosen = str(matching_versions[0])
            logger.debug(
                f"Selected game config {chosen} for game={game!r}, version={version!r}"
            )
            return chosen

        available_versions = sorted(
            {str(doc.get("version", "")).strip() or "<none>" for _, doc in matches}
        )
        raise FileNotFoundError(
            f"No game config for {game!r} with version {version!r} found. "
            f"Available versions for this game: {available_versions}"
        )

    # version == "latest": pick the latest stable release.
    stable_candidates = []  # list[(Version, Path)]
    other_candidates = []  # list[(Version | None, Path)]

    for path, doc in matches:
        raw_version = str(doc.get("version", "")).strip()
        if not raw_version:
            other_candidates.append((None, path))
            continue

        try:
            v = Version(raw_version)
        except InvalidVersion:
            logger.warning(
                f"Game config {path} has invalid version {raw_version!r}. "
                "Treating as unversioned."
            )
            other_candidates.append((None, path))
            continue

        if not v.is_prerelease and not v.is_devrelease:
            stable_candidates.append((v, path))
        else:
            other_candidates.append((v, path))

    if stable_candidates:
        v, chosen_path = max(stable_candidates, key=lambda x: x[0])
        chosen = str(chosen_path)
        logger.debug(
            f"Selected latest stable game config {chosen} "
            f"for game={game!r}, version={v}"
        )
        return chosen

    # No stable versions; fall back to highest version among others, if any.
    versioned_others = [(v, p) for v, p in other_candidates if v is not None]
    if versioned_others:
        v, chosen_path = max(versioned_others, key=lambda x: x[0])
        chosen = str(chosen_path)
        logger.debug(
            f"No stable versions for {game!r}. "
            f"Selected latest non-stable game config {chosen} with version={v}."
        )
        return chosen

    # No parseable versions at all: fall back to latest by modification time.
    if other_candidates:
        chosen_path = max(
            (p for _, p in other_candidates), key=lambda p: p.stat().st_mtime
        )
        chosen = str(chosen_path)
        logger.debug(
            f"No version info for {game!r}. "
            f"Selected most recently modified game config {chosen}."
        )
        return chosen

    # This should be unreachable, but keep a defensive error.
    raise FileNotFoundError(f"Could not determine a suitable config for game {game!r}.")
