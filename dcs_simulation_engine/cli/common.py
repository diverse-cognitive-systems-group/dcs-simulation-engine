"""Shared cli utilities."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import typer
from rich.console import Console
from rich.theme import Theme

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
