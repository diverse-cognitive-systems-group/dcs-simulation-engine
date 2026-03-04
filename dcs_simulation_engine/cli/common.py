"""Shared cli utilities."""

import socket
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import Literal, Optional, Tuple

import typer
from rich.console import Console
from rich.theme import Theme

from dcs_simulation_engine.helpers.run_helpers import load_runs
from dcs_simulation_engine.utils.package import get_package_version

cli_theme = Theme(
    {
        "success": "green",
        "warning": "bold bright_yellow",
        "error": "bold bright_red",
    }
)
console = Console(theme=cli_theme)

LogLevel = Literal["debug", "info", "warning", "error", "critical"]


@dataclass
class GlobalOptions:
    """Global options for the CLI."""

    quiet: bool = False
    yes: bool = False
    config: Optional[Path] = None


def echo(ctx: Optional[typer.Context], message: str, style: str = "white") -> None:
    """Respect global quiet flag; print only if not quiet."""
    quiet = False
    if ctx is not None and isinstance(getattr(ctx, "obj", None), GlobalOptions):
        quiet = ctx.obj.quiet

    if quiet:
        return

    console.print(message, style=style)


def version_callback(value: bool) -> None:
    """Callback to display version and exit."""
    if value:
        console.print(f"dcs v{get_package_version()}", style="white", highlight=False)
        raise typer.Exit()


def step(msg: str) -> None:
    """Print a step message."""
    console.print("• ", style="dim", end="")
    console.print(msg, style="dim", end="")


def done() -> None:
    """Print 'done' message."""
    console.print(" done.", style="dim")


def check_localhost(
    host: str = "127.0.0.1",
    port: int = 8080,
    path: str = "/",
    timeout_s: float = 0.6,
) -> Tuple[str, str]:
    """Returns localhost status.

    "Down" = nothing is running on the port
    "Up" = something is running and responded to HTTP request (could still be unhealthy)
    """
    # First: fast TCP check
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
    except OSError as e:
        return ("Down", f"connect failed: {e.__class__.__name__}")

    # Second: attempt an HTTP request (some services may not be HTTP; treat that as "Live (non-HTTP)")
    try:
        conn = HTTPConnection(host, port, timeout=timeout_s)
        conn.request("GET", path)
        resp = conn.getresponse()
        code = resp.status
        # Drain to allow clean close on some implementations
        try:
            resp.read()
        except Exception:
            pass
        finally:
            conn.close()

        if 200 <= code < 400:
            return ("Up", f"HTTP {code}")
        return ("Up", f"HTTP {code} (unhealthy)")
    except Exception as e:
        return ("Up", f"non-HTTP or no response: {e.__class__.__name__}")


# def deployment_names(include_local: bool = True) -> Tuple[List[str], bool]:
#     """Get deployment names."""
#     apps = deploy.list_deployments() or []
#     names = [
#         (a.get("Name") or a.get("name"))
#         for a in apps
#         if (a.get("Name") or a.get("name"))
#     ]

#     local_is_running = check_localhost()[0] == "Up"
#     if include_local and local_is_running and "local" not in names:
#         names.append("local")

#     return names, local_is_running


def select_run(
    ctx: typer.Context,
    run_name: Optional[str],
) -> str:
    """Select run, either from argument or prompt."""
    runs = load_runs()
    if run_name:
        if run_name not in runs:
            echo(ctx, f"Run '{run_name}' not found.", style="error")
            raise typer.Exit(code=1)

    if not runs:
        console.print("No runs available to select from.", style="warning")
        raise typer.Exit()

    for i, name in enumerate(runs, 1):
        console.print(f"{i}. {name}")

    choice = typer.prompt("Select run", type=int)

    try:
        name = runs[choice - 1]
    except (IndexError, ValueError):
        console.print("Invalid selection.", style="error")
        raise typer.Exit(code=1)

    return name
