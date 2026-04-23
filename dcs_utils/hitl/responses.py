"""Async shared-history sync and simulator response generation for HITL scenarios."""

import asyncio
from collections import defaultdict
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from dcs_simulation_engine.api.client import APIClient, SimulationRun
from dcs_simulation_engine.api.models import CreateGameRequest
from dcs_utils.hitl import Scenario, ScenarioFile, SimulatorResponseType
from dcs_utils.hitl.generate import load_scenario_file, save_scenario_file


class ParentSessionMissingError(RuntimeError):
    """Raised when a saved parent session can no longer be resumed."""


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


def compute_status_counts(
    path: Path,
    *,
    only: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude: list[str] | None = None,
) -> dict[str, int]:
    """Return post-update counts for the selected scenarios."""
    scenario_file = load_scenario_file(path)
    counts = {
        "attempts_missing_simulator_responses": 0,
        "attempts_missing_player_feedback": 0,
        "empty_conversation_histories": 0,
        "conversation_histories_missing_simulator_reply": 0,
    }

    for g_idx, s_idx in _selected_scenarios(
        scenario_file,
        only=only,
        include_ids=include_ids,
        exclude=exclude,
    ):
        scenario = scenario_file.scenario_groups[g_idx].scenarios[s_idx]
        if not scenario.conversation_history:
            counts["empty_conversation_histories"] += 1
        elif _history_last_role(scenario.conversation_history) == "user":
            counts["conversation_histories_missing_simulator_reply"] += 1

        for attempt in scenario.attempts:
            if attempt.simulator_response is None:
                counts["attempts_missing_simulator_responses"] += 1
            elif attempt.evaluator_feedback is None:
                counts["attempts_missing_player_feedback"] += 1

    return counts


def _latest_ai_content(events: list) -> str | None:
    """Return the latest AI event content from a list of websocket events."""
    for event in reversed(events):
        if getattr(event, "event_type", None) == "ai":
            content = str(getattr(event, "content", "") or "")
            return content or None
    return None


def _event_type_priority(event_type: str) -> int:
    priorities = {
        "ai": 0,
        "error": 1,
        "warning": 2,
        "info": 3,
    }
    return priorities.get(event_type, 99)


def _serialize_event(event) -> dict[str, str]:
    event_type = str(getattr(event, "event_type", "") or "info").lower()
    if event_type not in {"ai", "info", "error", "warning"}:
        event_type = "info"
    return {
        "event_type": event_type,
        "content": str(getattr(event, "content", "") or ""),
    }


def _select_attempt_response(events: list) -> tuple[str | None, SimulatorResponseType | None, list[dict[str, str]]]:
    """Pick the primary attempt response and preserve any extra events."""
    serialized = [_serialize_event(event) for event in events]
    if not serialized:
        return None, None, []

    ordered = sorted(
        enumerate(serialized),
        key=lambda item: (_event_type_priority(item[1]["event_type"]), item[0]),
    )
    primary_idx, primary = ordered[0]
    extras = [event for idx, event in enumerate(serialized) if idx != primary_idx]
    content = primary["content"] or None
    if content is None:
        return None, None, extras
    return content, primary["event_type"], extras


def _step_and_capture_events(run: SimulationRun, user_input: str = "") -> tuple[str | None, list]:
    """Advance one turn and return the AI reply plus all emitted events for that step."""
    previous_event_count = len(run.history)
    run.step(user_input)
    new_events = run.history[previous_event_count:]
    return _latest_ai_content(new_events), new_events


def _event_excerpt(content: str, limit: int = 120) -> str:
    content = " ".join(content.split())
    if len(content) <= limit:
        return content
    return content[: limit - 3] + "..."


def _describe_non_ai_events(events: list) -> str:
    parts: list[str] = []
    for event in events:
        event_type = str(getattr(event, "event_type", "") or "info").lower()
        if event_type == "ai":
            continue
        content = _event_excerpt(str(getattr(event, "content", "") or ""))
        if content:
            parts.append(f"{event_type}={content!r}")
        else:
            parts.append(event_type)

    if not parts:
        return "no non-AI events emitted"
    return ", ".join(parts[:3])


def _no_ai_warning(*, scenario_id: str, attempt_idx: int, branch: SimulationRun, events: list) -> str:
    branch_id = getattr(branch, "session_id", None) or "unknown-branch"
    details = _describe_non_ai_events(events)
    return (
        f"{scenario_id} attempt {attempt_idx + 1}: no simulator reply was emitted for branch {branch_id} "
        f"(turns={branch.turns}, exited={branch.is_complete}); observed {details}"
    )


