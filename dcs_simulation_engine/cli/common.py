"""Shared cli utilities."""

import socket
from contextlib import contextmanager
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


@contextmanager
def step(msg: str):
    """Context manager for displaying a step with a spinner."""
    try:
        with console.status(msg, spinner="dots") as status:
            yield
    except Exception:
        status.stop()
        console.print(f"[red]✖[/red] {msg}", style="dim")
        raise
    else:
        status.stop()
        console.print(f"[green]✔[/green] {msg}", style="dim")


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


def select_run(
    ctx: typer.Context,
    run_name: Optional[str],
) -> str:
    """Select run, either from argument or prompt."""
    runs = load_runs()  # Dict[str, Dict[str, Any]]

    if not runs:
        console.print("No runs available to select from.", style="warning")
        raise typer.Exit(code=0)

    if run_name:
        if run_name not in runs:
            echo(ctx, f"Run '{run_name}' not found.", style="error")
            raise typer.Exit(code=1)
        return run_name

    names = list(runs.keys())

    for i, name in enumerate(names, 1):
        console.print(f"{i}. {name}")

    choice = typer.prompt("Select run", type=int)

    if not (1 <= choice <= len(names)):
        console.print("Invalid selection.", style="error")
        raise typer.Exit(code=1)

    return names[choice - 1]
