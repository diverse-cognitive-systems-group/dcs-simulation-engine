"""CLI commands for validating resources."""

from typing import Optional

import typer

from dcs_simulation_engine.cli.common import echo
from dcs_simulation_engine.errors import DCSError
from dcs_simulation_engine.helpers.game_helpers import validate_game_compiles

validate_app = typer.Typer(help="Validate resources.")


@validate_app.command("game")
def validate_game(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Game name to validate."),
) -> None:
    """Validate a game configuration without running it."""
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


@validate_app.command("character")
def validate_character(
    ctx: typer.Context,
    character: Optional[str] = typer.Argument(
        None,
        help="Character ID (preferred). If omitted, you will be prompted.",
    ),
) -> None:
    """Validate a character (not implemented)."""
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)
