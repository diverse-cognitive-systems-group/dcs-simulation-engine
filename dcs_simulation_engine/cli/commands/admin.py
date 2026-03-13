"""CLI admin commands for database administration."""

from pathlib import Path

import typer
from dcs_simulation_engine.cli.bootstrap import create_provider_admin
from dcs_simulation_engine.cli.common import echo, seed_database

admin_app = typer.Typer(help="Database administration commands.")


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
