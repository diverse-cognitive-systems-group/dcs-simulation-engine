"""CLI commands for listing resources."""

import typer
from rich.table import Table

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.cli.common import echo
from dcs_simulation_engine.helpers.game_helpers import list_games as _list_games
from dcs_simulation_engine.infra import deploy
from dcs_simulation_engine.infra.fly import FlyError

list_app = typer.Typer(help="List resources.")


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


@list_app.command("players")
def list_players(ctx: typer.Context) -> None:
    """List players."""
    try:
        players = dbh.list_players()
    except AttributeError:
        echo(ctx, "TODO: implement dbh.list_players().", style="warning")
        raise typer.Exit(code=2)
    except Exception as e:
        echo(ctx, f"Failed to list players: {e}", style="error")
        raise typer.Exit(code=1)

    table = Table(title="Players", show_header=True, header_style="bold magenta")
    table.add_column("ID")
    table.add_column("Name")

    rows = 0
    for p in players or []:
        pid = str(p.get("_id") or p.get("id") or "—")
        name = str(p.get("name") or "—")
        table.add_row(pid, name)
        rows += 1

    if rows == 0:
        table.add_row("—", "No players found")

    echo(ctx, table)


@list_app.command("deployments")
def list_deployments(ctx: typer.Context) -> None:
    """List deployments (Fly apps)."""
    try:
        apps = deploy.list_deployments()
    except FlyError as e:
        # Keep it simple + actionable. FlyError already wraps the underlying issue.
        msg = str(e)
        if "flyctl not found" in msg.lower() or "not found on path" in msg.lower():
            echo(
                ctx,
                "flyctl not found. Install Fly CLI to list deployments.",
                style="error",
            )
            raise typer.Exit(code=1)
        echo(ctx, f"Failed to list deployments: {e}", style="error")
        raise typer.Exit(code=1)

    table = Table(title="Deployments", show_header=True, header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Organization")
    table.add_column("Status")

    if apps:
        for a in apps:
            name = str(a.get("Name") or a.get("name") or "—")
            org = str(a.get("Organization") or a.get("organization") or "—")
            status = str(a.get("Status") or a.get("status") or "—")
            table.add_row(name, org, status)
    else:
        table.add_row("—", "—", "No deployments found")

    echo(ctx, table)
