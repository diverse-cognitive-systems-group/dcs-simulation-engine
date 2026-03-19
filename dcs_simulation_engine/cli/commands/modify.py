"""CLI commands for modifying resources."""

import asyncio
import json
from pathlib import Path
from typing import List, Optional

import typer
from dcs_simulation_engine.cli.bootstrap import (
    create_async_provider,
)
from dcs_simulation_engine.cli.common import console, echo
from dcs_simulation_engine.utils.misc import parse_kv

modify_app = typer.Typer(help="Modify characters or players available for use.")


def _run_async(coro):
    """Execute an async coroutine from sync CLI command handlers."""
    return asyncio.run(coro)


@modify_app.command("character")
def modify_character(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(None, help="Character name. If omitted, you will be prompted."),
    fields: List[str] = typer.Argument(None, help="Extra character fields as key=value (values may be JSON)."),
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
    character_id: Optional[str] = typer.Option(None, "--id", help="Explicit character _id to upsert."),
    delete: bool = typer.Option(False, "--delete", help="Delete the character by --id."),
) -> None:
    """Create/update (upsert) or delete a character."""
    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)
    provider = _run_async(create_async_provider(mongo_uri=mongo_uri))

    if delete:
        if not character_id:
            raise typer.BadParameter("--id is required with --delete.")
        try:
            _run_async(provider.delete_character(character_id))
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

    try:
        created_id = _run_async(provider.upsert_character(data, character_id=character_id))
    except Exception as e:
        echo(ctx, f"Failed to modify character: {e}", style="error")
        raise typer.Exit(code=1)

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
    player_id: Optional[str] = typer.Option(None, "--id", help="Explicit player _id to upsert."),
    no_key: bool = typer.Option(False, "--no-key", help="Do not issue a new access key."),
    delete: bool = typer.Option(False, "--delete", help="Delete the player by --id."),
) -> None:
    """Create/update (upsert) or delete a player."""
    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)
    provider = _run_async(create_async_provider(mongo_uri=mongo_uri))

    if delete:
        if not player_id:
            raise typer.BadParameter("--id is required with --delete.")
        try:
            _run_async(provider.delete_player(player_id))
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
        player_record, raw_key = _run_async(
            provider.create_player(
                player_data=data,
                player_id=player_id,
                issue_access_key=not no_key,
            )
        )
        created_id = player_record.id
    except Exception as e:
        echo(ctx, f"Failed to modify player: {e}", style="error")
        raise typer.Exit(code=1)

    console.print(f"id={created_id}")
    console.print(f"access_key={raw_key if raw_key else 'None'}")
