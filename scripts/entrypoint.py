"""DCS CLI Entrypoint.

Usage:
    dcs [global options] <command> [command options]

Global Options:
    -h, --help          Show help for dcs or a specific command
    -v, --version       Show version
    -q, --quiet         Suppress non-error output
    -y, --yes           Assume "yes" for all prompts (non-interactive mode)
    --config <path>     Optional global config file

Commands
--------

create game
    Create a new game.yml file. Runs an interactive wizard unless flags fully specify values.

    Usage:
        dcs create game [name] [options]

    Options:
        --template <name|path>   Template to use when generating the game
        --outdir <dir>           Output directory (default: project root)
        --force                  Overwrite existing file
        --non-interactive        Do not prompt; use defaults and flags
        --description <text>     Pre-fill description
        --tags <comma-list>      Pre-fill tags/metadata
        --dry-run                Show output without writing files


run
    Start a game locally.

    Usage:
        dcs run [options]

    Options:
        --game <name|path>       Game to run (defaults to ./game.yml)
        --interface <cli|ui>     Choose interface mode
        --port <number>          Port for UI mode
        --host <address>         Bind host
        --env <env>              Environment profile
        --watch                  Hot-reload on changes
        --seed <number>          Random seed
        --log-level <level>      Logging verbosity


deploy
    Deploy a game using fly.toml.

    Usage:
        dcs deploy [options]

    Options:
        --config <path>          Path to fly.toml (default: ./fly.toml)
        --game <name|path>       Game to bundle/deploy
        --env <env>              Environment or deployment profile
        --region <code>          Deployment region override
        --dry-run                Show deploy steps without executing
        --no-build               Skip build step
        --build-only             Build but do not deploy
        --tag <tag>              Image or version tag


validate
    Validate a game configuration without running it.

    Usage:
        dcs validate --game <name|path>


list games
    List games in the current project.

    Usage:
        dcs list games
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import List, Literal, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from dcs_simulation_engine.helpers.game_helpers import create_game_from_template
from dcs_simulation_engine.helpers.game_helpers import list_games as _list_games

cli_theme = Theme(
    {
        "info": "bold cyan",
        "warning": "bold yellow",
        "error": "bold red",
        "success": "bold green",
        "title": "bold magenta",
    }
)
console = Console(theme=cli_theme)


InterfaceMode = Literal["cli", "ui"]
LogLevel = Literal["debug", "info", "warning", "error", "critical"]

# For env/region/tag/etc you can refine later
EnvName = str
RegionCode = str
ImageTag = str


def get_version() -> str:
    """Get the current package version."""
    try:
        return version("dcs-simulation-engine")  # your package name from pyproject
    except PackageNotFoundError:
        return "0.0.0"  # fallback for editable/local use


@dataclass
class GlobalOptions:
    """Global options for the CLI.

    Attributes:
        quiet (bool): Suppress non-error output.
        yes (bool): Assume "yes" for all prompts.
        config (Optional[Path]): Optional global config file.

    """

    quiet: bool = False
    yes: bool = False
    config: Optional[Path] = None


def echo(
    ctx: Optional[typer.Context],
    message: str,
    style: str = "info",
) -> None:
    """Respect global quiet flag; print only if not quiet."""
    quiet = False
    if ctx is not None and isinstance(ctx.obj, GlobalOptions):
        quiet = ctx.obj.quiet

    if quiet:
        return

    console.print(message, style=style)


def version_callback(value: bool) -> None:
    """Callback to display version and exit."""
    if value:
        console.print(f"dcs v{get_version()}", style="title", highlight=False)
        raise typer.Exit()


# ---------------------------------------------------------------------------
# App + sub-apps
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=True,
    help="DCS CLI entrypoint.",
)

create_app = typer.Typer(help="Create resources (e.g., games).")
list_app = typer.Typer(help="List resources (e.g., games).")


# ---------------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=False)
def main(
    ctx: typer.Context,
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output.",
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
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Initialize global CLI options and context."""
    ctx.obj = GlobalOptions(quiet=quiet, yes=yes, config=config)


# ---------------------------------------------------------------------------
# create game
# ---------------------------------------------------------------------------


@create_app.command("game")
def create_game(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Name of the game. If omitted, you will be prompted.",
    ),
) -> None:
    """Create a new game from the default template.

    Examples:
      dcs create game my-game
      dcs create game
    """
    if name is None:
        name = typer.prompt("Game name", default="my-game")

    created_path = create_game_from_template(name)

    echo(
        ctx,
        f"Created new game '{name}' from template at: {created_path}",
        style="success",
    )
    echo(
        ctx,
        "Game configuration can be modified in file.",
        style="info",
    )


