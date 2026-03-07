"""CLI commands for modifying resources."""

import json
import shutil
from pathlib import Path
from typing import List, Optional

import typer

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.cli.common import console, echo
from dcs_simulation_engine.errors import DCSError
from dcs_simulation_engine.helpers.game_helpers import (
    create_game_from_template,
    validate_game_compiles,
)
from dcs_simulation_engine.utils.misc import parse_kv

modify_app = typer.Typer(help="Modify games or characters available for use.")


def _validate_game(ctx: typer.Context, name: str) -> None:
    echo(ctx, f"Validating game configuration [bold]{name}[/bold]...", style="info")

    try:
        path = validate_game_compiles(name)
    except DCSError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.secho(
        "Warning: This validation only checks configuration and graph compilation. "
        "It does not test gameplay behavior, branching logic, or node execution.",
        fg=typer.colors.YELLOW,
    )

    echo(
        ctx,
        f"Game configuration [bold]{name}[/bold] is valid.\nConfig path: {path}",
        style="success",
    )


def _validate_character(ctx: typer.Context, character_id: str) -> None:
    echo(ctx, f"Validating character [bold]{character_id}[/bold]...", style="info")
    echo(ctx, "Character validation not implemented.", style="warning")


def _validate_player(ctx: typer.Context, player_id: str) -> None:
    echo(ctx, f"Validating player [bold]{player_id}[/bold]...", style="info")
    echo(ctx, "Player validation not implemented.", style="warning")


@modify_app.command("game")
def modify_game(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None, help="Name of the game. If omitted, you will be prompted."
    ),
    delete: bool = typer.Option(False, "--delete", help="Delete the game directory."),
) -> None:
    """Create or delete a game."""
    if name is None:
        name = typer.prompt("Game name", default="my-game")

    game_path = Path(name)

    if delete:
        if not game_path.exists():
            echo(ctx, f"Game '{name}' does not exist at {game_path}.", style="error")
            raise typer.Exit(code=1)
        try:
            shutil.rmtree(game_path)
        except Exception as e:
            echo(ctx, f"Failed to delete game '{name}': {e}", style="error")
            raise typer.Exit(code=1)

        echo(ctx, f"Deleted game '{name}' at {game_path}.", style="success")
        return

    try:
        created_path = create_game_from_template(name)
    except FileExistsError:
        typer.secho(
            f"A game named '{name}' already exists.\nDelete it or choose a different name.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    # VALIDATION
    _validate_game(ctx, name)

    echo(
        ctx,
        f"Modified game '{name}'. Config path: {created_path}",
        style="success",
    )


@modify_app.command("character")
def modify_character(
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
    delete: bool = typer.Option(
        False, "--delete", help="Delete the character by --id."
    ),
) -> None:
    """Create/update (upsert) or delete a character."""
    if delete:
        if not character_id:
            raise typer.BadParameter("--id is required with --delete.")
        delete_fn = getattr(dbh, "delete_character", None)
        if not callable(delete_fn):
            echo(ctx, "Character delete not supported.", style="error")
            raise typer.Exit(code=2)
        try:
            delete_fn(character_id)
        except Exception as e:
            echo(ctx, f"Failed to delete character: {e}", style="error")
            raise typer.Exit(code=1)
        echo(ctx, f"Deleted character id={character_id}", style="success")
        return

    data: dict = {}

    if file is not None:
        try:
            parsed = json.loads(file.read_text())
            if not isinstance(parsed, dict):
                raise typer.BadParameter("--file JSON must be an object.")
            data.update(parsed)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON in --file: {e}") from e

    kv = parse_kv(fields or [])
    if kv:
        data.update(kv)

    resolved_name = data.get("name") or name
    if not resolved_name:
        resolved_name = typer.prompt("Character name")
    data["name"] = resolved_name

    upsert_fn = getattr(dbh, "create_character", None) or getattr(
        dbh, "upsert_character", None
    )
    if not callable(upsert_fn):
        echo(ctx, "Character modify not implemented.", style="error")
        raise typer.Exit(code=2)

    try:
        created_id = upsert_fn(data, character_id=character_id)
    except TypeError:
        created_id = upsert_fn(data)
    except Exception as e:
        echo(ctx, f"Failed to modify character: {e}", style="error")
        raise typer.Exit(code=1)

    _validate_character(ctx, str(created_id))

    console.print(f"id={created_id}")


@modify_app.command("player")
def modify_player(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Player name.",
    ),
    fields: List[str] = typer.Argument(None, help="Extra player fields as key=value."),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a JSON file.",
        exists=True,
        readable=True,
    ),
    player_id: Optional[str] = typer.Option(
        None, "--id", help="Explicit player _id to upsert."
    ),
    no_key: bool = typer.Option(
        False, "--no-key", help="Do not issue a new access key."
    ),
    delete: bool = typer.Option(False, "--delete", help="Delete the player by --id."),
) -> None:
    """Create/update (upsert) or delete a player."""
    if delete:
        if not player_id:
            raise typer.BadParameter("--id is required with --delete.")
        delete_fn = getattr(dbh, "delete_player", None)
        if not callable(delete_fn):
            echo(ctx, "Player delete not supported.", style="error")
            raise typer.Exit(code=2)
        try:
            delete_fn(player_id)
        except Exception as e:
            echo(ctx, f"Failed to delete player: {e}", style="error")
            raise typer.Exit(code=1)
        echo(ctx, f"Deleted player id={player_id}", style="success")
        return

    data: dict = {}

    if file is not None:
        parsed = json.loads(file.read_text())
        data.update(parsed)

    kv = parse_kv(fields or [])
    if kv:
        data.update(kv)

    resolved_name = data.get("name") or name
    if not resolved_name:
        resolved_name = typer.prompt("Player name")
    data["name"] = resolved_name

    try:
        created_id, raw_key = dbh.create_player(
            data,
            player_id=player_id,
            issue_access_key=not no_key,
        )
    except Exception as e:
        echo(ctx, f"Failed to modify player: {e}", style="error")
        raise typer.Exit(code=1)

    _validate_player(ctx, str(created_id))

    console.print(f"id={created_id}")
    console.print(f"access_key={raw_key if raw_key else 'None'}")
