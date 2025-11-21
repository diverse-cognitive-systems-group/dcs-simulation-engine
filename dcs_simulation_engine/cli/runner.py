"""CLI runner for DCS Simulation Engine."""

from typing import Optional

from loguru import logger
from rich.console import Console

from dcs_simulation_engine.cli.configuration import load_theme
from dcs_simulation_engine.core.run_manager import RunManager

# TODO: consider adding game setup intro like the ascii art banner,
# game name, description, pc, npc, etc.


def _render_step(
    run: RunManager,
    console: Console,
    theme: dict[str, str],
    user_input: str,
) -> None:
    """Run one simulation step and render all resulting events."""
    for event in run.step(user_input):
        etype = event.get("type")
        content = event.get("content")

        if etype in {"ai", "assistant", "simulator", "system"}:
            console.print()
            console.print(content, style=theme["simulation-response"])

        elif etype == "info":
            console.print()
            console.print(content, style=theme["info"])

        elif etype == "warning":
            console.print()
            console.print(content, style=theme["warning"])

        elif etype == "error":
            console.print()
            console.print(content, style=theme["error"])

        # optional: lifecycle termination
        if event.get("lifecycle") == "EXIT":
            break


def run_cli(
    game: str,
    source: str,
    pc_choice: Optional[str] = None,
    npc_choice: Optional[str] = None,
    access_key: Optional[str] = None,
    custom_theme_path: Optional[str] = None,
) -> None:
    """Run the CLI interaction loop."""
    console = Console()
    theme = load_theme(custom_theme_path)

    try:
        with console.status("Setting up simulation...", spinner="dots"):
            run = RunManager.create(
                game=game,
                source=source,
                pc_choice=pc_choice,
                npc_choice=npc_choice,
                access_key=access_key,
            )
    except Exception as e:
        console.print(
            f"Failed to setup simulation with error: {e}", style=theme["error"]
        )
        logger.exception(f"Failed to setup simulation with error: {e}")
        raise

    console.rule("Game Started", style=theme["intro"])

    # system takes the first turn (empty user input)
    _render_step(run=run, console=console, theme=theme, user_input="")

    if run.state.get("lifecycle") == "EXIT":
        console.rule(f"Game Exited (reason: {run.exit_reason})", style=theme["outtro"])
        return

    while True:
        console.print()
        console.print("what do you do next?", style=theme["user-prompt"], end=" ")
        user_input = console.input().strip()

        if not user_input:  # user wants to exit
            break

        _render_step(run=run, console=console, theme=theme, user_input=user_input)

        if run.state.get("lifecycle") == "EXIT":
            break

    console.rule(f"Game Exited (reason: {run.exit_reason})", style=theme["outtro"])
