"""Collect feedback for simulator responses in the main and branch transcripts."""

from pathlib import Path

import typer
from dcs_simulation_engine.hitl.evaluation import is_response, load_evaluation_file, save_evaluation_file
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text


def _feedback_targets(session, *, path=(), context=(), descriptions=()):
    descriptions = (*descriptions, session.get("description", ""))
    history = list(context)
    for index, entry in enumerate(session["transcript"]):
        entry_path = (*path, index)
        if entry["type"] == "branch":
            yield from _feedback_targets(entry, path=entry_path, context=history, descriptions=descriptions)
            continue
        if is_response(entry) and entry.get("evaluator_feedback") is None:
            yield entry_path, session.get("session_id"), descriptions, history, entry
        history.append(entry)


def _prompt_feedback(console, label, session_id, descriptions, history, response):
    console.print(Rule(label, style="dim"))
    if session_id:
        console.print(Text(f"Session ID: {session_id}", style="dim"))
    for description in descriptions:
        if description:
            console.print(Text(description), style="dim")
    if history:
        latest_pc = next((entry for entry in reversed(history) if entry["source"] == "pc"), None)
        transcript = Table.grid(padding=(0, 1, 0, 0))
        transcript.add_column(no_wrap=True)
        transcript.add_column()
        for entry in history:
            source = entry["source"]
            speaker = {"pc": "PC", "npc": "Simulator", "system": "System"}[source]
            current = entry is latest_pc
            label_style = "bold green" if current else "bold dim"
            if source == "pc":
                content = Text(entry["content"], style="" if current else "dim")
            else:
                content = Markdown(entry["content"], style="dim", hyperlinks=False)
            transcript.add_row(Text(f"{speaker}:", style=label_style), content)
            if entry.get("evaluator_note"):
                note = Text.assemble(("Evaluator note: ", "bold"), entry["evaluator_note"], style="" if current else "dim")
                transcript.add_row("", note)
        console.print(transcript)
    kind = response["type"]
    title = "Simulator Response" if kind == "message" else f"Simulator Response ({kind.upper()})"
    console.print(
        Panel(Markdown(response["content"], hyperlinks=False), title=Text(title, style="bold cyan"), border_style="dim", expand=False)
    )

    # --- Thumbs ---
    while True:
        raw = (
            typer.prompt(
                "Rating  [u] up  [d] down (Enter to skip for now)",
                default="",
                show_default=False,
            )
            .strip()
            .lower()
        )
        if raw == "":
            return None
        if raw in ("u", "up", "y", "yes", "1"):
            liked = True
            break
        if raw in ("d", "down", "n", "no", "0"):
            liked = False
            break
        console.print("[warning]Enter 'u' for up, 'd' for down, or press Enter to skip.[/warning]")

    # --- Flags ---
    out_of_character = False
    doesnt_make_sense = False
    other_flag = False

    if not liked:
        console.print(
            "Flags (required for thumbs down):\n"
            "  o = out of character\n"
            "  s = doesn't make sense\n"
            "  x = other\n"
            "  Enter one or more letters, for example: os",
            style="dim",
        )
        while True:
            raw_flags = typer.prompt("Flags", default="").strip().lower()
            selected = set(raw_flags)
            valid = {"o", "s", "x"}
            if not selected:
                console.print("[warning]Select at least one flag for a thumbs-down response.[/warning]")
                continue
            if not selected.issubset(valid):
                console.print("[warning]Use only 'o', 's', and/or 'x'.[/warning]")
                continue
            out_of_character = "o" in selected
            doesnt_make_sense = "s" in selected
            other_flag = "x" in selected
            break

    # --- Comment ---
    comment = typer.prompt("Comment (Enter to skip)", default="").strip()

    console.print()

    return {
        "liked": liked,
        "comment": comment,
        "doesnt_make_sense": doesnt_make_sense,
        "out_of_character": out_of_character,
        "other": other_flag,
    }


def collect_feedback(path: Path, *, selected, console):
    """Prompt for unrated responses and checkpoint each rating."""
    data = load_evaluation_file(path)
    if data.get("evaluator_instructions"):
        console.print(Text.assemble(("Instructions: ", "bold"), data["evaluator_instructions"]))
        console.print()
    if data["evaluator_id"]:
        console.print(Text(f"Evaluator: {data['evaluator_id']}"), style="dim")
    for index in selected:
        root = data["sessions"][index]
        for entry_path, session_id, descriptions, history, response in _feedback_targets(root):
            label = f"Session {index + 1}" + "".join(f" / branch at entry {i + 1}" for i in entry_path[:-1])
            feedback = _prompt_feedback(console, label, session_id, descriptions, history, response)
            if feedback is None:
                console.print("Skipped. This response remains unrated.", style="dim")
                continue

            current = load_evaluation_file(path)
            if (
                current["evaluator_id"] != data["evaluator_id"]
                or current["character_hid"] != data["character_hid"]
                or current["sessions"][index : index + 1] != [root]
            ):
                raise ValueError("The evaluator, transcript, or response changed while feedback was being entered.")
            target = current["sessions"][index]
            for position in entry_path:
                target = target["transcript"][position]
            target["evaluator_feedback"] = feedback
            save_evaluation_file(path, current)
            response["evaluator_feedback"] = feedback
            console.print("Feedback saved.", style="dim")
