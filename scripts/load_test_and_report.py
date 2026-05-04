#!/usr/bin/env python3
"""Run a DCS load test and publish the system-performance report.

Usage:
    uv run python scripts/load_test_and_report.py
    uv run python scripts/load_test_and_report.py --clients 1 --games 1 --turns 1

Prerequisites:
    Start the DCS engine separately with shutdown dumping enabled, for example
    through the compose flow that runs `dcs server --dump ./runs`.

Workflow:
    1. This script runs load-test clients against the already-running engine.
    2. When the load test finishes, stop/close the engine.
    3. The engine writes its standard results export to runs/<timestamp>.
    4. This script runs:
       dcs report results runs/<timestamp> --only system-performance \
           --title "Load Test Results Report" \
           --report-path docs/reports/load_test_results_report.html
"""

import asyncio
import concurrent.futures
import json
import multiprocessing as mp
import random
import re
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import typer
from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.api.models import (
    CreateGameRequest,
    GameSetupOptionsResponse,
    RegistrationRequest,
    WSAdvanceRequest,
    WSAuthRequest,
    WSCloseRequest,
    WSClosedFrame,
    WSErrorFrame,
    WSEventFrame,
    WSSessionMetaFrame,
    WSTurnEndFrame,
)
from dcs_simulation_engine.errors import APIRequestError
from websockets.asyncio.client import connect

VALID_PC_ACTIONS = (
    "I look around the room.",
    "I wave and say hello.",
    "I wait and listen.",
    "I ask what is happening.",
    "I take a slow step forward.",
    "I check the nearest door.",
    "I look at the other person.",
    "I ask if they need help.",
    "I stand still and observe.",
    "I point to the object nearby.",
)


@dataclass
class GameResult:
    """Result for one attempted game run."""

    client_id: int
    game_number: int
    game: str
    success: bool
    game_duration_ms: float
    wait_samples: list[dict[str, Any]]
    turns: int
    session_id: str | None = None
    error: str | None = None


