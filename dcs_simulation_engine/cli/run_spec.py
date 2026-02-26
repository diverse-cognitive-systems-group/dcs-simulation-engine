"""Run configuration dataclasses."""

from dataclasses import dataclass, field
from typing import Any

import typer


@dataclass
class RunSpec:
    """Specification for a run."""

    name: str = "default"
    interfaces: list[str] = field(default_factory=lambda: ["gui", "api"])


@dataclass
class GameSpec:
    """Specification for a game to run, including its name and any overrides."""

    name: str
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunConfig:
    """Full configuration for a run, including provider settings and games to run."""

    run: RunSpec = field(default_factory=RunSpec)
    games: list[GameSpec] = field(default_factory=lambda: [GameSpec(name="explore")])


def parse_run_config(data: dict[str, Any]) -> RunConfig:
    """Parse a dict (e.g. from YAML) into a RunConfig, with validation."""
    run_obj = data.get("run", {}) or {}
    if not isinstance(run_obj, dict):
        raise typer.BadParameter("run must be a mapping")

    run_name = str(run_obj.get("name", "default"))

    interfaces_obj = run_obj.get("interfaces", RunSpec().interfaces)
    if isinstance(interfaces_obj, str):
        interfaces = [interfaces_obj]
    elif isinstance(interfaces_obj, list):
        interfaces = [str(x) for x in interfaces_obj]
    else:
        raise typer.BadParameter("run.interfaces must be a string or list of strings")

    interfaces = [i.strip().lower() for i in interfaces if str(i).strip()]
    if not interfaces:
        raise typer.BadParameter("run.interfaces must be non-empty")

    allowed = {"api", "gui"}
    bad = [i for i in interfaces if i not in allowed]
    if bad:
        raise typer.BadParameter(
            f"run.interfaces has invalid values: {bad}. Allowed: {sorted(allowed)}"
        )

    games_obj = data.get("games", None)
    games: list[GameSpec] = []

    if games_obj is None:
        games = [GameSpec(name="explore")]
    else:
        if not isinstance(games_obj, list) or len(games_obj) == 0:
            raise typer.BadParameter("games must be a non-empty list")
        for i, g in enumerate(games_obj):
            if not isinstance(g, dict):
                raise typer.BadParameter(f"games[{i}] must be a mapping")
            if "name" not in g:
                raise typer.BadParameter(f"games[{i}].name is required")
            game_name = str(g["name"])
            overrides = g.get("overrides", {}) or {}
            if not isinstance(overrides, dict):
                raise typer.BadParameter(f"games[{i}].overrides must be a mapping")
            games.append(GameSpec(name=game_name, overrides=overrides))

    return RunConfig(
        run=RunSpec(
            name=run_name,
            interfaces=interfaces,
        ),
        games=games,
    )
