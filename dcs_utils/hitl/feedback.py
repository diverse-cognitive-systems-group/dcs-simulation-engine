"""Interactive evaluator feedback collection for HITL scenarios.

Walks through every attempt that has a simulator_response but lacks
evaluator_feedback, displays the scenario context and NPC output, then
prompts the evaluator for a thumbs rating, flags, and an optional comment.

Saving is atomic after each entry so the session is interrupt-safe; re-running
the command resumes from the first attempt without feedback.
"""

from datetime import datetime, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from dcs_utils.hitl import Attempt, EvaluatorFeedback, ScenarioGroup, Scenario
from dcs_utils.hitl.generate import load_scenario_file, save_scenario_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pending_attempts(
    scenario_file,
    *,
    only: list[str] | None,
    include_ids: list[str] | None,
    exclude: list[str] | None,
) -> list[tuple[int, int, int]]:
    """Return (group_idx, scenario_idx, attempt_idx) for attempts needing feedback.

    An attempt is eligible when it has a ``simulator_response`` but no
    ``evaluator_feedback``.  Scenarios without any simulator responses yet are
    silently skipped.
    """
    pending: list[tuple[int, int, int]] = []
    for g_idx, group in enumerate(scenario_file.scenario_groups):
        for s_idx, scenario in enumerate(group.scenarios):
            sid = scenario.id
            if only and sid not in only:
                if not include_ids or sid not in include_ids:
                    continue
            if exclude and sid in exclude:
                continue
            for a_idx, attempt in enumerate(scenario.attempts):
                if attempt.simulator_response is not None and attempt.evaluator_feedback is None:
                    pending.append((g_idx, s_idx, a_idx))
    return pending


def _count_awaiting_responses(scenario_file) -> int:
    return sum(
        1
        for group in scenario_file.scenario_groups
        for scenario in group.scenarios
        for attempt in scenario.attempts
        if attempt.simulator_response is None
    )


# ---------------------------------------------------------------------------
# Interactive prompt
# ---------------------------------------------------------------------------


def _prompt_feedback(
    console: Console,
    group: ScenarioGroup,
    scenario: Scenario,
    attempt: Attempt,
    attempt_label: str,
) -> EvaluatorFeedback:
    """Display one attempt and collect evaluator feedback interactively."""

    console.print(Rule(f"[bold]{group.label}[/bold]", style="dim"))
    console.print(
        f"  [dim]Expected failure:[/dim] {group.expected_failure_mode}"
    )
    console.print()
    console.print(
        f"  [bold]{scenario.id}[/bold] · {attempt_label}"
    )
    console.print(f"  [dim]{scenario.description}[/dim]")
    console.print(
        f"  [dim]Expected behavior:[/dim] {scenario.expected_pc_behavior}"
    )
    console.print()
    console.print(f"  [bold]Player:[/bold] {attempt.player_message}")
    console.print()

    response_text = attempt.simulator_response or "[no response]"
    console.print(
        Panel(
            Text(response_text),
            title="NPC Response",
            border_style="dim",
            expand=False,
        )
    )
    console.print()

    # --- Thumbs ---
    while True:
        raw = typer.prompt("Thumbs  [u] up  [d] down").strip().lower()
        if raw in ("u", "up", "y", "yes", "1"):
            liked = True
            break
        if raw in ("d", "down", "n", "no", "0"):
            liked = False
            break
        console.print("[warning]Enter 'u' for up or 'd' for down.[/warning]")

    # --- Flags ---
    out_of_character = False
    doesnt_make_sense = False
    other_flag = False

    if not liked:
        console.print(
            "Flags (press letter to toggle, Enter to confirm):\n"
            "  [o] out of character   [s] doesn't make sense   [x] other\n"
            "  Enter a string like 'os' to set multiple, or just Enter to skip.",
            style="dim",
        )
        raw_flags = typer.prompt("Flags", default="").strip().lower()
        out_of_character = "o" in raw_flags
        doesnt_make_sense = "s" in raw_flags
        other_flag = "x" in raw_flags

    # --- Comment ---
    comment = typer.prompt("Comment (Enter to skip)", default="").strip()

    console.print()

    return EvaluatorFeedback(
        liked=liked,
        comment=comment,
        doesnt_make_sense=doesnt_make_sense,
        out_of_character=out_of_character,
        other=other_flag,
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def collect_feedback(
    path: Path,
    *,
    evaluator_id: str = "",
    only: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude: list[str] | None = None,
    console: Console,
) -> None:
    """Walk through pending attempts and collect evaluator feedback.

    Args:
        path: Path to the ``<hid>-scenarios.json`` file.
        evaluator_id: Optional string recorded in each feedback entry.
        only: If set, process ONLY scenarios with these IDs.
        include_ids: Force-include these scenario IDs even when ``only`` is set.
        exclude: Skip scenarios with these IDs.
        console: Rich Console for output.
    """
    scenario_file = load_scenario_file(path)
    pending = _pending_attempts(
        scenario_file, only=only, include_ids=include_ids, exclude=exclude
    )

    awaiting = _count_awaiting_responses(scenario_file)
    if awaiting:
        console.print(
            f"[dim]{awaiting} attempt(s) still awaiting simulator responses — "
            f"skipping those.[/dim]"
        )

    if not pending:
        console.print("[success]All feedback recorded.[/success]")
        return

    console.print(
        f"Collecting feedback for [bold]{len(pending)}[/bold] attempt(s). "
        f"Press Ctrl-C to pause — progress is saved after each entry.\n"
    )
    if evaluator_id:
        console.print(f"Evaluator: [bold]{evaluator_id}[/bold]\n", style="dim")

    completed = 0
    try:
        for pos, (g_idx, s_idx, a_idx) in enumerate(pending):
            # Always reload from disk so we pick up concurrent changes
            scenario_file = load_scenario_file(path)
            group = scenario_file.scenario_groups[g_idx]
            scenario = group.scenarios[s_idx]
            attempt = scenario.attempts[a_idx]

            total_attempts_in_scenario = len(scenario.attempts)
            attempt_label = f"attempt {a_idx + 1}/{total_attempts_in_scenario}"

            console.print(
                f"\n[dim]── {pos + 1}/{len(pending)} ──[/dim]"
            )

            feedback = _prompt_feedback(
                console=console,
                group=group,
                scenario=scenario,
                attempt=attempt,
                attempt_label=attempt_label,
            )

            # Save atomically after each entry
            sf = load_scenario_file(path)
            sf.scenario_groups[g_idx].scenarios[s_idx].attempts[a_idx].evaluator_feedback = feedback
            save_scenario_file(path, sf)
            completed += 1

            result_icon = "[green]✔[/green]" if feedback.liked else "[red]✗[/red]"
            console.print(f"  {result_icon} Feedback saved.", style="dim")

    except (KeyboardInterrupt, typer.Abort):
        console.print(
            f"\n[warning]Paused after {completed} entr{'y' if completed == 1 else 'ies'}. "
            f"Run the command again to resume.[/warning]"
        )
        return

    console.print(
        f"\n[success]Done — {completed} feedback entr"
        f"{'y' if completed == 1 else 'ies'} recorded.[/success]"
    )
