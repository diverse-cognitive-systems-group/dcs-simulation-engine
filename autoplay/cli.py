"""Command line interface for autoplay."""

import asyncio
import logging
import os
from pathlib import Path
from typing import Annotated

import typer
import typer.rich_utils as ru
from autoplay.driver import PlayerHarness
from autoplay.players import player_from_spec
from dotenv import load_dotenv
from rich.console import Console
from rich.theme import Theme

# Keep Typer/Rich help styling aligned with dcs_simulation_engine.cli.app.
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

cli_theme = Theme(
    {
        "success": "green",
        "warning": "bold bright_yellow",
        "error": "bold bright_red",
    }
)
console = Console(theme=cli_theme)
app = typer.Typer(rich_markup_mode="rich", help="Run automated API players against a live DCS engine.")


def echo(message: str, style: str = "white", *, quiet: bool = False) -> None:
    """Print one message using the same visual style as the DCS CLI."""
    if quiet:
        return
    console.print(message, style=style)


@app.command("run")
def run(
    models: Annotated[
        list[str] | None,
        typer.Option(
            "--model",
            help=("Run one automated player. Repeat for multiple players. Supported forms: openrouter:<model-id>, python:<path.py>."),
        ),
    ] = None,
    base_url: str = typer.Option(
        "http://127.0.0.1:8000",
        "--base-url",
        help="Base URL for the running DCS API.",
    ),
    max_turns_per_assignment: int = typer.Option(
        20,
        "--max-turns-per-assignment",
        min=1,
        help="Maximum player inputs to send before stopping one assignment.",
    ),
    timeout: float = typer.Option(
        60.0,
        "--timeout",
        min=1.0,
        help="HTTP/WebSocket timeout in seconds.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress non-error output.",
    ),
) -> None:
    """Run one or more automated players against an already-running DCS API."""
    _load_environment()
    specs = list(models or [])
    if not specs:
        echo("At least one --model is required.", style="error", quiet=quiet)
        raise typer.Exit(code=1)

    _configure_logging(quiet=quiet)
    try:
        _preflight_specs(specs)
    except Exception as exc:
        echo(str(exc), style="error", quiet=quiet)
        raise typer.Exit(code=1) from exc

    try:
        players = [player_from_spec(spec) for spec in specs]
    except Exception as exc:
        echo(str(exc), style="error", quiet=quiet)
        raise typer.Exit(code=1) from exc

    try:
        results = asyncio.run(
            _run_players(
                base_url=base_url,
                players=players,
                max_turns_per_assignment=max_turns_per_assignment,
                timeout=timeout,
                quiet=quiet,
            )
        )
    except Exception as exc:
        echo(str(exc), style="error", quiet=quiet)
        raise typer.Exit(code=1) from exc

    for result in results:
        completed = result.completed_assignments == len(result.assignments)
        style = "success" if completed else "warning"
        marker = "✓" if completed else "!"
        echo(
            (f"{marker} {result.model_id}: completed {result.completed_assignments}/{len(result.assignments)} assignment(s)"),
            style=style,
            quiet=quiet,
        )
        for assignment in result.assignments:
            if assignment.error:
                echo(
                    f"  {assignment.game_name}: {assignment.status} after {assignment.turns} turn(s): {assignment.error}",
                    style="error",
                    quiet=quiet,
                )


async def _run_players(*, base_url: str, players: list, max_turns_per_assignment: int, timeout: float, quiet: bool):
    results = []
    total = len(players)
    for index, player in enumerate(players, start=1):
        echo(f"[{index}/{total}] {player.model_id}: starting", style="dim", quiet=quiet)
        harness = PlayerHarness(
            base_url=base_url,
            player=player,
            max_turns_per_assignment=max_turns_per_assignment,
            timeout=timeout,
            on_event=_event_printer(quiet=quiet),
        )
        result = await harness.run()
        results.append(result)
        echo(f"[{index}/{total}] {player.model_id}: finished", style="dim", quiet=quiet)
    return results


def _configure_logging(*, quiet: bool) -> None:
    level = logging.ERROR if quiet else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s")
    logging.getLogger("autoplay").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


def _load_environment() -> None:
    load_dotenv(Path.cwd() / ".env")


def _preflight_specs(specs: list[str]) -> None:
    for spec in specs:
        provider, separator, value = spec.partition(":")
        provider = provider.strip().lower()
        if not separator or not provider or not value.strip():
            raise ValueError(f"Invalid --model value: {spec!r}. Use openrouter:<model-id> or python:<path.py>.")
        if provider == "openrouter" and not os.getenv("OPENROUTER_API_KEY", "").strip():
            raise RuntimeError("OPENROUTER_API_KEY is required for --model openrouter:<model-id>.")


def _event_printer(*, quiet: bool):
    def print_event(event: str, payload: dict) -> None:
        model_id = payload["model_id"]
        if event == "player_started":
            echo(f"  {model_id}: registered player {payload['player_id']} for {payload['run_name']}", style="dim", quiet=quiet)
        elif event == "assignment_started":
            echo(
                f"  {model_id}: playing {payload['game_name']} "
                f"(assignment {payload['assignment_id']}, session {payload['session_id']})",
                style="dim",
                quiet=quiet,
            )
        elif event == "turn_sent":
            echo(f"  {model_id}: turn {payload['turns']} -> {_shorten(str(payload['input']))}", style="dim", quiet=quiet)
        elif event == "assignment_exited":
            echo(
                f"  {model_id}: assignment exited after {payload['turns']} turn(s): {payload['reason']}",
                style="dim",
                quiet=quiet,
            )
        elif event == "assignment_failed":
            echo(
                f"  {model_id}: assignment failed after {payload['turns']} turn(s): {payload['error']}",
                style="error",
                quiet=quiet,
            )
        elif event == "player_completed":
            echo(f"  {model_id}: run assignments complete", style="success", quiet=quiet)
        elif event == "no_assignment":
            echo(f"  {model_id}: no assignment available", style="warning", quiet=quiet)

    return print_event


def _shorten(text: str, limit: int = 96) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def main() -> None:
    """Entrypoint for console scripts and python -m autoplay."""
    app()


if __name__ == "__main__":
    main()
