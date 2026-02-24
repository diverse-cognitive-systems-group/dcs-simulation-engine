"""CLI commands for listing resources."""

from typing import List, Optional

import typer
from rich.table import Table

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.cli.common import done, echo, select_deployment, step
from dcs_simulation_engine.helpers.game_helpers import list_games as _list_games

list_app = typer.Typer(help="List games or characters available for use.")


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
        chars = dbh.list_characters()
        if len(chars) == 0:
            echo(
                ctx,
                "No characters found. You may need to seed the database first"
                " (dcs create database).",
                style="warning",
            )
    except Exception as e:
        echo(ctx, f"Failed to list characters: {e}", style="error")
        raise typer.Exit(code=1)

    table = Table(title="Characters", show_header=True, header_style="bold magenta")
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


def _render_id_table(ctx: typer.Context, title: str, ids: List[str]) -> None:
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right")
    table.add_column("ID")

    if not ids:
        table.add_row("—", f"No {title.lower()} found")
        echo(ctx, table)
        return

    for idx, _id in enumerate(ids, start=1):
        table.add_row(str(idx), _id)

    echo(ctx, table)


@list_app.command("players")
def list_players(
    ctx: typer.Context,
    deployment: Optional[str] = typer.Argument(None, help="Deployment name."),
) -> None:
    """List players in a live database."""
    app, local_is_running = select_deployment(ctx, deployment, include_local=True)

    if app in ("local", "localhost"):
        if not local_is_running:
            echo(
                ctx,
                "Localhost is not live. Start the local server first.",
                style="error",
            )
            raise typer.Exit(code=1)

        step("Listing players from local database...")
        try:
            chars = dbh.list_players() or []
        except Exception as e:
            echo(ctx, f"Failed to list players from local database: {e}", style="error")
            raise typer.Exit(code=1)
        done()

        if len(chars) == 0:
            echo(
                ctx,
                "No players found in local database. You may need to seed the database first (dcs create database).",
                style="warning",
            )

        ids = [str(c.get("id") or "—") for c in chars]
        _render_id_table(ctx, "Players", ids)
        return

    echo(ctx, "TODO: implement listing players from fly deployment.", style="warning")
    raise typer.Exit(code=2)


@list_app.command("runs")
def list_runs(
    ctx: typer.Context,
    deployment: Optional[str] = typer.Argument(None, help="Deployment name."),
) -> None:
    """List runs in a live database."""
    app, local_is_running = select_deployment(ctx, deployment, include_local=True)

    if app in ("local", "localhost"):
        if not local_is_running:
            echo(
                ctx,
                "Localhost is not live. Start the local server first.",
                style="error",
            )
            raise typer.Exit(code=1)

        step("Listing runs from local database...")
        try:
            runs = dbh.list_runs() or []
        except Exception as e:
            echo(ctx, f"Failed to list runs from local database: {e}", style="error")
            raise typer.Exit(code=1)
        done()

        if len(runs) == 0:
            echo(
                ctx,
                "No runs found in local database. You may need to seed the database first (dcs create database).",
                style="warning",
            )
        ids = [str(r.get("id") or "—") for r in runs]
        _render_id_table(ctx, "Runs", ids)
        return

    echo(ctx, "TODO: implement listing runs from fly deployment.", style="warning")
    raise typer.Exit(code=2)
