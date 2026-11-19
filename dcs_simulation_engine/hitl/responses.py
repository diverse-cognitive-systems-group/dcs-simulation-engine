"""Generate and resume play for character evaluation transcripts."""

import asyncio
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Event, Lock
from time import sleep

import httpx
import typer
from dcs_simulation_engine.api.client import APIClient, SimulationRun
from dcs_simulation_engine.api.models import CreateGameRequest
from dcs_simulation_engine.errors import APIRequestError
from dcs_simulation_engine.hitl import ScenarioFile
from dcs_simulation_engine.hitl.create import load_scenario_file
from dcs_simulation_engine.hitl.evaluation import (
    Turn,
    backup_evaluation_file,
    iter_sessions,
    load_evaluation_file,
    save_evaluation_file,
    transcript_parts,
)
from rich.text import Text


class ReplayDeclined(RuntimeError):
    """The evaluator declined to replace recorded session work."""


class InvalidSession(ValueError):
    """A saved session cannot be used for the requested transcript."""


def _normalize_role(role: str) -> str:
    lowered = role.strip().lower()
    if lowered in {"assistant", "simulator"}:
        return "assistant"
    if lowered in {"user", "player"}:
        return "user"
    return lowered


def _history_last_role(history: list[dict]) -> str | None:
    if not history:
        return None
    return _normalize_role(str(history[-1].get("role", "")))


def _selected_scenarios(
    scenario_file: ScenarioFile,
    *,
    only: list[str] | None,
    include_ids: list[str] | None,
    exclude: list[str] | None,
) -> list[tuple[int, int]]:
    """Return selected (group_idx, scenario_idx) pairs."""
    selected: list[tuple[int, int]] = []
    for g_idx, group in enumerate(scenario_file.scenario_groups):
        for s_idx, scenario in enumerate(group.scenarios):
            sid = scenario.id
            if only and sid not in only and (not include_ids or sid not in include_ids):
                continue
            if exclude and sid in exclude:
                continue
            selected.append((g_idx, s_idx))
    return selected


