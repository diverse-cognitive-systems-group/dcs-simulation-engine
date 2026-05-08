"""CLI database administration commands."""

from pathlib import Path

import typer
from dcs_simulation_engine.cli.bootstrap import create_provider_admin, create_sync_db
from dcs_simulation_engine.cli.common import echo, seed_database
from dcs_simulation_engine.dal.mongo.util import dump_all_collections_to_json
from dcs_simulation_engine.utils.auth import generate_access_key

database_app = typer.Typer(help="Manage database and database operations.")


@database_app.command("seed")
def seed(
    ctx: typer.Context,
    seeds_dir: Path = typer.Argument(
        help="Directory of JSON/NDJSON seed files. Defaults to database_seeds/dev.",
    ),
) -> None:
    """Seed the database from JSON files."""
    seed_database(ctx, seeds_dir)


@database_app.command("backup")
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


@database_app.command("dump")
def dump(
    ctx: typer.Context,
    outdir: Path = typer.Argument(
        ...,
        help="Directory to write the dump to. A timestamped subdirectory is created inside.",
        file_okay=False,
        dir_okay=True,
        writable=True,
        readable=True,
        resolve_path=False,
    ),
) -> None:
    """Dump all Mongo collections to JSON files."""
    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)
    try:
        db = create_sync_db(mongo_uri=mongo_uri)
        result = dump_all_collections_to_json(db, outdir)
    except Exception as e:
        echo(ctx, f"Failed to dump database: {e}", style="error")
        raise typer.Exit(code=1)

    echo(ctx, f"Dump written to: {result}", style="success")


@database_app.command("keygen")
def keygen(ctx: typer.Context) -> None:
    """Generate a deployment-ready admin key without storing it anywhere."""
    key = generate_access_key()
    echo(ctx, key, style="success")
    echo(ctx, "This key has not been added to any app or database.", style="error")
    echo(ctx, "It is intended to be supplied during deployment, for example via `dcs remote deploy --admin-key`.")
