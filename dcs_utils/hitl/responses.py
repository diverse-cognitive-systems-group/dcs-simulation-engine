"""Async simulator response generation for HITL scenarios.

For each scenario attempt that lacks a simulator_response, calls the DCS
engine via APIClient, captures the simulator output, and writes back to the
scenarios file. For fresh scenarios, the saved conversation history begins
with the simulator's opening scene, followed by alternating player/simulator
turns.

Current implementation status
------------------------------
Only scenarios with an **empty** conversation_history are fully supported.
For these, the engine starts a fresh session and generates an opening scene
automatically.

Scenarios with a non-empty conversation_history (mid-conversation resumes)
are not yet implemented: the DCS server does not currently support injecting
an arbitrary conversation history into a new session via ``start_game``.
A ``TODO`` comment below marks exactly where that support should be added
once the server exposes a ``context`` parameter on ``CreateGameRequest``.
"""

import asyncio
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.api.models import CreateGameRequest
from dcs_utils.hitl import Attempt, ScenarioFile
from dcs_utils.hitl.generate import load_scenario_file, save_scenario_file


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _pending_work(
    scenario_file: ScenarioFile,
    *,
    only: list[str] | None,
    include_ids: list[str] | None,
    exclude: list[str] | None,
) -> list[tuple[int, int, int]]:
    """Return (group_idx, scenario_idx, attempt_idx) triples for pending attempts.

    An attempt is *pending* when ``simulator_response`` is ``None``.
    Eligibility also depends on the scenario's conversation_history state:

    * Empty history → eligible
    * Non-empty history → NOT YET IMPLEMENTED (skipped with a warning printed
      by the caller)

    Filtering is applied via ``only``, ``include_ids``, and ``exclude`` on
    scenario IDs following the same semantics as the ``--only / --include /
    --exclude`` flags.
    """
    pending: list[tuple[int, int, int]] = []
    for g_idx, group in enumerate(scenario_file.scenario_groups):
        for s_idx, scenario in enumerate(group.scenarios):
            sid = scenario.id

            # Apply --only filter: if set, include ONLY these IDs (unless --include overrides)
            if only and sid not in only:
                if not include_ids or sid not in include_ids:
                    continue

            # Apply --exclude filter
            if exclude and sid in exclude:
                continue

            # Apply --include: ensure these are always processed even if excluded
            # (already handled above by checking include_ids inside the only block)

            history = scenario.conversation_history
            has_content = bool(history)

            for a_idx, attempt in enumerate(scenario.attempts):
                if attempt.simulator_response is not None:
                    continue  # already generated

                if not has_content:
                    pending.append((g_idx, s_idx, a_idx))
                else:
                    # Non-empty history: not yet implemented.  Caller warns.
                    pass

    return pending