def _scenario_request(*, scenario: Scenario, npc_hid: str, api_key: str) -> CreateGameRequest:
    """Build the start_game request for one scenario."""
    return CreateGameRequest(
        game=scenario.game,
        pc_choice=scenario.pc_hid,
        npc_choice=npc_hid,
        api_key=api_key or None,
        source="hitl",
    )


def _resume_parent_run(*, client: APIClient, scenario: Scenario, api_key: str) -> SimulationRun:
    return SimulationRun(
        client=client,
        session_id=str(scenario.parent_session_id),
        game_name=scenario.game,
        api_key=api_key or None,
        resume_on_first_connect=True,
    )


def _missing_parent_message(scenario: Scenario) -> str:
    return (
        f"{scenario.id}: saved parent session "
        f"{scenario.parent_session_id!r} is unavailable on the server. "
        "This usually means the session store was wiped, the DB was reset, "
        "or the server restarted without the persisted session data. "
        "Re-run with --regenerate-parent-session to rebuild the parent from the saved history."
    )


def _validate_parent_session(*, client: APIClient, scenario: Scenario, api_key: str) -> None:
    if not scenario.parent_session_id:
        raise ParentSessionMissingError(_missing_parent_message(scenario))

    try:
        _resume_parent_run(client=client, scenario=scenario, api_key=api_key).get_state()
    except Exception as exc:  # noqa: BLE001
        raise ParentSessionMissingError(_missing_parent_message(scenario)) from exc


def _rebuild_parent_session(
    *,
    client: APIClient,
    scenario: Scenario,
    npc_hid: str,
    api_key: str,
) -> str:
    """Rebuild a parent session from saved shared history."""
    root = client.start_game(_scenario_request(scenario=scenario, npc_hid=npc_hid, api_key=api_key))
    _step_and_capture_events(root, "")

    history = list(scenario.conversation_history or [])
    replay_limit = len(history)
    if _history_last_role(history) == "user":
        replay_limit -= 1

    for turn in history[:replay_limit]:
        if _normalize_role(str(turn.get("role", ""))) == "user":
            _step_and_capture_events(root, str(turn.get("content", "")))

    scenario.parent_session_id = root.session_id
    return root.session_id


def _bootstrap_empty_history(
    *,
    client: APIClient,
    scenario: Scenario,
    npc_hid: str,
    api_key: str,
    warnings: list[str],
) -> str:
    """Create a fresh parent and store the opening simulator turn."""
    root = client.start_game(_scenario_request(scenario=scenario, npc_hid=npc_hid, api_key=api_key))
    opening_text, opening_events = _step_and_capture_events(root, "")
    scenario.parent_session_id = root.session_id
    scenario.conversation_history = []
    if opening_text:
        scenario.conversation_history.append({"role": "assistant", "content": opening_text})
    else:
        warnings.append(
            f"{scenario.id}: no opening simulator reply was emitted for the shared history; "
            f"observed {_describe_non_ai_events(opening_events)}"
        )
    return root.session_id


def _sync_shared_history(
    *,
    client: APIClient,
    scenario: Scenario,
    npc_hid: str,
    api_key: str,
    regenerate_parent_session: bool,
    warnings: list[str],
) -> str | None:
    """Ensure saved history and parent session end on the same turn boundary."""
    history = list(scenario.conversation_history or [])
    last_role = _history_last_role(history)

    if not history:
        return _bootstrap_empty_history(
            client=client,
            scenario=scenario,
            npc_hid=npc_hid,
            api_key=api_key,
            warnings=warnings,
        )

    try:
        _validate_parent_session(client=client, scenario=scenario, api_key=api_key)
    except ParentSessionMissingError:
        if not regenerate_parent_session:
            raise
        _rebuild_parent_session(
            client=client,
            scenario=scenario,
            npc_hid=npc_hid,
            api_key=api_key,
        )

    if last_role == "user":
        parent = _resume_parent_run(client=client, scenario=scenario, api_key=api_key)
        response_text, step_events = _step_and_capture_events(parent, str(history[-1].get("content", "")))
        if response_text is None:
            warnings.append(
                f"{scenario.id}: no simulator reply was emitted for the trailing shared-history player turn; "
                f"observed {_describe_non_ai_events(step_events)}"
            )
        else:
            scenario.conversation_history.append({"role": "assistant", "content": response_text})

    return scenario.parent_session_id


