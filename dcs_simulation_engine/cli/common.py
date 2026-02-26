"""Shared cli utilities."""

import socket
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
from typing import List, Literal, Optional, Tuple

import typer
from rich.console import Console
from rich.theme import Theme

from dcs_simulation_engine.infra import deploy
from dcs_simulation_engine.utils.package import get_package_version

# TODO: this theme color scheme is YUCK. Make look nicer.
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
    """Global options for the CLI."""

    quiet: bool = False
    yes: bool = False
    config: Optional[Path] = None


def echo(ctx: Optional[typer.Context], message: str, style: str = "info") -> None:
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
        console.print(f"dcs v{get_package_version()}", style="title", highlight=False)
        raise typer.Exit()


def step(msg: str) -> None:
    """Print a step message."""
    typer.secho("• ", fg=typer.colors.BLUE, nl=False)
    typer.secho(msg, fg=typer.colors.BLUE, nl=False)


def done() -> None:
    """Print 'done' message."""
    typer.secho(" done.", fg=typer.colors.BLUE)


def check_localhost_http(
    host: str = "127.0.0.1",
    port: int = 8080,
    path: str = "/",
    timeout_s: float = 0.6,
) -> Tuple[str, str]:
    """Returns localhost status."""
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
            return ("Live", f"HTTP {code}")
        return ("Live", f"HTTP {code} (unhealthy)")
    except Exception as e:
        return ("Live", f"non-HTTP or no response: {e.__class__.__name__}")


def deployment_names(include_local: bool = True) -> Tuple[List[str], bool]:
    """Get deployment names."""
    apps = deploy.list_deployments() or []
    names = [
        (a.get("Name") or a.get("name"))
        for a in apps
        if (a.get("Name") or a.get("name"))
    ]

    local_is_running = check_localhost_http()[0] == "Live"
    if include_local and local_is_running and "local" not in names:
        names.append("local")

    return names, local_is_running


def select_deployment(
    ctx: typer.Context,
    deployment: Optional[str],
    *,
    include_local: bool = True,
) -> Tuple[str, bool]:
    """Select deployment, either from argument or prompt."""
    if deployment:
        # Still compute localhost state for downstream decisions.
        _, local_is_running = deployment_names(include_local=include_local)
        return deployment, local_is_running

    names, local_is_running = deployment_names(include_local=include_local)

    if not names:
        typer.secho(
            "Simulation engine isn't running anywhere (local or remote).",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit()

    for i, name in enumerate(names, 1):
        typer.echo(f"{i}. {name}")

    choice = typer.prompt("Select deployment", type=int)

    try:
        app = names[choice - 1]
    except (IndexError, ValueError):
        typer.secho("Invalid selection.", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    return app, local_is_running
