"""CLI commands for listing resources."""

import typer
from rich.table import Table

from dcs_simulation_engine.cli.common import echo
from dcs_simulation_engine.helpers.game_helpers import (
    list_characters as _list_characters,
    list_games as _list_games,
)

list_app = typer.Typer(help="List available games and characters.")


@list_app.command("games")
def list_games(ctx: typer.Context) -> None:
    """List available games."""
    table = Table(
        title="Available Games",
        show_header=True,
        show_lines=True,
    )
    table.add_column("Name")
    table.add_column("Author(s)")
    table.add_column("Description")

    for name, author, _, _, description in _list_games():
        table.add_row(name, author, description or "—")

    echo(ctx, table)


@list_app.command("characters")
def list_characters(ctx: typer.Context) -> None:
    """List available characters."""
    try:
        chars = _list_characters()
        if len(chars) == 0:
            echo(
                ctx,
                "No characters found. (dcs create database).",
                style="warning",
            )
    except Exception as e:
        echo(ctx, f"Failed to list characters: {e}", style="error")
        raise typer.Exit(code=1)

    table = Table(
        title="Available Characters",
        show_header=True,
        header_style="bold white",
        show_lines=True,
    )
    table.add_column("#", justify="right")
    table.add_column("HID")
    table.add_column("Short Description")

    rows = 0
    for idx, c in enumerate(chars or [], start=1):
        cid = str(c.get("hid") or "—")
        name = str(c.get("short_description") or "—")
        table.add_row(str(idx), cid, name)
        rows += 1

    if rows == 0:
        table.add_row("—", "—", "No characters found")

    echo(ctx, table)
