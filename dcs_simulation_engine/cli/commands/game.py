"""CLI game command — run a simulation via the API."""

from datetime import datetime
from typing import Optional

import typer
from dcs_simulation_engine.api.models import CreateGameRequest, WSEventFrame
from dcs_simulation_engine.cli.common import console, echo, get_client


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _print_events(events: list[WSEventFrame]) -> None:
    for e in events:
        if e.event_type == "ai":
            console.print(f"[dim][{_ts()}][/dim] {e.content}")
        elif e.event_type in ("info", "warning", "error"):
            console.print(f"[dim][{_ts()}] {e.content}[/dim]")


def game(
    ctx: typer.Context,
    game_name: str = typer.Argument(help="Name of the game to run (e.g. 'Explore')."),
    api_key: str = typer.Option(
        ...,
        "--api-key",
        "-k",
        envvar="DCS_API_KEY",
        help="Player API key.",
    ),
    pc: Optional[str] = typer.Option(
        None,
        "--pc",
        help="Player character ID or name.",
    ),
    npc: Optional[str] = typer.Option(
        None,
        "--npc",
        help="NPC character ID or name.",
    ),
) -> None:
    """Start an interactive game session."""
    request = CreateGameRequest(api_key=api_key, game=game_name, pc_choice=pc, npc_choice=npc, source="cli")

    try:
        with get_client(ctx) as client:
            run = client.start_game(request)
    except Exception as e:
        echo(ctx, str(e), style="error")
        raise typer.Exit(code=1)

    echo(ctx, f"Started session {run.session_id} — game: {run.game_name}")

    try:
        run.step()
    except Exception as e:
        echo(ctx, str(e), style="error")
        raise typer.Exit(code=1)

    _print_events(run.history)

    while not run.is_complete:
        try:
            user_input = typer.prompt(">")
        except (EOFError, KeyboardInterrupt):
            echo(ctx, "\nAborted.", style="warning")
            run.close()
            raise typer.Exit(code=0)

        prev_len = len(run.history)
        try:
            echo(ctx, f"[{_ts()}] Sent", style="dim")
            run.step(user_input)
        except Exception as e:
            echo(ctx, str(e), style="error")
            raise typer.Exit(code=1)

        _print_events(run.history[prev_len:])

    echo(ctx, f"Game complete after {run.turns} turn(s).")
