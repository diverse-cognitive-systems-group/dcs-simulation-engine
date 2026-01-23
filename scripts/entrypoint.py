"""DCS CLI Entrypoint."""

import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import List, Literal, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from dcs_simulation_engine.helpers import database_helpers as dbh
from dcs_simulation_engine.helpers import deploy_helpers as dh
from dcs_simulation_engine.helpers.game_helpers import (
    create_game_from_template,
    parse_kv,
)
from dcs_simulation_engine.helpers.game_helpers import list_games as _list_games
from dcs_simulation_engine.helpers.logging_helpers import configure_logger
from dcs_simulation_engine.widget.widget import build_widget

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


def _validate_port(port: int) -> int:
    if not (1 <= port <= 65535):
        raise typer.BadParameter("port must be between 1 and 65535")
    return port


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

create_app = typer.Typer(help="Create resources (e.g., games, players, databases).")
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

    # built-in games
    for name, version, path, description in _list_games():
        table.add_row(name, version or "—", description or "—")

    # project-local games (if ./games exists)
    project_games_dir = Path.cwd() / "games"
    if project_games_dir.exists():
        for name, version, path, description in _list_games(project_games_dir):
            table.add_row(name, version or "—", description or "—")

    echo(ctx, Panel(table, title="[title]dcs list games[/title]"))


app.add_typer(list_app, name="list")


# ---------------------------------------------------------------------------
# create
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


@create_app.command("player")
def create_player(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Player name. If omitted, you will be prompted.",
    ),
    fields: List[str] = typer.Argument(
        None,
        help="Extra player fields as key=value (values may be JSON).",
    ),
    player_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Explicit player _id to upsert.",
    ),
    no_key: bool = typer.Option(
        False,
        "--no-key",
        help="Do not issue a new access key.",
    ),
) -> None:
    """Create a player and print id + access key."""
    if name is None:
        name = typer.prompt("Player name")

    data = parse_kv(fields or [])
    # Let explicit argument win unless user also passes name=... in fields
    data.setdefault("name", name)

    created_id, raw_key = dbh.create_player(
        data,
        player_id=player_id,
        issue_access_key=not no_key,
    )

    # Treat as command output (don’t hide behind --quiet)
    console.print(f"id={created_id}")
    console.print(f"access_key={raw_key if raw_key else 'None'}")


# TODO: when we know how we are going to handle dbs (dev, prod) rework this script
# to create empty, reseed, reset, local/cloud, etc.
@create_app.command("database")
def create_database(
    ctx: typer.Context,
    db_name: str = typer.Option(
        dbh.DEFAULT_DB_NAME,
        "--db-name",
        help=f"Database name (default: {dbh.DEFAULT_DB_NAME}).",
    ),
    seeds_dir: Optional[Path] = typer.Option(
        dbh.SEEDS_DIR_DEFAULT,
        "--seeds-dir",
        help="Directory containing seed files.",
    ),
    force: bool = typer.Option(False, "--force", help="Re-seed even if non-empty."),
) -> None:
    """Seed the database with initial data from seed files."""
    # Best-effort cluster-wide warning (may silently no-op if no privileges)
    if dbh.warn_if_db_name_exists(db_name) and not force:
        console.print(
            f"A database named '{db_name}' already exists on this cluster.",
            style="warning",
        )

    result = dbh.init_or_seed_database(
        db_name=db_name, seeds_dir=seeds_dir, force=force
    )

    if not result["seeded"] and result.get("reason") == "db_not_empty" and not force:
        existing = result.get("existing_collections", [])
        preview = ", ".join(existing[:8]) + (" ..." if len(existing) > 8 else "")
        auto_yes = bool(getattr(ctx.obj, "yes", False))

        if not auto_yes:
            ok = typer.confirm(
                f"Database '{db_name}' has {len(existing)} collection(s): {preview}\n"
                "Re-seed from files? This will drop/replace seeded collections.",
                default=False,
            )
            if not ok:
                console.print("Cancelled.", style="warning")
                raise typer.Exit()

        result = dbh.init_or_seed_database(
            db_name=db_name, seeds_dir=seeds_dir, force=True
        )

    console.print(
        f"Seeded database '{db_name}' from {result['seeds_dir']}.", style="success"
    )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


