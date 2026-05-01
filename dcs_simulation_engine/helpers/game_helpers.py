"""Helpers for games."""

import os
from pathlib import Path

from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.utils.paths import (
    package_root,
)
from loguru import logger

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def create_game_from_template(name: str, template: str | Path | None = None) -> Path:
    """Copy a game into ./games from a template game file."""
    games_dir = Path.cwd() / "games"
    games_dir.mkdir(parents=True, exist_ok=True)

    dest = games_dir / f"{name}.yaml"

    if dest.exists():
        raise FileExistsError(f"{dest} already exists.")

    if template is None:
        template_path = Path(get_game_config("Explore"))
    else:
        t = Path(template).expanduser()
        template_path = t if t.is_file() else Path(get_game_config(str(template)))

    dest.write_text(
        template_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    logger.info("Copied game template %s -> %s", template_path, dest)
    return dest


def list_games(
    directory: str | Path | None = None,
) -> list[tuple[str, str, Path, str | None, str | None]]:
    """Return available games."""
    _ = directory
    results: list[tuple[str, str, Path, str | None, str | None]] = []
    for game_cls in SessionManager._builtin_game_classes().values():
        config = GameConfig.from_game_class(game_cls)
        author_str = ", ".join(config.authors or [])
        path = Path(f"<builtin:{config.name}>")
        results.append((config.name, author_str, path, config.version, config.description))
    return results


def list_characters() -> list[dict]:
    """Return available characters from seed data.

    Useful for checking available characters when db is not live.
    """
    import json

    pkg_root = package_root()
    subfolder = "prod" if IS_PROD else "dev"
    seeds_path = pkg_root.parent / "database_seeds" / subfolder / "characters.json"

    if not seeds_path.exists():
        raise FileNotFoundError(f"Character seed file not found: {seeds_path}")

    data = json.loads(seeds_path.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise ValueError("characters.json must contain a list of character objects")

    return [c for c in data if isinstance(c, dict)]


def get_game_config(game: str, version: str = "latest") -> str:
    """Return a YAML path for explicit custom configs; built-ins are class-backed."""
    _ = version
    possible_path = Path(game).expanduser()
    if possible_path.is_file() and possible_path.suffix.lower() in {".yaml", ".yml"}:
        return str(possible_path)
    config = SessionManager.get_game_config_cached(game)
    raise FileNotFoundError(f"{config.name!r} is a built-in class-backed game and no YAML config path exists.")
