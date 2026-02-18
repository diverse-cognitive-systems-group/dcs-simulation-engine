"""CLI commands for creating resources."""

import json
from pathlib import Path
from typing import List, Optional

import typer

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.cli.common import console, echo
from dcs_simulation_engine.helpers.game_helpers import create_game_from_template
from dcs_simulation_engine.infra.deploy import deploy_app
from dcs_simulation_engine.infra.fly import FlyError
from dcs_simulation_engine.utils.misc import parse_kv

create_app = typer.Typer(help="Create resources.")


@create_app.command("database")
def create_database(
    ctx: typer.Context,
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Optional path to initialize the database at (default: ./database_seeds/dev).",
        dir_okay=True,
        file_okay=False,
        writable=False,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-initialization of the database (overwrite existing data).",
    ),
) -> None:
    """Create the database."""
    res = dbh.init_or_seed_database(seeds_dir=path, force=force)
    if res["seeded"]:
        echo(ctx, "Database initialized and seeded.", style="success")
    else:
        echo(ctx, "Database already exists. No action taken.", style="info")


@create_app.command("game")
def create_game(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None, help="Name of the game. If omitted, you will be prompted."
    ),
) -> None:
    """Create a new game from the default template."""
    if name is None:
        name = typer.prompt("Game name", default="my-game")

    try:
        created_path = create_game_from_template(name)
    except FileExistsError:
        typer.secho(
            f"A game named '{name}' already exists.\nDelete it or"
            " choose a different name.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    echo(
        ctx,
        f"Created new game '{name}' from template. Modify the configuration"
        f" in {created_path} to customize your game.",
        style="success",
    )


@create_app.command("character")
def create_character(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None, help="Character name. If omitted, you will be prompted."
    ),
    fields: List[str] = typer.Argument(
        None, help="Extra character fields as key=value (values may be JSON)."
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a JSON file containing character fields.",
        dir_okay=False,
        file_okay=True,
        exists=True,
        readable=True,
    ),
    character_id: Optional[str] = typer.Option(
        None, "--id", help="Explicit character _id to upsert."
    ),
    no_key: bool = typer.Option(
        False, "--no-key", help="Do not issue a new access key."
    ),
) -> None:
    """Create a character (not implemented)."""
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)


@create_app.command("player")
def create_player(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Player name. If omitted, you will be prompted (unless"
        " name is in --file/fields).",
    ),
    fields: List[str] = typer.Argument(
        None, help="Extra player fields as key=value (values may be JSON)."
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a JSON file containing player fields.",
        dir_okay=False,
        file_okay=True,
        exists=True,
        readable=True,
    ),
    player_id: Optional[str] = typer.Option(
        None, "--id", help="Explicit player _id to upsert."
    ),
    no_key: bool = typer.Option(
        False, "--no-key", help="Do not issue a new access key."
    ),
) -> None:
    """Create a player and print id + access key."""
    data: dict = {}

    if file is not None:
        try:
            parsed = json.loads(file.read_text())
            if not isinstance(parsed, dict):
                raise typer.BadParameter(
                    "--file JSON must be an object at the top level."
                )
            data.update(parsed)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON in --file: {e}") from e

    kv = parse_kv(fields or [])
    if kv:
        data.update(kv)

    resolved_name = data.get("name") or name
    if not resolved_name:
        resolved_name = typer.prompt("Player name")
    data["name"] = resolved_name

    no_structured_input = (file is None) and (not (fields or []))
    if no_structured_input and "email" not in data:
        email = typer.prompt("Email (optional)", default="", show_default=False)
        if email.strip():
            data["email"] = email

    try:
        created_id, raw_key = dbh.create_player(
            data,
            player_id=player_id,
            issue_access_key=not no_key,
        )
    except Exception as e:
        echo(ctx, f"Failed to create player: {e}", style="error")
        raise typer.Exit(code=1)

    console.print(f"id={created_id}")
    console.print(f"access_key={raw_key if raw_key else 'None'}")


@create_app.command("deployment")
def create_deployment(
    ctx: typer.Context,
    game: str = typer.Argument(..., help="Game name to deploy (e.g., my-game)."),
    deployment: Optional[str] = typer.Argument(
        None,
        help="Deployment name (Fly app name). If omitted, you will be prompted.",
    ),
    version: str = typer.Option(
        "latest", "--version", help="Version selector (currently informational)."
    ),
    fly_toml: Path = typer.Option(
        Path("fly.toml"), "--fly-toml", help="Path to fly.toml."
    ),
    env_file: Optional[Path] = typer.Option(
        Path(".env"),
        "--env-file",
        help="Optional .env file to load/forward (excluding FLY_API_TOKEN).",
    ),
    region: Optional[str] = typer.Option(
        None, "--region", help="Override primary_region in fly.toml (optional)."
    ),
) -> None:
    """Create a deployment for a game (Fly.io)."""
    if not deployment:
        deployment = typer.prompt("Deployment name", default=f"{game}")

    try:
        res = deploy_app(
            game=game,
            deployment=deployment,
            fly_toml=fly_toml,
            env_file=env_file,
            region=region,
            version=version,
        )
    except FlyError as e:
        echo(ctx, str(e), style="error")
        raise typer.Exit(code=1)

    echo(ctx, f"Deployment created: {res.app_name}", style="success")
