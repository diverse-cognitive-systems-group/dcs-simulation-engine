"""Root cli app wiring."""

from pathlib import Path
from typing import Optional

import typer

from dcs_simulation_engine.cli.commands.list import list_app
from dcs_simulation_engine.cli.commands.modify import modify_app
from dcs_simulation_engine.cli.commands.run import run
from dcs_simulation_engine.cli.commands.status import status
from dcs_simulation_engine.cli.commands.stop import stop
from dcs_simulation_engine.cli.common import GlobalOptions, version_callback
from dcs_simulation_engine.helpers.logging_helpers import configure_logger

app = typer.Typer(
    add_completion=True,
    help="Command line interface for the DCS Simulation Engine.",
)

# sub-apps
app.add_typer(list_app, name="list")
app.add_typer(modify_app, name="modify")

# top level commands (no subcommand)
app.command("run")(run)
app.command("stop")(stop)
app.command("status")(status)


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
