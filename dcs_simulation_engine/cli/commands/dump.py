"""CLI command for dumping Mongo collections to JSON files."""

from pathlib import Path

import typer
from dcs_simulation_engine.cli.bootstrap import create_sync_db
from dcs_simulation_engine.cli.common import echo
from dcs_simulation_engine.dal.mongo.util import dump_all_collections_to_json


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