app.add_typer(create_app, name="create")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command("run")
def run_game(
    ctx: typer.Context,
    game: Path = typer.Option(
        Path("game.yml"),
        "--game",
        help="Game to run (defaults to ./game.yml).",
        dir_okay=False,
        file_okay=True,
    ),
    interface: InterfaceMode = typer.Option(
        "cli",
        "--interface",
        help="Interface mode (cli or ui).",
        case_sensitive=False,
    ),
    port: Optional[int] = typer.Option(
        None,
        "--port",
        help="Port for UI mode.",
    ),
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind host.",
    ),
    env: Optional[EnvName] = typer.Option(
        None,
        "--env",
        help="Environment profile.",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        help="Hot-reload on changes.",
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed",
        help="Random seed.",
    ),
    log_level: Optional[LogLevel] = typer.Option(
        None,
        "--log-level",
        help="Logging verbosity (debug, info, warning, error, critical).",
    ),
) -> None:
    """Start a game locally."""
    # Stub behavior: show run configuration
    table = Table(
        title="Run Configuration", show_header=True, header_style="bold magenta"
    )
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Game", str(game))
    table.add_row("Interface", interface)
    table.add_row("Host", host)
    table.add_row("Port", str(port) if port is not None else "<auto>")
    table.add_row("Env", env or "<default>")
    table.add_row("Watch", str(watch))
    table.add_row("Seed", str(seed) if seed is not None else "<random>")
    table.add_row("Log level", log_level or "<default>")

    echo(ctx, Panel(table, title="[title]dcs run[/title]"))

    # TODO: Implement actual game runtime logic here
    echo(ctx, "Game runtime would start here.", style="success")


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------


@app.command("deploy")
def deploy_game(
    ctx: typer.Context,
    config: Path = typer.Option(
        Path("fly.toml"),
        "--config",
        help="Path to fly.toml (default: ./fly.toml).",
        dir_okay=False,
        file_okay=True,
    ),
    game: Optional[Path] = typer.Option(
        None,
        "--game",
        help="Game to bundle/deploy.",
        dir_okay=False,
        file_okay=True,
    ),
    env: Optional[EnvName] = typer.Option(
        None,
        "--env",
        help="Environment or deployment profile.",
    ),
    region: Optional[RegionCode] = typer.Option(
        None,
        "--region",
        help="Deployment region override.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show deploy steps without executing.",
    ),
    no_build: bool = typer.Option(
        False,
        "--no-build",
        help="Skip build step.",
    ),
    build_only: bool = typer.Option(
        False,
        "--build-only",
        help="Build but do not deploy.",
    ),
    tag: Optional[ImageTag] = typer.Option(
        None,
        "--tag",
        help="Image or version tag.",
    ),
) -> None:
    """Deploy a game using fly.toml."""
    steps: List[str] = []

    if not no_build:
        steps.append("Build image")
    else:
        steps.append("Skip build (no-build)")

    if not build_only:
        steps.append("Push image")
        steps.append("Deploy to Fly.io")
    else:
        steps.append("Build only; no deploy")

    table = Table(title="Deploy Plan", show_header=True, header_style="bold magenta")
    table.add_column("Field")
    table.add_column("Value")

    table.add_row("Config", str(config))
    table.add_row("Game", str(game) if game else "<auto-detect>")
    table.add_row("Env", env or "<default>")
    table.add_row("Region", region or "<provider default>")
    table.add_row("Tag", tag or "<auto>")
    table.add_row("Dry run", str(dry_run))
    table.add_row("No build", str(no_build))
    table.add_row("Build only", str(build_only))

    echo(ctx, Panel(table, title="[title]dcs deploy[/title]"))

    steps_table = Table(show_header=True, header_style="bold cyan", title="Steps")
    steps_table.add_column("#", justify="right")
    steps_table.add_column("Action")

    for i, step in enumerate(steps, start=1):
        steps_table.add_row(str(i), step)

    echo(ctx, steps_table)
    if dry_run:
        echo(ctx, "Dry run: deployment not executed.", style="warning")
        return

    # TODO: Implement actual deployment logic here
    echo(ctx, "Deployment pipeline would execute here.", style="success")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


@app.command("validate")
def validate_game(
    ctx: typer.Context,
    game: Path = typer.Option(
        ...,
        "--game",
        help="Game configuration file to validate.",
        dir_okay=False,
        file_okay=True,
        exists=True,
        readable=True,
    ),
) -> None:
    """Validate a game configuration without running it."""
    # TODO: Replace stub with real validation
    echo(
        ctx,
        f"Validating game configuration at [bold]{game}[/bold]...",
        style="info",
    )

    # Stub: pretend validation passed
    echo(ctx, "TODO: implement validation logic.", style="error")


# ---------------------------------------------------------------------------
# list games
# ---------------------------------------------------------------------------


@list_app.command("games")
def list_games(ctx: typer.Context) -> None:
    """List games in the current project."""
    table = Table(
        title="Games in Project", show_header=True, header_style="bold magenta"
    )
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Path")

    # built-in games
    for name, version, path, description in _list_games():
        table.add_row(name, version or "—", description or "—", str(path))

    # project-local games (if ./games exists)
    project_games_dir = Path.cwd() / "games"
    if project_games_dir.exists():
        for name, version, path, description in _list_games(project_games_dir):
            table.add_row(name, version or "—", description or "—", str(path))

    echo(ctx, Panel(table, title="[title]dcs list games[/title]"))


app.add_typer(list_app, name="list")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    app()


if __name__ == "__main__":
    run()