def compute_status_summary(
    path: Path,
    *,
    only: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict[str, int]:
    """Return totals plus incomplete-work counts for the selected scenarios."""
    scenario_file = load_scenario_file(path)
    selected = _selected_scenarios(
        scenario_file,
        only=only,
        include_ids=include_ids,
        exclude=exclude,
    )

    summary = {
        "scenario_groups_total": len({g_idx for g_idx, _s_idx in selected}),
        "scenarios_total": len(selected),
        "attempts_total": 0,
        "attempts_without_simulator_responses": 0,
        "attempts_without_player_feedback": 0,
        "empty_conversation_histories": 0,
        "conversation_histories_missing_simulator_reply": 0,
    }

    for g_idx, s_idx in selected:
        scenario = scenario_file.scenario_groups[g_idx].scenarios[s_idx]
        summary["attempts_total"] += len(scenario.attempts)
        if not scenario.conversation_history:
            summary["empty_conversation_histories"] += 1
        elif _history_last_role(scenario.conversation_history) == "user":
            summary["conversation_histories_missing_simulator_reply"] += 1

        for attempt in scenario.attempts:
            if attempt.simulator_response is None:
                summary["attempts_without_simulator_responses"] += 1
            elif attempt.evaluator_feedback is None:
                summary["attempts_without_player_feedback"] += 1

    return summary


def compute_status_counts(
    path: Path,
    *,
    only: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict[str, int]:
    """Return post-update counts for the selected scenarios."""
    summary = compute_status_summary(
        path,
        only=only,
        include_ids=include_ids,
        exclude=exclude,
    )
    return {
        "attempts_missing_simulator_responses": summary["attempts_without_simulator_responses"],
        "attempts_missing_player_feedback": summary["attempts_without_player_feedback"],
        "empty_conversation_histories": summary["empty_conversation_histories"],
        "conversation_histories_missing_simulator_reply": summary["conversation_histories_missing_simulator_reply"],
    }


def render_status_summary(
    summary: dict[str, int],
    *,
    title: str = "Scenario File Summary",
) -> str:
    """Render a stable human-readable summary block."""
    scenarios_total = summary["scenarios_total"]
    attempts_total = summary["attempts_total"]
    lines = [
        f"[bold]{title}[/bold]",
        f"  {summary['scenario_groups_total']} scenario group(s)",
        f"  {scenarios_total} scenario(s)",
        f"  {attempts_total} attempt(s)",
        (f"  {summary['attempts_without_simulator_responses']}/{attempts_total} attempt(s) without simulator responses"),
        (f"  {summary['attempts_without_player_feedback']}/{attempts_total} attempt(s) without player feedback"),
        (f"  {summary['empty_conversation_histories']}/{scenarios_total} empty conversation history/histories"),
        (
            f"  {summary['conversation_histories_missing_simulator_reply']}/{scenarios_total} "
            "conversation history/histories missing a simulator reply"
        ),
    ]
    return "\n".join(lines)


def _classify_output(events, *, opening):
    """Keep setup and auxiliary info in the transcript, and make replies ratable."""
    if not opening and not any(event["source"] == "npc" for event in events):
        for event in events:
            event.update(source="npc", evaluator_feedback=None)
    return events


def _output_event(kind, content):
    if kind in ("ai", "message", "warning", "error"):
        return {
            "type": "message" if kind == "ai" else kind,
            "source": "npc",
            "content": content,
            "evaluator_feedback": None,
        }
    return {"type": "info", "source": "system", "content": content}


def _read_session(server_url, api_key, session_id):
    url = f"{server_url.rstrip('/')}/api/sessions/{session_id}/reconstruction"
    for attempt in range(3):
        response = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=30)
        if response.status_code == 404:
            raise InvalidSession(f"Saved session {session_id} was unavailable.")
        response.raise_for_status()
        payload = response.json()
        # Runtime snapshots can be visible before the corresponding event batch.
        snapshot = payload["session"].get("runtime_state") or {}
        recorded_turns = {
            event.get("turn_index")
            for event in payload["events"]
            if event.get("direction") == "outbound" and event.get("event_type") in ("message", "command")
        }
        if snapshot.get("turn_count", 0) <= len(recorded_turns):
            return payload["session"], _recorded_events(payload["events"])
        if attempt < 2:
            sleep(0.25)
    if (recovered := _recover_snapshot_history(payload)) is not None:
        return payload["session"], recovered
    raise InvalidSession(f"Session {session_id} has a newer snapshot than its saved transcript.")


def _recorded_events(rows):
    events = []
    for event in rows:
        if event["direction"] == "inbound":
            events.append({"type": "message", "source": "pc", "content": event["content"]})
        elif event["direction"] == "outbound":
            events.append(_output_event(event["event_type"], event["content"]))
    return events


def _snapshot_dialogue(snapshot, pc_hid):
    if snapshot.get("schema_version") != 1:
        return None
    transcript = (snapshot.get("game_state") or {}).get("filtered_transcript_buffer")
    if not isinstance(transcript, list):
        return None
    turns = []
    prompt = None
    pc_prefix = f"Player ({pc_hid}): "
    for line in transcript:
        if not isinstance(line, str):
            return None
        if prompt is None and line.startswith(pc_prefix):
            prompt = {"type": "message", "source": "pc", "content": line.removeprefix(pc_prefix)}
        elif prompt is None and line.startswith("Opening scene: "):
            turns.append([_output_event("ai", line.removeprefix("Opening scene: "))])
        elif prompt is not None and line.startswith("Simulator: "):
            turns.append([prompt, _output_event("ai", line.removeprefix("Simulator: "))])
            prompt = None
        else:
            return None
    if prompt is None and len(turns) == snapshot["turn_count"]:
        return turns
    return None


def _recover_snapshot_history(payload):
    """Fill gaps in the event log using matching dialogue from the saved runtime."""
    session = payload["session"]
    turns = _snapshot_dialogue(session["runtime_state"], session["pc_hid"])
    if turns is None:
        return None
    rows_by_turn = defaultdict(list)
    last_turn = 0
    for row in payload["events"]:
        if row["direction"] not in ("inbound", "outbound"):
            continue
        turn = row.get("turn_index")
        if not isinstance(turn, int) or turn < last_turn:
            return None
        rows_by_turn[turn].append(row)
        last_turn = turn
    history = _recorded_events(rows_by_turn.pop(0, []))
    for turn, expected in enumerate(turns, 1):
        events = _recorded_events(rows_by_turn.pop(turn, []))
        if len(expected) == 2 and not any(event["source"] == "pc" for event in events):
            events.insert(0, expected[0])
        if not any(event["source"] == "npc" and event["type"] == "message" for event in events):
            events.append(expected[-1])
        dialogue = [event for event in events if event["type"] == "message"]
        if _event_keys(dialogue) != _event_keys(expected):
            return None
        history.extend(events)
    for rows in rows_by_turn.values():
        history.extend(_recorded_events(rows))
    return history


def _event_keys(entries):
    # Command and warning types can differ between live and persisted events.
    return [(entry["source"] == "pc", entry["content"]) for entry in entries]


@dataclass
class SessionPlan:
    """A transcript and the server work needed to synchronize it."""

    node: dict
    label: str
    parts: list
    create: bool
    replace_reason: str = ""


def _plan_fresh(node, label, *, opening, include_branches, replace_reason=""):
    parts = transcript_parts(node["transcript"], opening=opening)
    if include_branches:
        parts = [
            part if isinstance(part, Turn) else _plan_fresh(part, f"{label} / branch {number}", opening=False, include_branches=True)
            for number, part in enumerate(parts, 1)
        ]
    return SessionPlan(node, label, parts, create=True, replace_reason=replace_reason)


def _plan_node(
    node,
    settings,
    label,
    read_session,
    *,
    replay_invalid,
    include_branches,
    parent_id=None,
    inherited=(),
    opening=True,
):
    try:
        if not node.get("session_id"):
            for descendant, _ in iter_sessions(node, opening=opening):
                if descendant.get("session_id") or any(entry.get("source") in ("npc", "system") for entry in descendant["transcript"]):
                    raise InvalidSession("The session has recorded work but no session ID.")
            return _plan_fresh(node, label, opening=opening, include_branches=include_branches)

        if not opening and not parent_id:
            raise InvalidSession("The recorded parent state is unavailable.")
        metadata, events = read_session(node["session_id"])
        if (
            str(metadata["game_name"]).casefold() != settings["game"].casefold()
            or metadata.get("pc_hid") != settings["pc_hid"]
            or metadata.get("npc_hid") != settings["npc_hid"]
            or metadata.get("branch_from_session_id") != parent_id
        ):
            raise InvalidSession("The saved game, characters, or parent differ from the evaluation.")

        if _event_keys(events[: len(inherited)]) != _event_keys(inherited):
            raise InvalidSession("The saved branch history differs from the transcript at its fork.")
        remote = transcript_parts(events[len(inherited) :], opening=opening)
        if opening and not remote[0].output:
            remote.pop(0)
        parts = transcript_parts(node["transcript"], opening=opening)
        cursor, offset = 0, len(inherited)
        needs_step = False
        needs_fork = False
        for i, part in enumerate(parts):
            if isinstance(part, Turn):
                if cursor == len(remote):
                    if part.output:
                        raise InvalidSession("The transcript has responses missing from the saved session.")
                    needs_step = True
                    continue
                recorded = remote[cursor]
                if _event_keys([part.prompt] if part.prompt else []) != _event_keys([recorded.prompt] if recorded.prompt else []):
                    raise InvalidSession("The saved PC messages differ from the transcript.")
                if _event_keys(part.output) != _event_keys(recorded.output[: len(part.output)]):
                    raise InvalidSession("The saved responses differ from the transcript.")
                if not recorded.output:
                    raise InvalidSession("The saved PC turn has no response.")
                part.recorded = _classify_output(recorded.output, opening=part.prompt is None)
                cursor += 1
                offset += len(recorded.output) + (recorded.prompt is not None)
                continue
            if not include_branches:
                continue
            child = _plan_node(
                part,
                settings,
                f"{label} / branch {i + 1}",
                read_session,
                replay_invalid=replay_invalid,
                include_branches=True,
                parent_id=None if needs_step else node["session_id"],
                inherited=events[:offset],
                opening=False,
            )
            if child.create and cursor < len(remote):
                raise InvalidSession("The parent has advanced past a branch that needs a new session.")
            needs_fork |= child.create
            parts[i] = child
        if cursor != len(remote):
            raise InvalidSession("The server has PC turns missing from the transcript.")
        if (needs_step or needs_fork) and metadata["status"] not in ("active", "paused"):
            raise InvalidSession("The saved session has ended and cannot be advanced or branched.")
        return SessionPlan(node, label, parts, create=False)
    except InvalidSession as exc:
        if not replay_invalid:
            raise ValueError(f"{label}: {exc} Re-run with --replay-invalid-sessions to replay it.") from exc
        return _plan_fresh(
            node,
            label,
            opening=opening,
            include_branches=include_branches,
            replace_reason=str(exc),
        )


def _replacements(plan):
    if plan.replace_reason:
        yield plan
        return
    for part in plan.parts:
        if isinstance(part, SessionPlan):
            yield from _replacements(part)


def _confirm_replacements(path, data, selected, plans, console):
    replacements = [item for plan in plans.values() for item in _replacements(plan)]
    for plan in replacements:
        console.print(Text(f"{plan.label}: {plan.replace_reason}"), style="warning")
        for node, _ in iter_sessions(plan.node):
            if node.get("description"):
                console.print(Text(node["description"]), style="dim")
            for entry in node["transcript"]:
                if entry["type"] != "branch":
                    console.print(Text(f"{entry['source']}: {entry['content']}"), style="dim")
        console.print("Replaying replaces the saved sessions, simulator responses, and feedback in this transcript and its branches.")
        if not typer.confirm("Replay this session?", default=False):
            raise ReplayDeclined(f"{plan.label} was not confirmed. Evaluation update canceled.")
    current = load_evaluation_file(path)
    if (
        current["character_hid"] != data["character_hid"]
        or current["evaluator_id"] != data["evaluator_id"]
        or any(current["sessions"][i : i + 1] != data["sessions"][i : i + 1] for i in selected)
    ):
        raise ValueError("The selected sessions changed during preparation. Review the file and run update again.")
    if replacements:
        backup = backup_evaluation_file(path)
        console.print(f"Saved the original evaluation to {backup}", style="dim")


def _reset_plan(plan):
    plan.node["session_id"] = None
    for part in plan.parts:
        if isinstance(part, Turn):
            part.output.clear()
        elif isinstance(part, SessionPlan):
            _reset_plan(part)
        else:
            for node, _ in iter_sessions(part, opening=False):
                node["session_id"] = None
                node["transcript"] = [entry for entry in node["transcript"] if entry["type"] == "branch" or entry["source"] == "pc"]


def _materialize(plan):
    transcript = []
    for part in plan.parts:
        if isinstance(part, Turn):
            if part.prompt is not None:
                transcript.append(part.prompt)
            transcript.extend(part.output)
        elif isinstance(part, SessionPlan):
            transcript.append(_materialize(part))
        else:
            transcript.append(part)
    plan.node["transcript"] = transcript
    return plan.node


def _without_annotations(node):
    transcript = []
    for entry in node["transcript"]:
        if entry["type"] == "branch":
            transcript.append(_without_annotations(entry))
        elif entry["source"] == "pc":
            transcript.append({key: value for key, value in entry.items() if key != "evaluator_note"})
        else:
            transcript.append(entry)
    return {**node, "description": "", "transcript": transcript}


def _copy_annotations(source, target):
    target.pop("description", None)
    if "description" in source:
        target["description"] = source["description"]
    source_inputs = [entry for entry in source["transcript"] if entry["type"] == "branch" or entry["source"] == "pc"]
    target_inputs = [entry for entry in target["transcript"] if entry["type"] == "branch" or entry["source"] == "pc"]
    for old, new in zip(source_inputs, target_inputs, strict=True):
        if old["type"] == "branch":
            _copy_annotations(old, new)
        else:
            new.pop("evaluator_note", None)
            if "evaluator_note" in old:
                new["evaluator_note"] = old["evaluator_note"]


def _execute(plan, settings, client, api_key, checkpoint, stopped, *, parent_id=None):
    if stopped.is_set():
        return
    opening = parent_id is None
    if plan.create:
        if opening:
            try:
                run = client.start_game(
                    CreateGameRequest(
                        game=settings["game"],
                        pc_choice=settings["pc_hid"],
                        npc_choice=settings["npc_hid"],
                        api_key=api_key,
                        source="hitl",
                    )
                )
            except APIRequestError as exc:
                raise APIRequestError(
                    f"Could not start {settings['game']} with PC {settings['pc_hid']} and NPC {settings['npc_hid']}. "
                    f"DCS server error: {exc}"
                ) from exc
        else:
            run = client.branch_session(parent_id, api_key=api_key)
        if plan.replace_reason:
            _reset_plan(plan)
        plan.node["session_id"] = run.session_id
        checkpoint()
    else:
        resume = not opening or plan.parts[0].recorded is not None
        run = SimulationRun(
            client=client,
            session_id=plan.node["session_id"],
            game_name=settings["game"],
            api_key=api_key,
            resume_on_first_connect=resume,
        )

    for part in plan.parts:
        if stopped.is_set():
            return
        if isinstance(part, SessionPlan):
            _execute(part, settings, client, api_key, checkpoint, stopped, parent_id=run.session_id)
        elif isinstance(part, Turn):
            if part.recorded is not None:
                recovered = part.recorded[len(part.output) :]
                if recovered:
                    part.output.extend(recovered)
                    checkpoint()
                continue
            previous = len(run.history)
            run.step(part.prompt["content"] if part.prompt is not None else "")
            output = [_output_event(event.event_type, event.content) for event in run.history[previous:]]
            if not output:
                raise RuntimeError(f"{plan.label}: The simulator returned no events for the turn.")
            part.output = _classify_output(output, opening=part.prompt is None)
            checkpoint()


async def generate_responses(
    path: Path,
    *,
    server_url,
    api_key,
    selected,
    concurrency,
    include_branches,
    replay_invalid,
    console,
):
    """Validate selected session trees and save progress as each turn finishes."""
    data = load_evaluation_file(path)

    def read_session(session_id):
        return _read_session(server_url, api_key, session_id)

    plans = {
        index: await asyncio.to_thread(
            _plan_node,
            deepcopy(data["sessions"][index]),
            data["sessions"][index],
            f"Session {index + 1}",
            read_session,
            replay_invalid=replay_invalid,
            include_branches=include_branches,
        )
        for index in selected
    }
    _confirm_replacements(path, data, selected, plans, console)
    lock, stopped = Lock(), Event()

    def run(index):
        plan = plans[index]
        expected = data["sessions"][index]

        def checkpoint():
            nonlocal expected
            with lock:
                current = load_evaluation_file(path)
                if index >= len(current["sessions"]) or current["character_hid"] != data["character_hid"]:
                    raise ValueError(f"{plan.label} changed during generation. Progress was not applied.")
                latest = current["sessions"][index]
                if latest != expected and _without_annotations(latest) != _without_annotations(expected):
                    raise ValueError(f"{plan.label} changed during generation. Progress was not applied.")
                updated = _materialize(plan)
                if latest != expected:
                    _copy_annotations(latest, updated)
                current["sessions"][index] = updated
                save_evaluation_file(path, current)
                expected = deepcopy(updated)

        with APIClient(url=server_url, api_key=api_key) as client:
            _execute(plan, data["sessions"][index], client, api_key, checkpoint, stopped)

    semaphore = asyncio.Semaphore(concurrency)

    async def update(index):
        async with semaphore:
            try:
                await asyncio.to_thread(run, index)
            except Exception as exc:
                return f"Session {index + 1}: {exc}"
        return None

    try:
        failures = [failure for failure in await asyncio.gather(*(update(index) for index in selected)) if failure]
        if failures:
            raise RuntimeError("\n".join(failures))
    finally:
        stopped.set()