async def _run_scenario_async(
    path: Path,
    scenario_file: ScenarioFile,
    group_idx: int,
    scenario_idx: int,
    run_attempts: bool,
    regenerate_parent_session: bool,
    server_url: str,
    api_key: str,
    lock: asyncio.Lock,
) -> list[str]:
    """Sync shared history and optionally run pending attempts for one scenario."""

    def _sync_run() -> tuple[list[dict], str | None, list[tuple[int, str | None, SimulatorResponseType | None, list[dict[str, str]]]], list[str]]:
        scenario = scenario_file.scenario_groups[group_idx].scenarios[scenario_idx]
        warnings: list[str] = []

        with APIClient(url=server_url, api_key=api_key) as client:
            parent_session_id = _sync_shared_history(
                client=client,
                scenario=scenario,
                npc_hid=scenario_file.npc_hid,
                api_key=api_key,
                regenerate_parent_session=regenerate_parent_session,
                warnings=warnings,
            )

            responses: list[tuple[int, str | None, SimulatorResponseType | None, list[dict[str, str]]]] = []
            if run_attempts and _history_last_role(scenario.conversation_history) == "assistant" and parent_session_id:
                for a_idx, attempt in enumerate(scenario.attempts):
                    if attempt.simulator_response is not None:
                        continue
                    branch = client.branch_session(parent_session_id, api_key=api_key or None)
                    _ai_response_text, step_events = _step_and_capture_events(branch, attempt.player_message)
                    response_text, response_type, extra_events = _select_attempt_response(step_events)
                    if response_text is None:
                        warnings.append(
                            _no_ai_warning(
                                scenario_id=scenario.id,
                                attempt_idx=a_idx,
                                branch=branch,
                                events=step_events,
                            )
                        )
                    responses.append((a_idx, response_text, response_type, extra_events))

        return scenario.conversation_history, scenario.parent_session_id, responses, warnings

    shared_history, parent_session_id, attempt_responses, warnings = await asyncio.to_thread(_sync_run)

    async with lock:
        sf = load_scenario_file(path)
        scenario = sf.scenario_groups[group_idx].scenarios[scenario_idx]
        scenario.conversation_history = shared_history
        scenario.parent_session_id = parent_session_id

        for a_idx, response_text, response_type, extra_events in attempt_responses:
            if response_text is not None:
                scenario.attempts[a_idx].simulator_response = response_text
                scenario.attempts[a_idx].simulator_response_type = response_type
                scenario.attempts[a_idx].simulator_extra_events = extra_events

        save_scenario_file(path, sf)

    return warnings


async def generate_responses(
    path: Path,
    *,
    server_url: str = "http://localhost:8080",
    api_key: str = "",
    only: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude: list[str] | None = None,
    concurrency: int = 4,
    run_attempts: bool = True,
    regenerate_parent_session: bool = False,
    console,
) -> None:
    """Sync shared history and optionally generate simulator responses for attempts."""
    scenario_file = load_scenario_file(path)
    selected = _selected_scenarios(
        scenario_file,
        only=only,
        include_ids=include_ids,
        exclude=exclude,
    )

    if not selected:
        console.print("[success]No matching scenarios selected.[/success]")
        return

    total_attempts = sum(
        1
        for g_idx, s_idx in selected
        for attempt in scenario_file.scenario_groups[g_idx].scenarios[s_idx].attempts
        if attempt.simulator_response is None
    )
    action = "Synchronizing shared history only" if not run_attempts else "Synchronizing history and generating responses"
    console.print(
        f"{action} for [bold]{len(selected)}[/bold] scenario(s)"
        + (f" with [bold]{total_attempts}[/bold] pending attempt(s)..." if run_attempts else "...")
    )

    lock = asyncio.Lock()
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(g_idx: int, s_idx: int):
        sid = scenario_file.scenario_groups[g_idx].scenarios[s_idx].id
        async with sem:
            try:
                warnings = await _run_scenario_async(
                    path=path,
                    scenario_file=scenario_file,
                    group_idx=g_idx,
                    scenario_idx=s_idx,
                    run_attempts=run_attempts,
                    regenerate_parent_session=regenerate_parent_session,
                    server_url=server_url,
                    api_key=api_key,
                    lock=lock,
                )
                return sid, None, warnings
            except Exception as exc:  # noqa: BLE001
                return sid, str(exc), []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running HITL update...", total=len(selected))

        async def _runner():
            results = []
            for coro in asyncio.as_completed([_bounded(g_idx, s_idx) for g_idx, s_idx in selected]):
                result = await coro
                progress.advance(task)
                results.append(result)
            return results

        results = await _runner()

    failures = [(sid, err) for sid, err, _warnings in results if err]
    if failures:
        for sid, err in failures:
            console.print(f"[error]✖ {sid}: {err}[/error]")
        raise RuntimeError(f"{len(failures)} scenario(s) failed during update")

    warnings_by_scenario: dict[str, list[str]] = defaultdict(list)
    for sid, _err, warnings in results:
        warnings_by_scenario[sid].extend(warnings)

    for sid in sorted(warnings_by_scenario):
        for warning in warnings_by_scenario[sid]:
            console.print(f"[warning]{warning}[/warning]")

    console.print("[success]✔ HITL update complete.[/success]")
