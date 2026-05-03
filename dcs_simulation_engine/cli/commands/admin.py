"""CLI admin commands for database administration."""

from pathlib import Path

import typer
from dcs_simulation_engine.cli.bootstrap import create_provider_admin
from dcs_simulation_engine.cli.commands.workflow import admin_publish_app, hitl_app
from dcs_simulation_engine.cli.common import echo, seed_database
from dcs_simulation_engine.utils.auth import generate_access_key

admin_app = typer.Typer(help="Database administration commands.")
admin_app.add_typer(hitl_app, name="hitl")
admin_app.add_typer(admin_publish_app, name="publish")


@admin_app.command("seed")
def seed(
    ctx: typer.Context,
    seeds_dir: Path = typer.Argument(
        help="Directory of JSON/NDJSON seed files. Defaults to database_seeds/dev.",
    ),
) -> None:
    """Seed the database from JSON files."""
    seed_database(ctx, seeds_dir)


@admin_app.command("backup")
def backup(
    ctx: typer.Context,
    outdir: Path = typer.Argument(
        help="Directory to write the backup to. A timestamped subdirectory is created inside.",
    ),
) -> None:
    """Backup the entire database to a directory."""
    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)
    try:
        admin = create_provider_admin(mongo_uri=mongo_uri)
        result = admin.backup_db(outdir)
    except Exception as e:
        echo(ctx, str(e), style="error")
        raise typer.Exit(code=1)
    echo(ctx, f"Backup written to: {result}")


@admin_app.command("keygen")
def keygen(ctx: typer.Context) -> None:
    """Generate a deployment-ready admin key without storing it anywhere."""
    key = generate_access_key()
    echo(ctx, key, style="success")
    echo(ctx, "This key has not been added to any app or database.", style="error")
    echo(ctx, "It is intended to be supplied during deployment, for example via `dcs remote deploy --admin-key`.")
