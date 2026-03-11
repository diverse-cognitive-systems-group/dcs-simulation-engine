"""CLI commands for listing resources."""

import typer
from dcs_simulation_engine.cli.common import echo, get_client
from dcs_simulation_engine.errors import APIRequestError
from rich.table import Table

list_app = typer.Typer(help="List available games and characters.")


@list_app.command("games")
def list_games(ctx: typer.Context) -> None:
    """List available games."""
    try:
        with get_client(ctx) as client:
            response = client.list_games()
    except APIRequestError as e:
        echo(ctx, f"Failed to list games: {e}", style="error")
        raise typer.Exit(code=1)

    table = Table(title="Available Games", show_header=True, show_lines=True)
    table.add_column("Name")
    table.add_column("Author(s)")
    table.add_column("Description")

    for game in response.games:
        table.add_row(game.name, game.author, game.description or "—")

    echo(ctx, table)


@list_app.command("characters")
def list_characters(ctx: typer.Context) -> None:
    """List available characters."""
    try:
        with get_client(ctx) as client:
            response = client.list_characters()
    except APIRequestError as e:
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

    if not response.characters:
        table.add_row("—", "—", "No characters found")
    else:
        for idx, c in enumerate(response.characters, start=1):
            table.add_row(str(idx), c.hid, c.short_description)

    echo(ctx, table)
