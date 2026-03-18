"""Shared cli utilities."""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import typer
from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.cli.bootstrap import create_provider_admin
from rich.console import Console
from rich.theme import Theme

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
    mongo_uri: Optional[str] = None
    server_url: str = "http://localhost:8000"


def get_client(ctx: Optional[typer.Context]) -> APIClient:
    """Return an APIClient configured from the CLI context."""
    url = "http://localhost:8000"
    if ctx is not None and isinstance(getattr(ctx, "obj", None), GlobalOptions):
        url = ctx.obj.server_url
    return APIClient(url=url)


def echo(ctx: Optional[typer.Context], message: str, style: str = "white") -> None:
    """Respect global quiet flag; print only if not quiet."""
    quiet = False
    if ctx is not None and isinstance(getattr(ctx, "obj", None), GlobalOptions):
        quiet = ctx.obj.quiet

    if quiet:
        return

    console.print(message, style=style)


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


def seed_database(ctx: typer.Context, seed_dir: Path) -> None:
    """Seed the database from JSON/NDJSON files."""
    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)
    try:
        admin = create_provider_admin(mongo_uri=mongo_uri)
        result = admin.seed_database(seed_dir=seed_dir)
    except Exception as e:
        echo(ctx, str(e), style="error")
        raise typer.Exit(code=1)
    echo(ctx, f"Seeded: {result}")
