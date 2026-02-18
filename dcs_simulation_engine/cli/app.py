"""Root cli app wiring."""

from pathlib import Path
from typing import Optional

import typer

from dcs_simulation_engine.cli.commands.creating import create_app
from dcs_simulation_engine.cli.commands.deleting import delete_app
from dcs_simulation_engine.cli.commands.listing import list_app
from dcs_simulation_engine.cli.commands.running import run_app
from dcs_simulation_engine.cli.commands.stopping import stop_app
from dcs_simulation_engine.cli.commands.validating import validate_app
from dcs_simulation_engine.cli.common import GlobalOptions, version_callback
from dcs_simulation_engine.helpers.logging_helpers import configure_logger

app = typer.Typer(
    add_completion=True,
    help="Command line interface for the DCS Simulation Engine.",
)

app.add_typer(list_app, name="list")
app.add_typer(create_app, name="create")
app.add_typer(validate_app, name="validate")
app.add_typer(run_app, name="run")
app.add_typer(delete_app, name="delete")
app.add_typer(stop_app, name="stop")


@app.callback(invoke_without_command=False)
def main(
    ctx: typer.Context,
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress non-error output."
    ),
    verbose: int = typer.Option(
        0,
        "-v",
        "--verbose",
        count=True,
        help="Increase verbosity: -v for INFO, -vv for DEBUG.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help='Assume "yes" for all prompts (non-interactive mode).',
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        help="Optional global config file.",
        exists=False,
        dir_okay=False,
        file_okay=True,
        readable=True,
    ),
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Initialize global CLI options and context."""
    ctx.obj = GlobalOptions(quiet=quiet, yes=yes, config=config)
    configure_logger(source="dcs-cli", quiet=quiet, verbose=verbose)


if __name__ == "__main__":
    app()