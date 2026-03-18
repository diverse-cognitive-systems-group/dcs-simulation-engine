"""Root cli app wiring."""

from pathlib import Path
from typing import Optional

import typer
import typer.rich_utils as ru
from dcs_simulation_engine.cli.commands.admin import admin_app
from dcs_simulation_engine.cli.commands.game import game
from dcs_simulation_engine.cli.commands.list import list_app
from dcs_simulation_engine.cli.commands.modify import modify_app
from dcs_simulation_engine.cli.commands.server import server
from dcs_simulation_engine.cli.common import GlobalOptions
from dcs_simulation_engine.helpers.logging_helpers import configure_logger
from dotenv import load_dotenv

load_dotenv()

# Default style overrides to neutral white/gray colors
ru.STYLE_OPTION = "bold white"
ru.STYLE_SWITCH = "bold white"
ru.STYLE_NEGATIVE_OPTION = "bold white"
ru.STYLE_NEGATIVE_SWITCH = "bold white"
ru.STYLE_METAVAR = "bold white"
ru.STYLE_METAVAR_SEPARATOR = "dim"
ru.STYLE_USAGE = "white"
ru.STYLE_USAGE_COMMAND = "bold"
ru.STYLE_DEPRECATED = "white"
ru.STYLE_DEPRECATED_COMMAND = "dim"
ru.STYLE_HELPTEXT_FIRST_LINE = ""
ru.STYLE_HELPTEXT = "dim"
ru.STYLE_OPTION_HELP = ""
ru.STYLE_OPTION_DEFAULT = "dim"
ru.STYLE_OPTION_ENVVAR = "dim white"
ru.STYLE_REQUIRED_SHORT = "white"
ru.STYLE_REQUIRED_LONG = "dim white"
ru.STYLE_OPTIONS_PANEL_BORDER = "dim"
ru.STYLE_COMMANDS_PANEL_BORDER = "dim"
ru.STYLE_COMMANDS_TABLE_FIRST_COLUMN = "bold white"
ru.STYLE_ERRORS_PANEL_BORDER = "white"
ru.STYLE_ERRORS_SUGGESTION = "dim"
ru.STYLE_ABORTED = "white"

app = typer.Typer(
    rich_markup_mode="rich",
    add_completion=True,
    help="Command line interface for the DCS Simulation Engine.",
)

# sub-apps
app.add_typer(admin_app, name="admin")
app.add_typer(list_app, name="list")
app.add_typer(modify_app, name="modify")

# top level commands (no subcommand)
app.command("game")(game)
app.command("server")(server)


@app.callback(invoke_without_command=False)
def main(
    ctx: typer.Context,
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress non-error output."),
    verbose: int = typer.Option(
        1,
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
    mongo_uri: Optional[str] = typer.Option(
        None,
        "--mongo-uri",
        envvar="MONGO_URI",
        help="MongoDB connection URI. Overrides MONGO_URI environment value.",
    ),
    server_url: str = typer.Option(
        "http://localhost:8000",
        "--server-url",
        envvar="DCS_SERVER_URL",
        help="DCS API server URL.",
    ),
) -> None:
    """Initialize global CLI options and context."""
    ctx.obj = GlobalOptions(quiet=quiet, yes=yes, config=config, mongo_uri=mongo_uri, server_url=server_url)
    configure_logger(source="dcs-cli", quiet=quiet, verbose=verbose)


if __name__ == "__main__":
    app()