async def _run_scenario_async(
    path: Path,
    scenario_file: ScenarioFile,
    group_idx: int,
    scenario_idx: int,
    attempt_indices: list[int],
    server_url: str,
    api_key: str,
    lock: asyncio.Lock,
) -> list[str]:
    """Run one scenario session in a thread and return simulator responses.

    All APIClient calls are synchronous (websocket-based), so we offload to
    a thread via ``asyncio.to_thread`` to allow concurrency.
    """

    def _sync_run() -> tuple[list[dict[str, str]], list[str]]:
        scenario = scenario_file.scenario_groups[group_idx].scenarios[scenario_idx]
        generated_history: list[dict[str, str]] = []
        responses: list[str] = []

        with APIClient(url=server_url, api_key=api_key) as client:
            run = client.start_game(
                CreateGameRequest(
                    game=scenario.game,
                    pc_choice=scenario.pc_hid,
                    npc_choice=scenario_file.npc_hid,
                    api_key=api_key or None,
                    # TODO: Once the server supports context injection, pass
                    # scenario.conversation_history here so the session starts
                    # from a seeded state rather than a fresh opening scene.
                    # This requires a `context` parameter on CreateGameRequest
                    # and corresponding server-side handling in the session
                    # initialisation path (see SessionManager.create_async).
                    # Until then, the engine generates its own opening scene.
                )
            )

            with run:
                # Consume the engine's opening turn.  We capture its content
                # so we can store it in conversation_history later.
                run.step("")
                opening_content = run.simulator_output or ""
                if opening_content:
                    generated_history.append(
                        {"role": "assistant", "content": opening_content}
                    )

                for a_idx in attempt_indices:
                    attempt: Attempt = scenario.attempts[a_idx]
                    run.step(attempt.player_message)
                    response_text = run.simulator_output or ""
                    generated_history.extend(
                        [
                            {"role": "user", "content": attempt.player_message},
                            {"role": "assistant", "content": response_text},
                        ]
                    )
                    responses.append(response_text)

        return generated_history, responses

    generated_history, attempt_responses = await asyncio.to_thread(_sync_run)

    # Write results back under the lock so concurrent tasks don't clobber each other.
    async with lock:
        sf = load_scenario_file(path)  # reload latest state
        scenario = sf.scenario_groups[group_idx].scenarios[scenario_idx]

        # Populate conversation_history with the generated transcript when the
        # scenario started empty.
        if not scenario.conversation_history and generated_history:
            scenario.conversation_history.extend(generated_history)

        for resp, a_idx in zip(attempt_responses, attempt_indices):
            scenario.attempts[a_idx].simulator_response = resp

        save_scenario_file(path, sf)

    return attempt_responses


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def generate_responses(
    path: Path,
    *,
    server_url: str = "http://localhost:8080",
    api_key: str = "",
    only: list[str] | None = None,
    include_ids: list[str] | None = None,
    exclude: list[str] | None = None,
    concurrency: int = 4,
    console,
) -> None:
    """Generate simulator responses for all pending scenario attempts.

    Args:
        path: Path to the ``<hid>-scenarios.json`` file.
        server_url: Base URL of the running DCS server.
        api_key: API key for the DCS server.
        only: If set, process ONLY scenarios with these IDs.
        include_ids: Force-include these scenario IDs even when ``only`` is set.
        exclude: Skip scenarios with these IDs.
        concurrency: Maximum number of parallel scenario requests.
        console: Rich Console for output.
    """
    scenario_file = load_scenario_file(path)

    # Collect pending work
    pending = _pending_work(
        scenario_file,
        only=only,
        include_ids=include_ids,
        exclude=exclude,
    )

    # Count skipped non-empty-history scenarios (not yet implemented)
    skipped_resume: list[str] = []
    for group in scenario_file.scenario_groups:
        for scenario in group.scenarios:
            if scenario.conversation_history:
                has_pending = any(a.simulator_response is None for a in scenario.attempts)
                if has_pending:
                    skipped_resume.append(scenario.id)

    if skipped_resume:
        console.print(
            f"[warning]⚠ Skipping {len(skipped_resume)} scenario(s) with existing "
            f"conversation history — resuming mid-game is not yet implemented.[/warning]"
        )

    if not pending:
        console.print("[success]All responses already generated.[/success]")
        return

    # Group pending triples by (group_idx, scenario_idx) so we process all
    # attempts for a scenario in one session.
    from collections import defaultdict
    by_scenario: dict[tuple[int, int], list[int]] = defaultdict(list)
    for g_idx, s_idx, a_idx in pending:
        by_scenario[(g_idx, s_idx)].append(a_idx)

    total_attempts = sum(len(v) for v in by_scenario.values())
    console.print(
        f"Generating responses for [bold]{total_attempts}[/bold] attempt(s) "
        f"across [bold]{len(by_scenario)}[/bold] scenario(s)..."
    )

    lock = asyncio.Lock()
    sem = asyncio.Semaphore(concurrency)

    async def _bounded(g_idx, s_idx, attempt_indices):
        sid = scenario_file.scenario_groups[g_idx].scenarios[s_idx].id
        async with sem:
            try:
                await _run_scenario_async(
                    path=path,
                    scenario_file=scenario_file,
                    group_idx=g_idx,
                    scenario_idx=s_idx,
                    attempt_indices=attempt_indices,
                    server_url=server_url,
                    api_key=api_key,
                    lock=lock,
                )
                return sid, None
            except Exception as exc:
                return sid, exc

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        tasks = {}
        for (g_idx, s_idx), a_idxs in by_scenario.items():
            sid = scenario_file.scenario_groups[g_idx].scenarios[s_idx].id
            task_id = progress.add_task(f"[dim]{sid}[/dim]", total=None)
            tasks[(g_idx, s_idx)] = task_id

        coros = [
            _bounded(g_idx, s_idx, a_idxs)
            for (g_idx, s_idx), a_idxs in by_scenario.items()
        ]
        results = await asyncio.gather(*coros)

    errors = [(sid, exc) for sid, exc in results if exc is not None]
    successes = len(results) - len(errors)

    console.print(f"[success]✔[/success] {successes} scenario(s) completed.", style="dim")
    for sid, exc in errors:
        console.print(f"[error]✗ {sid}: {exc}[/error]")