@dataclass
class ClientResult:
    """Aggregate results for one client."""

    client_id: int
    player_id: str | None = None
    attempted_games: int = 0
    completed_games: int = 0
    game_results: list[GameResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _ws_url(base_url: str, session_id: str) -> str:
    """Build websocket URL for a session id."""
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return f"{scheme}://{parsed.netloc}/api/play/game/{quote(session_id, safe='')}/ws"


async def _recv_json(ws: Any) -> dict[str, Any]:
    """Receive one raw JSON websocket frame."""
    raw = await ws.recv()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    if not isinstance(raw, str):
        raise RuntimeError("Expected text websocket frame")
    frame = json.loads(raw)
    if not isinstance(frame, dict):
        raise RuntimeError("Expected JSON object frame")
    return frame


async def _recv_frame(ws: Any) -> WSEventFrame | WSSessionMetaFrame | WSTurnEndFrame | WSClosedFrame:
    """Receive and parse one typed websocket frame."""
    frame = await _recv_json(ws)
    frame_type = frame.get("type")
    if frame_type == "error":
        error = WSErrorFrame.model_validate(frame)
        raise RuntimeError(f"Server error: {error.detail}")
    if frame_type == "event":
        return WSEventFrame.model_validate(frame)
    if frame_type == "session_meta":
        return WSSessionMetaFrame.model_validate(frame)
    if frame_type == "turn_end":
        return WSTurnEndFrame.model_validate(frame)
    if frame_type == "closed":
        return WSClosedFrame.model_validate(frame)
    raise RuntimeError(f"Unexpected websocket frame type: {frame_type!r}")


async def _recv_until_turn_end(ws: Any) -> tuple[list[WSEventFrame], WSTurnEndFrame | WSClosedFrame]:
    """Consume event frames until turn_end/closed."""
    events: list[WSEventFrame] = []
    while True:
        frame = await _recv_frame(ws)
        if isinstance(frame, WSSessionMetaFrame):
            continue
        if isinstance(frame, WSEventFrame):
            events.append(frame)
            continue
        return events, frame


async def _wait_for_server(base_url: str, timeout_s: float = 20.0) -> None:
    """Poll /healthz until the target server is accepting requests."""
    start = time.monotonic()
    last_error: str | None = None
    async with httpx.AsyncClient(base_url=base_url, timeout=2.0) as client:
        while time.monotonic() - start < timeout_s:
            try:
                resp = await client.get("/healthz")
                if resp.status_code == 200:
                    return
                last_error = f"healthz returned {resp.status_code}"
            except Exception as exc:  # noqa: BLE001 - startup race expected
                last_error = str(exc)
            await asyncio.sleep(0.1)
    raise RuntimeError(f"Server did not become ready within {timeout_s}s ({last_error})")


def _find_playable_setup(
    *,
    api: APIClient,
    game_names: list[str],
    api_key: str,
    forced_game: str | None,
) -> tuple[str, str, str]:
    """Find a game setup the player can start and return game/pc/npc choices."""
    candidates = [forced_game] if forced_game else random.sample(game_names, len(game_names))
    diagnostics: list[str] = []
    for game_name in candidates:
        try:
            setup: GameSetupOptionsResponse = api.setup_options(game_name=game_name, api_key=api_key)
        except APIRequestError as exc:
            diagnostics.append(f"{game_name}: {exc}")
            continue
        pcs = setup.pcs
        npcs = setup.npcs
        if not setup.can_start or not pcs or not npcs:
            diagnostics.append(
                f"{game_name}: can_start={setup.can_start} denial_reason={setup.denial_reason} pcs={len(pcs)} npcs={len(npcs)}"
            )
            continue
        if "NA" not in {pc.hid for pc in pcs}:
            diagnostics.append(f"{game_name}: NA is not an allowed pc_choice")
            continue
        return game_name, "NA", random.choice(npcs).hid
    detail = "; ".join(diagnostics) if diagnostics else "no setup diagnostics available"
    raise RuntimeError(f"No playable game setup found for this client ({detail})")


def _create_session(
    *,
    base_url: str,
    api_key: str,
    game_names: list[str],
    forced_game: str | None,
) -> tuple[str, str]:
    """Create one playable session and return (game_name, session_id)."""
    with APIClient(url=base_url, api_key=api_key, timeout=60.0) as api:
        game_name, pc_choice, npc_choice = _find_playable_setup(
            api=api,
            game_names=game_names,
            api_key=api_key,
            forced_game=forced_game,
        )
        run = api.start_game(
            CreateGameRequest(
                api_key=api_key,
                game=game_name,
                pc_choice=pc_choice,
                npc_choice=npc_choice,
                source="manual-load-test",
            )
        )
        return game_name, run.session_id


async def _play_single_game(
    *,
    client_id: int,
    game_index: int,
    base_url: str,
    api_key: str,
    game_names: list[str],
    n_turns: int,
    forced_game: str | None,
) -> GameResult:
    """Create one session, run opening + N turns over WS, then close."""
    game_name, session_id = await asyncio.to_thread(
        _create_session,
        base_url=base_url,
        api_key=api_key,
        game_names=game_names,
        forced_game=forced_game,
    )

    start_ns = time.perf_counter_ns()
    turns_seen = 0
    wait_samples: list[dict[str, Any]] = []
    ws_url = _ws_url(base_url, session_id)
    async with connect(ws_url) as ws:
        await ws.send(WSAuthRequest(type="auth", api_key=api_key).model_dump_json())

        wait_start_ns = time.perf_counter_ns()
        _, opening_end = await _recv_until_turn_end(ws)
        wait_samples.append(
            {
                "phase": "opening",
                "duration_ms": (time.perf_counter_ns() - wait_start_ns) / 1_000_000,
                "turn_index": 0,
            }
        )
        if isinstance(opening_end, WSTurnEndFrame):
            turns_seen = opening_end.turns
        else:
            raise RuntimeError("Session closed before first turn completed")

        for turn_idx in range(n_turns):
            action = random.choice(VALID_PC_ACTIONS)
            await ws.send(WSAdvanceRequest(type="advance", text=action).model_dump_json())
            wait_start_ns = time.perf_counter_ns()
            _, turn_end = await _recv_until_turn_end(ws)
            wait_samples.append(
                {
                    "phase": "turn",
                    "duration_ms": (time.perf_counter_ns() - wait_start_ns) / 1_000_000,
                    "turn_index": turn_idx + 1,
                }
            )
            if isinstance(turn_end, WSClosedFrame):
                break
            turns_seen = turn_end.turns
            if turn_end.exited:
                break

        await ws.send(WSCloseRequest(type="close").model_dump_json())
        wait_start_ns = time.perf_counter_ns()
        closed = await _recv_frame(ws)
        wait_samples.append(
            {
                "phase": "close",
                "duration_ms": (time.perf_counter_ns() - wait_start_ns) / 1_000_000,
                "turn_index": turns_seen,
            }
        )
        if not isinstance(closed, WSClosedFrame):
            raise RuntimeError(f"Expected closed frame, got: {closed}")

    game_duration_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
    return GameResult(
        client_id=client_id,
        game_number=game_index + 1,
        game=game_name,
        success=True,
        game_duration_ms=game_duration_ms,
        wait_samples=wait_samples,
        turns=turns_seen,
        session_id=session_id,
    )


async def run_client(
    client_id: int,
    *,
    base_url: str,
    n_games: int,
    n_turns: int,
    forced_game: str | None,
) -> ClientResult:
    """Run full lifecycle for one client: register, auth, then play N games concurrently."""
    result = ClientResult(client_id=client_id)

    email = f"load-{client_id}-{uuid.uuid4().hex[:10]}@example.com"
    with APIClient(url=base_url, timeout=60.0) as api:
        reg_resp = api.register_player(
            RegistrationRequest(
                full_name=f"Load Tester {client_id}",
                email=email,
                phone_number=f"+1 555 {1000 + client_id:04d}",
            )
        )
        api_key = reg_resp.api_key
        result.player_id = reg_resp.player_id

        _ = api.auth(api_key=api_key)

        if forced_game:
            game_names = [forced_game]
        else:
            games_resp = api.list_games()
            game_names = [game.name for game in games_resp.games]
            if not game_names:
                raise RuntimeError("No games returned by /api/games/list")

    async def _play_one(game_index: int) -> GameResult:
        try:
            return await _play_single_game(
                client_id=client_id,
                game_index=game_index,
                base_url=base_url,
                api_key=api_key,
                game_names=game_names,
                n_turns=n_turns,
                forced_game=forced_game,
            )
        except Exception as exc:  # noqa: BLE001 - load test should keep running
            msg = f"client {client_id} game {game_index + 1}: {exc}"
            result.errors.append(msg)
            return GameResult(
                client_id=client_id,
                game_number=game_index + 1,
                game=forced_game or "<auto>",
                success=False,
                game_duration_ms=0.0,
                wait_samples=[],
                turns=0,
                session_id=None,
                error=str(exc),
            )

    result.attempted_games = n_games
    game_results = await asyncio.gather(*(_play_one(game_index) for game_index in range(n_games)))
    result.game_results.extend(game_results)
    result.completed_games = sum(1 for gr in game_results if gr.success)

    return result


def _run_client_process(
    client_id: int,
    base_url: str,
    n_games: int,
    n_turns: int,
    forced_game: str | None,
) -> ClientResult:
    """Client process entrypoint."""
    return asyncio.run(
        run_client(
            client_id=client_id,
            base_url=base_url,
            n_games=n_games,
            n_turns=n_turns,
            forced_game=forced_game,
        )
    )


def run_load_test(
    *,
    n_clients: int,
    base_url: str,
    n_games: int,
    n_turns: int,
    forced_game: str | None,
) -> list[ClientResult]:
    """Execute all clients concurrently in separate processes."""
    ctx = mp.get_context("spawn")
    results: list[ClientResult] = []
    print(
        f"Starting load test: clients={n_clients}, games/client={n_games}, turns/game={n_turns}, base_url={base_url}",
        flush=True,
    )
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_clients, mp_context=ctx) as pool:
        futures = [pool.submit(_run_client_process, i, base_url, n_games, n_turns, forced_game) for i in range(n_clients)]
        pending = set(futures)
        started = time.monotonic()
        while pending:
            done, pending = concurrent.futures.wait(
                pending,
                timeout=5.0,
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for fut in done:
                results.append(fut.result())
            elapsed_s = time.monotonic() - started
            completed_games = sum(result.completed_games for result in results)
            errors = sum(len(result.errors) for result in results)
            print(
                "Load test running: "
                f"clients_done={len(results)}/{n_clients}, "
                f"games_completed={completed_games}/{n_clients * n_games}, "
                f"errors={errors}, elapsed={elapsed_s:.1f}s",
                flush=True,
            )
    return sorted(results, key=lambda r: r.client_id)


def _print_summary(results: list[ClientResult], elapsed_s: float) -> None:
    """Print aggregate and per-client load test stats."""
    game_results = [gr for client in results for gr in client.game_results]
    successful = [gr for gr in game_results if gr.success]
    failed = [gr for gr in game_results if not gr.success]
    durations_ms = [gr.game_duration_ms for gr in successful]
    wait_samples = [sample for gr in successful for sample in gr.wait_samples]
    wait_samples_ms = [float(sample["duration_ms"]) for sample in wait_samples]
    wait_turn_ms = [float(sample["duration_ms"]) for sample in wait_samples if sample.get("phase") == "turn"]
    wait_opening_ms = [float(sample["duration_ms"]) for sample in wait_samples if sample.get("phase") == "opening"]
    wait_close_ms = [float(sample["duration_ms"]) for sample in wait_samples if sample.get("phase") == "close"]

    print("\n=== Load Test Summary ===")
    print(f"Clients: {len(results)}")
    print(f"Wall time: {elapsed_s:.2f}s")
    print(f"Total games attempted: {len(game_results)}")
    print(f"Total games completed: {len(successful)}")
    print(f"Total game failures: {len(failed)}")

    if durations_ms:
        print(f"Per-game duration (ms): min={min(durations_ms):.3f} mean={statistics.fmean(durations_ms):.3f} max={max(durations_ms):.3f}")
    else:
        print("Per-game duration (ms): n/a")

    if wait_samples_ms:
        print(
            "Wait-for-response duration (all phases, ms): "
            f"min={min(wait_samples_ms):.3f} "
            f"mean={statistics.fmean(wait_samples_ms):.3f} "
            f"max={max(wait_samples_ms):.3f}"
        )
    else:
        print("Wait-for-response duration (ms): n/a")

    if wait_turn_ms:
        print(
            "Wait-for-response duration (turn phase, ms): "
            f"min={min(wait_turn_ms):.3f} "
            f"mean={statistics.fmean(wait_turn_ms):.3f} "
            f"max={max(wait_turn_ms):.3f}"
        )
    if wait_opening_ms:
        print(
            "Wait-for-response duration (opening phase, ms): "
            f"min={min(wait_opening_ms):.3f} "
            f"mean={statistics.fmean(wait_opening_ms):.3f} "
            f"max={max(wait_opening_ms):.3f}"
        )
    if wait_close_ms:
        print(
            "Wait-for-response duration (close phase, ms): "
            f"min={min(wait_close_ms):.3f} "
            f"mean={statistics.fmean(wait_close_ms):.3f} "
            f"max={max(wait_close_ms):.3f}"
        )

    print("\nGames per client:")
    for client in sorted(results, key=lambda r: r.client_id):
        print(f"  client {client.client_id:>3}: completed={client.completed_games}/{client.attempted_games} errors={len(client.errors)}")

    if failed:
        print("\nErrors:")
        for game in failed[:50]:
            print(f"  client {game.client_id} game {game.game_number}: {game.error}")
        if len(failed) > 50:
            print(f"  ... {len(failed) - 50} more")


_RUN_DIR_RE = re.compile(r"^\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}$")
_REQUIRED_REPORT_FILES = frozenset({"runs.json", "sessions.json", "session_events.json"})


def _timestamped_run_dirs(runs_dir: Path) -> set[Path]:
    """Return timestamped result directories currently present under runs_dir."""
    if not runs_dir.exists():
        return set()
    return {path.resolve() for path in runs_dir.iterdir() if path.is_dir() and _RUN_DIR_RE.match(path.name)}


def _is_complete_results_dir(path: Path) -> bool:
    """Return True when a run directory has the minimum files needed for reporting."""
    return all((path / name).is_file() for name in _REQUIRED_REPORT_FILES)


def _find_new_results_dir(*, runs_dir: Path, before: set[Path]) -> Path | None:
    """Find the newest complete results directory that was not present before the load test."""
    candidates = [path for path in _timestamped_run_dirs(runs_dir) - before if _is_complete_results_dir(path)]
    if not candidates:
        return None
    return max(candidates, key=lambda path: (path.stat().st_mtime, path.name))


def _wait_for_results_dir(*, runs_dir: Path, before: set[Path], timeout_s: float) -> Path:
    """Wait until the engine writes a new complete runs/<timestamp> export."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        results_dir = _find_new_results_dir(runs_dir=runs_dir, before=before)
        if results_dir is not None:
            return results_dir
        time.sleep(2.0)

    raise TimeoutError(
        f"No new complete results export appeared under {runs_dir} within {timeout_s:.0f}s. "
        "Stop/close the DCS engine so it can write runs/<timestamp>, then rerun report generation."
    )


def _successful_game_count(results: list[ClientResult]) -> int:
    """Count successful completed games across all clients."""
    return sum(1 for client in results for game_result in client.game_results if game_result.success)


def _generate_report(*, results_dir: Path, report_path: Path, title: str) -> None:
    """Run the DCS report command for the completed load-test results directory."""
    command = [
        sys.executable,
        "-m",
        "dcs_simulation_engine.cli.app",
        "report",
        "results",
        str(results_dir),
        "--only",
        "system-performance",
        "--title",
        title,
        "--report-path",
        str(report_path),
    ]
    subprocess.run(command, check=True)


async def _run(
    *,
    base_url: str,
    clients: int,
    games: int,
    turns: int,
    game: str | None,
    runs_dir: Path,
    report_path: Path,
    title: str,
    wait_timeout: float,
) -> int:
    """Run load test clients against an already-running server."""
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000
    base_url = f"http://{host}:{port}"
    runs_dir = runs_dir.resolve()
    report_path = report_path.resolve()

    before_run_dirs = _timestamped_run_dirs(runs_dir)
    try:
        await _wait_for_server(base_url)
    except RuntimeError as exc:
        print(f"DCS engine is not reachable at {base_url}.")
        print("Start it first with `uv run dcs server --dump ./runs`, then rerun this script.")
        print(f"Readiness check failed: {exc}")
        return 1

    started = time.perf_counter()
    results = run_load_test(
        n_clients=clients,
        base_url=base_url,
        n_games=games,
        n_turns=turns,
        forced_game=game,
    )
    elapsed_s = time.perf_counter() - started
    _print_summary(results, elapsed_s=elapsed_s)

    if _successful_game_count(results) == 0:
        print("\nNo games completed successfully; skipping report generation.")
        return 1

    print("\nLoad test complete.")
    print("Stop/close the DCS engine now so it writes its automatic results export to runs/<timestamp>.")
    print(f"Waiting up to {wait_timeout:.0f}s for a new export under: {runs_dir}")

    try:
        results_dir = _wait_for_results_dir(runs_dir=runs_dir, before=before_run_dirs, timeout_s=wait_timeout)
    except TimeoutError as exc:
        print(f"\n{exc}")
        return 1

    print(f"Detected results directory: {results_dir}")
    _generate_report(results_dir=results_dir, report_path=report_path, title=title)
    print(f"Report written to: {report_path}")
    return 0


def main(
    base_url: str = typer.Option("http://127.0.0.1:8000", help="Server base URL"),
    clients: int = typer.Option(10, help="Number of concurrent clients"),
    games: int = typer.Option(10, help="Max games per client"),
    turns: int = typer.Option(3, help="Advance turns per game"),
    game: str | None = typer.Option(None, help="Force a specific game name (optional)"),
    runs_dir: Path = typer.Option(Path("runs"), help="Directory where the engine writes timestamped results exports"),
    report_path: Path = typer.Option(
        Path("docs/reports/load_test_results_report.html"),
        help="Output path for the generated HTML report",
    ),
    title: str = typer.Option("Load Test Results Report", help="Report title"),
    wait_timeout: float = typer.Option(300.0, help="Seconds to wait for a new runs/<timestamp> export after the load test"),
) -> None:
    """CLI entrypoint."""
    if clients < 1 or games < 1 or turns < 0:
        raise typer.BadParameter("Invalid arguments: clients>=1, games>=1, turns>=0 required")
    if wait_timeout <= 0:
        raise typer.BadParameter("Invalid arguments: wait-timeout must be > 0")

    raise SystemExit(
        asyncio.run(
            _run(
                base_url=base_url,
                clients=clients,
                games=games,
                turns=turns,
                game=game,
                runs_dir=runs_dir,
                report_path=report_path,
                title=title,
                wait_timeout=wait_timeout,
            )
        )
    )


if __name__ == "__main__":
    typer.run(main)