@app.command("run")
def run_game(
    ctx: typer.Context,
    game: str = typer.Option(
        "explore",
        "--game",
        help="Name of the game to launch (default: explore).",
    ),
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        help="Host interface to bind the Gradio server to (default: 0.0.0.0).",
    ),
    port: int = typer.Option(
        8080,
        "--port",
        callback=lambda v: _validate_port(v),
        help="Port to run the Gradio server on (default: 8080).",
    ),
    banner: str = typer.Option(
        "<b>LIVE EXPERIMENT</b>",
        "--banner",
        help="Optional markdown banner to show at the top of the widget.",
    ),
    share: bool = typer.Option(
        False,
        "--share",
        help="Create a public Gradio link.",
    ),
    verbose: int = typer.Option(
        0,
        "-V",
        "--verbose",
        count=True,
        help="Increase console verbosity: -V for INFO, -VV for DEBUG.",
    ),
) -> None:
    """Start/run a game locally.

    Examples:
      dcs run
      dcs run --game Explore --banner "<b>DEMO</b>"
    """
    # Configure logging
    try:
        configure_logger(source="run_game")
    except Exception as e:
        logger.warning(f"Failed to configure logger with source 'run_game': {e}")

    # Console side-channel based on verbosity
    if verbose > 0:
        level = "DEBUG" if verbose > 1 else "INFO"
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
        )

    app = None
    try:
        logger.debug("Building Gradio widget...")
        app = build_widget(
            game_name=game,
            banner=banner,
            # source=source,  # enable when supported
        )

        logger.info(f"Launching Gradio widget ({host}:{port})...")
        app.launch(
            server_name=host,
            server_port=port,
            share=share,
        )
    except KeyboardInterrupt:
        logger.info("Received interrupt. Shutting down...")
        raise typer.Exit(code=130)
    except Exception:
        logger.exception("Failed while building, launching, or running the widget")
        raise typer.Exit(code=1)
    finally:
        if app is not None:
            try:
                app.close()
            except Exception:
                logger.debug("Suppressing exception during app.close()", exc_info=True)


# ---------------------------------------------------------------------------
# deploy
# ---------------------------------------------------------------------------


@app.command("deploy")
def deploy_game(
    ctx: typer.Context,
    game: str = typer.Option(
        ...,
        "--game",
        help="Game name to deploy. This creates a public/live game/experiment.",
    ),
    version: str = typer.Option(
        "latest",
        "--version",
        help="Version selector (currently informational; kept for parity).",
    ),
    fly_toml: Path = typer.Option(
        Path("fly.toml"),
        "--fly-toml",
        help="Path to fly.toml.",
    ),
    tag: Optional[str] = typer.Option(
        None,
        "--tag",
        help="Short tag to distinguish app instances (letters/numbers/dashes).",
    ),
    env_file: Path = typer.Option(
        Path(".env"),
        "--env-file",
        help="Path to .env file to load and forward (excluding FLY_API_TOKEN).",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="Override primary_region in fly.toml (optional).",
    ),
    base_app_name: str = typer.Option(
        dh.DEFAULT_BASE_APP_NAME,
        "--base-app-name",
        help="Base Fly app name used when --tag is not provided.",
    ),
    with_db: bool = typer.Option(
        False,
        "--with-db",
        help="Deploy with a new DB (not implemented).",
    ),
) -> None:
    """Deploy a game publicly using Fly.io servers.

    Updates fly.toml and runs flyctl deploy
    """
    if with_db:
        raise typer.BadParameter("--with-db is not implemented yet.")

    try:
        dh.check_flyctl()
        loaded = dh.load_env(env_file=env_file)
    except Exception as e:
        logger.error(str(e))
        raise typer.Exit(code=1)

    try:
        tag_norm = dh.validate_tag(tag) if tag else None
        app_name = dh.compute_app_name(base_app_name=base_app_name, tag=tag_norm)
        cmd = dh.build_process_command(
            "widget",
            game=game,
            version=version,
            tag=tag_norm,
        )

        config_path = fly_toml
        original = config_path.read_text()

        updated = dh.update_app_and_region(original, app_name=app_name, region=region)
        updated = dh.update_process_cmd(updated, cmd)
        config_path.write_text(updated)

        logger.info("Updated fly.toml app=%r process=%s", app_name, cmd)
        dh.ensure_app_exists(app_name)

        visible_env_keys = [
            k for k in loaded.dotenv_vars.keys() if k != "FLY_API_TOKEN"
        ]
        logger.info(
            "Forwarding .env keys to Fly (excluding FLY_API_TOKEN):",
            f" {', '.join(visible_env_keys) or '(none)'}",
            ", ".join(visible_env_keys) or "(none)",
        )

        deploy_cmd = dh.build_deploy_cmd(config_path, app_name, loaded.dotenv_vars)
        logger.info("Deploying with: %s", " ".join(deploy_cmd))
        subprocess.run(deploy_cmd, check=True)

    except subprocess.CalledProcessError as e:
        logger.error(f"flyctl failed with exit code {e.returncode}")
        raise typer.Exit(code=e.returncode)
    except Exception as e:
        logger.exception(f"Deploy failed: {e}")
        raise typer.Exit(code=1)


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
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    app()


if __name__ == "__main__":
    run()
