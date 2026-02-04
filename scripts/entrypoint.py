"""DCS CLI."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional

import typer
from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.errors import DCSError
from dcs_simulation_engine.helpers import deployment_helpers as dh
from dcs_simulation_engine.helpers.cli_helpers import get_version
from dcs_simulation_engine.helpers.game_helpers import (
    create_game_from_template,
    validate_game_compiles,
)
from dcs_simulation_engine.helpers.game_helpers import list_games as _list_games
from dcs_simulation_engine.helpers.logging_helpers import configure_logger
from dcs_simulation_engine.utils.misc import parse_kv, validate_port
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

LogLevel = Literal["debug", "info", "warning", "error", "critical"]


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
# App + verb-first sub-apps
# ---------------------------------------------------------------------------

app = typer.Typer(
    add_completion=True,
    help="Command line interface for the DCS Simulation Engine.",
)

list_app = typer.Typer(help="List resources.")
create_app = typer.Typer(help="Create resources.")
validate_app = typer.Typer(help="Validate resources.")
run_app = typer.Typer(help="Run resources.")
delete_app = typer.Typer(help="Delete resources.")
stop_app = typer.Typer(help="Stop resources.")

app.add_typer(list_app, name="list")
app.add_typer(create_app, name="create")
app.add_typer(validate_app, name="validate")
app.add_typer(run_app, name="run")
app.add_typer(delete_app, name="delete")
app.add_typer(stop_app, name="stop")

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
        "--version",  # no short option to avoid conflict with -v/--verbose
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
) -> None:
    """Initialize global CLI options and context."""
    ctx.obj = GlobalOptions(quiet=quiet, yes=yes, config=config)
    configure_logger(source="dcs-cli", quiet=quiet, verbose=verbose)


# ---------------------------------------------------------------------------
# list: games / characters / players / deployments
# ---------------------------------------------------------------------------


@list_app.command("games")
def list_games(ctx: typer.Context) -> None:
    """List available games."""
    table = Table(
        title="Available Games",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
    )
    table.add_column("Name")
    table.add_column("Description")

    for name, _, _, description in _list_games():
        table.add_row(name, description or "—")

    echo(ctx, Panel(table, title="[title]dcs list games[/title]"))


@list_app.command("deployments")
def list_deployments(ctx: typer.Context) -> None:
    """List deployments (Fly apps)."""
    try:
        dh.check_flyctl()
        apps = dh.flyctl_json(["apps", "list"])
    except FileNotFoundError:
        echo(
            ctx, "flyctl not found. Install Fly CLI to list deployments.", style="error"
        )
        raise typer.Exit(code=1)
    except subprocess.CalledProcessError as e:
        err = (e.stderr or "").strip() or (e.stdout or "").strip() or str(e)
        echo(ctx, f"flyctl failed while listing apps:\n{err}", style="error")
        raise typer.Exit(code=e.returncode)
    except json.JSONDecodeError as e:
        echo(ctx, f"flyctl returned non-JSON output: {e}", style="error")
        raise typer.Exit(code=1)
    except Exception as e:
        echo(ctx, f"Failed to list deployments: {e}", style="error")
        raise typer.Exit(code=1)

    table = Table(title="Deployments", show_header=True, header_style="bold magenta")
    table.add_column("Name")
    table.add_column("Organization")
    table.add_column("Status")

    if isinstance(apps, list) and apps:
        for a in apps:
            name = str(a.get("Name") or a.get("name") or "—")
            org = str(a.get("Organization") or a.get("organization") or "—")
            status = str(a.get("Status") or a.get("status") or "—")
            table.add_row(name, org, status)
    else:
        table.add_row("—", "—", "No deployments found")

    echo(ctx, Panel(table, title="[title]dcs list deployments[/title]"))


@list_app.command("characters")
def list_characters(ctx: typer.Context) -> None:
    """List available characters."""
    try:
        chars = dbh.list_characters()
        # TODO: when proper db migrations are set up, can remove this
        if len(chars) == 0:
            echo(
                ctx,
                "No characters found. You may need to seed the database first (dcs create db).",
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

    echo(ctx, Panel(table, title="[title]dcs list characters[/title]"))


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

    echo(ctx, Panel(table, title="[title]dcs list players[/title]"))


# ---------------------------------------------------------------------------
# create: game / character / player / deployment / database
# ---------------------------------------------------------------------------


@create_app.command("game")
def create_game(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Name of the game. If omitted, you will be prompted.",
    ),
) -> None:
    """Create a new game from the default template."""
    if name is None:
        name = typer.prompt("Game name", default="my-game")

    try:
        created_path = create_game_from_template(name)
    except FileExistsError:
        typer.secho(
            f"A game named '{name}' already exists.\n"
            f"Delete it or choose a different name.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    echo(
        ctx,
        f"Created new game '{name}' from template. "
        f"Modify the configuration in {created_path} to customize your game.",
        style="success",
    )


@create_app.command("deployment")
def create_deployment(
    ctx: typer.Context,
    game: str = typer.Argument(..., help="Game name to deploy (e.g., my-game)."),
    deployment: Optional[str] = typer.Argument(
        None,
        help="Deployment name (Fly app name). If omitted, you will be prompted.",
    ),
    version: str = typer.Option(
        "latest",
        "--version",
        help="Version selector (currently informational).",
    ),
    fly_toml: Path = typer.Option(
        Path("fly.toml"),
        "--fly-toml",
        help="Path to fly.toml.",
    ),
    env_file: Optional[Path] = typer.Option(
        Path(".env"),
        "--env-file",
        help="Optional .env file to load/forward (excluding FLY_API_TOKEN).",
    ),
    region: Optional[str] = typer.Option(
        None,
        "--region",
        help="Override primary_region in fly.toml (optional).",
    ),
) -> None:
    """Create a deployment for a game (Fly.io)."""
    if not deployment:
        deployment = typer.prompt("Deployment name", default=f"{game}")

    try:
        dh.check_flyctl()
        loaded = (
            dh.load_env(env_file=env_file) if env_file else dh.load_env(env_file=None)
        )
    except Exception as e:
        logger.error(str(e))
        raise typer.Exit(code=1)

    try:
        # Treat deployment as the Fly app name directly.
        app_name = deployment

        cmd = dh.build_process_command(
            "widget",
            game=game,
            version=version,
            tag=None,  # tag no longer needed if app name is explicit
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
            "Forwarding .env keys to Fly (excluding FLY_API_TOKEN): %s",
            ", ".join(visible_env_keys) or "(none)",
        )

        deploy_cmd = dh.build_deploy_cmd(config_path, app_name, loaded.dotenv_vars)
        logger.info("Deploying with: %s", " ".join(deploy_cmd))
        subprocess.run(deploy_cmd, check=True)

        echo(ctx, f"Deployment created: {app_name}", style="success")

    except subprocess.CalledProcessError as e:
        logger.error(f"flyctl failed with exit code {e.returncode}")
        raise typer.Exit(code=e.returncode)
    except Exception:
        logger.exception("Deploy failed")
        raise typer.Exit(code=1)


@create_app.command("character")
def create_character(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Character name. If omitted, you will be prompted.",
    ),
    fields: List[str] = typer.Argument(
        None,
        help="Extra character fields as key=value (values may be JSON).",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a JSON file containing character fields.",
        dir_okay=False,
        file_okay=True,
        exists=True,
        readable=True,
    ),
    character_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="Explicit character _id to upsert.",
    ),
    no_key: bool = typer.Option(
        False,
        "--no-key",
        help="Do not issue a new access key.",
    ),
) -> None:
    """Create a character.

    TODO: prefer wait to implement until schema+validation is in place.
    """
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)


@create_app.command("player")
def create_player(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Player name. If omitted, you will be prompted (unless name is in --file/fields).",
    ),
    fields: List[str] = typer.Argument(
        None,
        help="Extra player fields as key=value (values may be JSON).",
    ),
    file: Optional[Path] = typer.Option(
        None,
        "--file",
        "-f",
        help="Path to a JSON file containing player fields.",
        dir_okay=False,
        file_okay=True,
        exists=True,
        readable=True,
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
    """Create a player and print id + access key.

    Input precedence:
      key=value args > --file JSON > interactive prompts/defaults
    """
    data: dict = {}

    if file is not None:
        try:
            parsed = json.loads(file.read_text())
            if not isinstance(parsed, dict):
                raise typer.BadParameter(
                    "--file JSON must be an object at the top level."
                )
            data.update(parsed)
        except json.JSONDecodeError as e:
            raise typer.BadParameter(f"Invalid JSON in --file: {e}") from e

    kv = parse_kv(fields or [])
    if kv:
        data.update(kv)

    resolved_name = data.get("name") or name
    if not resolved_name:
        resolved_name = typer.prompt("Player name")
    data["name"] = resolved_name

    no_structured_input = (file is None) and (not (fields or []))
    if no_structured_input:
        if "email" not in data:
            email = typer.prompt("Email (optional)", default="", show_default=False)
            if email.strip():
                data["email"] = email

    try:
        created_id, raw_key = dbh.create_player(
            data,
            player_id=player_id,
            issue_access_key=not no_key,
        )
    except Exception as e:
        echo(ctx, f"Failed to create player: {e}", style="error")
        raise typer.Exit(code=1)

    console.print(f"id={created_id}")
    console.print(f"access_key={raw_key if raw_key else 'None'}")


@create_app.command("database")
def create_database(
    ctx: typer.Context,
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-initialization of the database (overwrite existing data).",
    ),
) -> None:
    """Create the database."""
    res = dbh.init_or_seed_database(force=True)
    if res["seeded"]:
        echo(ctx, "Database initialized and seeded.", style="success")
    else:
        echo(ctx, "Database already exists. No action taken.", style="info")


# ---------------------------------------------------------------------------
# validate: game / character
# ---------------------------------------------------------------------------


@validate_app.command("game")
def validate_game(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Game name to validate."),
) -> None:
    """Validate a game configuration without running it.

    This check verifies that the game configuration is well-formed and that the
    game graph compiles successfully. It does NOT execute the game logic or
    validate behavior across all branches or runtime paths.

    Creators are responsible for testing gameplay logic, branching behavior,
    and node interactions manually or by adding explicit tests (as done for
    core games).
    """
    echo(ctx, f"Validating game configuration [bold]{name}[/bold]...", style="info")

    try:
        path = validate_game_compiles(name)
    except DCSError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    typer.secho(
        "Warning: This validation only checks configuration and graph compilation. "
        "It does not test gameplay behavior, branching logic, or node execution.",
        fg=typer.colors.YELLOW,
    )

    echo(
        ctx,
        f"Game configuration [bold]{name}[/bold] is valid.\n" f"Config path: {path}",
        style="success",
    )


@validate_app.command("character")
def validate_character(
    ctx: typer.Context,
    character: Optional[str] = typer.Argument(
        None,
        help="Character ID (preferred). If omitted, you will be prompted.",
    ),
) -> None:
    """Validate a character.

    Validate character against schema and create analysis_notebooks dir if needed.

    Warn user that they have to run manual analysis, all we can do is verify schema.
    """
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# run: game
# ---------------------------------------------------------------------------


@run_app.command("game")
def run_game(
    ctx: typer.Context,
    name: str = typer.Argument(
        "explore", help="Game name to run (default: explore).", show_default=True
    ),
    host: str = typer.Option(
        "0.0.0.0", "--host", help="Host interface to bind the Gradio server to."
    ),
    port: int = typer.Option(
        8080,
        "--port",
        callback=lambda v: (
            v
            if validate_port(v)
            else (_ for _ in ()).throw(
                typer.BadParameter("port must be between 1 and 65535")
            )
        ),
        help="Port to run the Gradio server on.",
    ),
    banner: str = typer.Option(
        "<b>DEFAULT BANNER</b>",
        "--banner",
        help="Optional markdown banner to show at the top of the widget.",
    ),
    share: bool = typer.Option(False, "--share", help="Create a public Gradio link."),
) -> None:
    """Run a game locally."""
    gradio_app = None
    try:
        dbh.init_or_seed_database()

        logger.debug("Building Gradio widget...")
        gradio_app = build_widget(game_name=name, banner=banner)

        # Friendly instructions
        browser_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        base_url = f"http://{browser_host}:{port}"

        typer.echo()
        typer.secho("Game server starting…", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"• Play in your browser: {base_url}")
        typer.secho(
            "When you're ready to close it, press Ctrl+C.", fg=typer.colors.YELLOW
        )
        typer.echo()

        logger.info(f"Launching Gradio widget ({host}:{port})...")
        launch_info = gradio_app.launch(
            server_name=host,
            server_port=port,
            share=share,
            quiet=True,  # TODO: update to use typer context
            prevent_thread_lock=True,
        )

        # If share=True, Gradio returns a public URL in many versions
        public_url = (
            getattr(launch_info, "share_url", None) if launch_info is not None else None
        )
        if public_url:
            typer.secho(f"Public link: {public_url}", fg=typer.colors.CYAN)

        # Block until Ctrl+C
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt. Shutting down...")
            raise typer.Exit(code=130)

    except Exception:
        logger.exception("Failed while building, launching, or running the widget")
        raise typer.Exit(code=1)
    finally:
        if gradio_app is not None:
            try:
                gradio_app.close()
            except Exception:
                logger.debug(
                    "Suppressing exception during gradio_app.close()", exc_info=True
                )


# ---------------------------------------------------------------------------
# delete: character / player
# ---------------------------------------------------------------------------


@delete_app.command("character")
def delete_character(
    ctx: typer.Context,
    character: Optional[str] = typer.Argument(
        None,
        help="Character ID (preferred). If omitted, you will be prompted.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Do not prompt for confirmation.",
    ),
) -> None:
    """Delete a character."""
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)


@delete_app.command("player")
def delete_player(
    ctx: typer.Context,
    player: Optional[str] = typer.Argument(
        None,
        help="Player ID (preferred). If omitted, you will be prompted.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Do not prompt for confirmation.",
    ),
) -> None:
    """Delete a player."""
    echo(ctx, "Not implemented", style="warning")
    raise typer.Exit(code=2)


# ---------------------------------------------------------------------------
# stop: deployment
# ---------------------------------------------------------------------------


@stop_app.command("deployment")
def stop_deployment(
    ctx: typer.Context,
    deployment: Optional[str] = typer.Argument(
        None,
        help="Deployment name (Fly app name). If omitted, you will be prompted.",
    ),
    logs_out: Optional[Path] = typer.Option(
        None,
        "--logs-out",
        help="Write recent logs to this file (JSON lines). If omitted, logs are not downloaded.",
        dir_okay=False,
        file_okay=True,
    ),
    logs_no_tail: bool = typer.Option(
        True,
        "--no-tail/--tail",
        help="Fetch buffered logs only (recommended for stop workflow).",
    ),
    db_remote: Optional[str] = typer.Option(
        None,
        "--db-remote",
        help="Remote DB file path on the VM to download (e.g., /data/db.sqlite3).",
    ),
    db_out: Optional[Path] = typer.Option(
        None,
        "--db-out",
        help="Local path to save the downloaded DB file. Defaults to ./<deployment>-db.sqlite3",
        dir_okay=False,
        file_okay=True,
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Do not prompt for confirmation.",
    ),
) -> None:
    """Stop a deployment and optionally download logs + DB."""
    if not deployment:
        deployment = typer.prompt("Deployment name")

    auto_yes = bool(getattr(ctx.obj, "yes", False))
    if not force and not auto_yes:
        ok = typer.confirm(
            f"Stop deployment '{deployment}'? This will stop its Machines.",
            default=False,
        )
        if not ok:
            echo(ctx, "Cancelled.", style="warning")
            raise typer.Exit(code=0)

    try:
        dh.check_flyctl()
    except Exception as e:
        echo(ctx, str(e), style="error")
        raise typer.Exit(code=1)

    # 1) Deployment time (best-effort)
    last_release_when = None
    try:
        releases = _flyctl_json(["releases", "--app", deployment])
        if isinstance(releases, list) and releases:
            r0 = releases[0]
            last_release_when = (
                r0.get("CreatedAt")
                or r0.get("created_at")
                or r0.get("createdAt")
                or r0.get("created")
            )
    except Exception:
        pass

    if last_release_when:
        echo(ctx, f"Last deploy: {last_release_when}", style="info")

    # 2) Download logs (best-effort)
    if logs_out:
        try:
            cmd = ["flyctl", "logs", "--app", deployment]
            if logs_no_tail:
                cmd.append("--no-tail")
            cmd.append("--json")
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logs_out.parent.mkdir(parents=True, exist_ok=True)
            logs_out.write_text(proc.stdout)
            echo(ctx, f"Wrote logs to: {logs_out}", style="success")
        except subprocess.CalledProcessError as e:
            err = (e.stderr or "").strip() or (e.stdout or "").strip() or str(e)
            echo(ctx, f"Failed to download logs:\n{err}", style="warning")

    # 3) Download DB file (best-effort)
    if db_remote:
        try:
            if db_out is None:
                db_out = Path(f"{deployment}-db.sqlite3")
            subprocess.run(
                [
                    "flyctl",
                    "ssh",
                    "sftp",
                    "get",
                    db_remote,
                    str(db_out),
                    "--app",
                    deployment,
                ],
                check=True,
            )
            echo(ctx, f"Downloaded DB to: {db_out}", style="success")
        except subprocess.CalledProcessError as e:
            echo(
                ctx,
                f"Failed to download DB (sftp get). Exit={e.returncode}",
                style="warning",
            )
        except Exception as e:
            echo(ctx, f"Failed to download DB: {e}", style="warning")

    # 4) Stop all machines
    try:
        machines = _flyctl_json(["machine", "list", "--app", deployment])
        machine_ids: list[str] = []
        if isinstance(machines, list):
            for m in machines:
                mid = m.get("id") or m.get("ID") or m.get("Id")
                if mid:
                    machine_ids.append(str(mid))

        if machine_ids:
            subprocess.run(
                ["flyctl", "machine", "stop", *machine_ids, "--app", deployment],
                check=True,
            )
        echo(ctx, f"Stopped deployment: {deployment}", style="success")
    except subprocess.CalledProcessError as e:
        echo(
            ctx,
            f"flyctl failed while stopping machines (exit {e.returncode})",
            style="error",
        )
        raise typer.Exit(code=e.returncode)
    except Exception as e:
        echo(ctx, f"Failed to stop deployment '{deployment}': {e}", style="error")
        raise typer.Exit(code=1)

    # 5) Cost note
    echo(
        ctx,
        "Cost note: stopped Machines are cheaper than running, but billing is best verified in Fly invoices/dashboard.",
        style="info",
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    app()


if __name__ == "__main__":
    run()
