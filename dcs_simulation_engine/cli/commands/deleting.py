"""CLI commands for deleting resources."""

from typing import Optional

import typer

from dcs_simulation_engine.cli.common import echo

delete_app = typer.Typer(help="Delete resources.")


@delete_app.command("character")
def delete_character(
    ctx: typer.Context,
    character: Optional[str] = typer.Argument(
        None,
        help="Character ID (preferred). If omitted, you will be prompted.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Do not prompt for confirmation."
    ),
) -> None:
    """Delete a character (not implemented)."""
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)


@delete_app.command("player")
def delete_player(
    ctx: typer.Context,
    player: Optional[str] = typer.Argument(
        None,
        help="Player ID (preferred). If omitted, you will be prompted.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Do not prompt for confirmation."
    ),
) -> None:
    """Delete a player (not implemented)."""
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)
