"""Command line interface for autoplay."""

import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer
import typer.rich_utils as ru
from autoplay.driver import PlayerHarness
from autoplay.players import player_from_spec
from dotenv import load_dotenv
from loguru import logger
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
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss,SSS} autoplay {level} {file.name}:{line} | {message}"


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
    log_dir: Path = typer.Option(
        Path("logs"),
        "--log-dir",
        help="Directory for autoplay run logs.",
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

    log_path = _configure_logging(log_dir=log_dir, quiet=quiet)
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

    _print_run_summary(
        base_url=base_url,
        players=players,
        max_turns_per_assignment=max_turns_per_assignment,
        timeout=timeout,
        log_path=log_path,
        quiet=quiet,
    )

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


def _configure_logging(*, log_dir: Path, quiet: bool) -> Path:
    logger.remove()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"autoplay_{datetime.now(UTC).strftime('%Y%m%d')}.log"
    console_level = "ERROR" if quiet else "WARNING"
    logger.add(sys.stderr, level=console_level, format="{message}")
    logger.add(
        log_path,
        level="INFO",
        format=LOG_FORMAT,
        encoding="utf-8",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    return log_path


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


def _print_run_summary(
    *,
    base_url: str,
    players: list,
    max_turns_per_assignment: int,
    timeout: float,
    log_path: Path,
    quiet: bool,
) -> None:
    echo("Autoplay run", style="white", quiet=quiet)
    echo(f"  API: {base_url}", style="dim", quiet=quiet)
    echo(f"  Models: {', '.join(player.model_id for player in players)}", style="dim", quiet=quiet)
    echo(f"  Max turns per assignment: {max_turns_per_assignment}", style="dim", quiet=quiet)
    echo(f"  Timeout: {timeout:g}s", style="dim", quiet=quiet)
    echo(f"  Log file: {log_path}", style="dim", quiet=quiet)
    prompts = sorted({str(getattr(player, "system_prompt", "")) for player in players if getattr(player, "system_prompt", "")})
    for index, prompt in enumerate(prompts, start=1):
        label = "Model system prompt" if len(prompts) == 1 else f"Model system prompt {index}"
        echo(f"  {label}: {prompt}", style="dim", quiet=quiet)
    logger.info("Autoplay run started")
    logger.info("API: {}", base_url)
    logger.info("Models: {}", ", ".join(player.model_id for player in players))
    logger.info("Max turns per assignment: {}", max_turns_per_assignment)
    logger.info("Timeout: {}s", f"{timeout:g}")
    logger.info("Log file: {}", log_path)
    for index, prompt in enumerate(prompts, start=1):
        label = "Model system prompt" if len(prompts) == 1 else f"Model system prompt {index}"
        logger.info("{}: {}", label, _single_line(prompt, limit=600))


def _event_printer(*, quiet: bool):
    state: dict[str, dict[str, int]] = {}

    def print_event(event: str, payload: dict) -> None:
        model_id = payload["model_id"]
        model_state = state.setdefault(model_id, {"assignment": 0, "turn": 0})
        if event == "player_started":
            logger.info("Player registered: model={} player={} run={}", model_id, payload["player_id"], payload["run_name"])
            echo(f"  {model_id}: registered player {payload['player_id']} for {payload['run_name']}", style="dim", quiet=quiet)
        elif event == "assignment_started":
            model_state["assignment"] += 1
            model_state["turn"] = 0
            characters = _character_summary(payload)
            logger.info(
                "Assignment {} started: {} ({}, session={}, assignment={})",
                model_state["assignment"],
                payload["game_name"],
                characters,
                payload["session_id"],
                payload["assignment_id"],
            )
            echo("", quiet=quiet)
            echo(f"Assignment {model_state['assignment']}: {payload['game_name']}", style="white", quiet=quiet)
            echo(f"Characters: {characters}", style="white", quiet=quiet)
            echo(f"Session: {payload['session_id']}", style="dim", quiet=quiet)
        elif event == "turn_sent":
            model_state["turn"] += 1
            logger.info("Turn {} player input: {}", model_state["turn"], _single_line(str(payload["input"])))
            echo("", quiet=quiet)
            echo(f"Turn {model_state['turn']}", style="white", quiet=quiet)
            echo(f"Player: {_shorten(str(payload['input']))}", style="dim", quiet=quiet)
        elif event == "message_received":
            _log_received_message(payload)
            _print_received_message(payload, quiet=quiet)
        elif event == "assignment_exited":
            turn_count = model_state.get("turn", 0)
            logger.info(
                "Assignment {} exited after {} turn(s): {}",
                model_state["assignment"],
                turn_count,
                payload["reason"],
            )
            echo("", quiet=quiet)
            echo(
                f"Assignment {model_state['assignment']} ended after {turn_count} turn(s)",
                style="warning",
                quiet=quiet,
            )
            echo(
                f"Reason: {payload['reason']}",
                style="warning",
                quiet=quiet,
            )
        elif event == "assignment_failed":
            turn_count = model_state.get("turn", 0)
            logger.error(
                "Assignment {} failed after {} turn(s): {}",
                model_state["assignment"],
                turn_count,
                _single_line(str(payload["error"]), limit=1200),
            )
            echo("", quiet=quiet)
            echo(
                f"Assignment {model_state['assignment']} failed after {turn_count} turn(s)",
                style="error",
                quiet=quiet,
            )
            echo(
                f"Error: {payload['error']}",
                style="error",
                quiet=quiet,
            )
        elif event == "player_completed":
            logger.info("Player completed all assignments: model={}", model_id)
            echo(f"  {model_id}: run assignments complete", style="success", quiet=quiet)
        elif event == "no_assignment":
            logger.warning("No assignment available: model={}", model_id)
            echo(f"  {model_id}: no assignment available", style="warning", quiet=quiet)

    return print_event


def _print_received_message(payload: dict, *, quiet: bool) -> None:
    event_type = str(payload.get("event_type") or "")
    role = str(payload.get("role") or "")
    content = _shorten(str(payload.get("content") or ""))
    if not content:
        return

    if event_type == "error":
        echo(f"Error: {content}", style="error", quiet=quiet)
    elif event_type == "warning":
        echo(f"Warning: {content}", style="warning", quiet=quiet)
    elif event_type == "info":
        echo(f"Info: {content}", style="white", quiet=quiet)
    elif role == "simulator":
        echo(f"Simulator: {content}", style="dim", quiet=quiet)
    else:
        echo(f"Server: {content}", style="dim", quiet=quiet)


def _log_received_message(payload: dict) -> None:
    label = _message_label(payload)
    content = _format_log_content(str(payload.get("content") or ""))
    if not content:
        return

    if payload.get("event_type") == "error":
        _log_content(logger.error, label, content)
    elif payload.get("event_type") == "warning":
        _log_content(logger.warning, label, content)
    else:
        _log_content(logger.info, label, content)


def _message_label(payload: dict) -> str:
    event_type = str(payload.get("event_type") or "")
    role = str(payload.get("role") or "")
    if event_type == "error":
        return "Server error"
    if event_type == "warning":
        return "Server warning"
    if event_type == "info":
        return "Info"
    if role == "simulator":
        return "Simulator"
    return "Server"


def _character_summary(payload: dict) -> str:
    pc_hid = str(payload.get("pc_hid") or "")
    npc_hid = str(payload.get("npc_hid") or "")
    labels = []
    if pc_hid:
        labels.append(f"PC: {pc_hid}")
    if npc_hid:
        labels.append(f"NPC: {npc_hid}")
    return ", ".join(labels) if labels else "unknown"


def _shorten(text: str, limit: int = 96) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def _single_line(text: str, limit: int = 240) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def _format_log_content(text: str, limit: int = 2000) -> str:
    content = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(content) <= limit:
        return content
    return f"{content[: limit - 3]}..."


def _log_content(log_method, label: str, content: str) -> None:
    if "\n" in content:
        log_method("{}:\n{}", label, _indent(content))
    else:
        log_method("{}: {}", label, content)


def _indent(text: str) -> str:
    return "\n".join(f"  {line}" if line else "" for line in text.splitlines())


def main() -> None:
    """Entrypoint for console scripts and python -m autoplay."""
    app()


if __name__ == "__main__":
    main()
