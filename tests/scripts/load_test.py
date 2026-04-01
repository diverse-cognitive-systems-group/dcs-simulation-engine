#!/usr/bin/env python3
"""Manual load test for end-to-end player registration/auth/gameplay.

This script assumes the API server is already running:
- runs each client in its own process (with async HTTP + WebSocket per client)
"""

import asyncio
import concurrent.futures
import json
import multiprocessing as mp
import random
import statistics
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
    WSTurnEndFrame,
)
from dcs_simulation_engine.errors import APIRequestError
from websockets.asyncio.client import connect

try:
    import pandas as pd
except ModuleNotFoundError as exc:
    raise SystemExit("Missing dependency: pandas. Install pandas to run load_test.py with dataframe export support.") from exc


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


async def _recv_frame(ws: Any) -> WSEventFrame | WSTurnEndFrame | WSClosedFrame:
    """Receive and parse one typed websocket frame."""
    frame = await _recv_json(ws)
    frame_type = frame.get("type")
    if frame_type == "error":
        error = WSErrorFrame.model_validate(frame)
        raise RuntimeError(f"Server error: {error.detail}")
    if frame_type == "event":
        return WSEventFrame.model_validate(frame)
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
        return game_name, random.choice(pcs).hid, random.choice(npcs).hid
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
            action = f"client={client_id} game={game_index + 1} turn={turn_idx + 1}: advance"
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
                consent_to_followup=True,
                consent_signature=f"Load Tester {client_id}",
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
    with concurrent.futures.ProcessPoolExecutor(max_workers=n_clients, mp_context=ctx) as pool:
        futures = [pool.submit(_run_client_process, i, base_url, n_games, n_turns, forced_game) for i in range(n_clients)]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
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


def _build_metrics_dataframe(results: list[ClientResult]) -> pd.DataFrame:
    """Build a flat dataframe for easy analysis ingestion.

    Rows include both metrics:
    - metric == "game_duration_ms" with one row per game result
    - metric == "wait_response_duration_ms" with one row per wait sample
    """
    rows: list[dict[str, Any]] = []
    for client in results:
        for game_result in client.game_results:
            common = {
                "client_id": game_result.client_id,
                "player_id": client.player_id,
                "game_number": game_result.game_number,
                "game": game_result.game,
                "success": game_result.success,
                "turns": game_result.turns,
                "error": game_result.error,
            }
            rows.append(
                {
                    **common,
                    "metric": "game_duration_ms",
                    "sample_index": 0,
                    "value_ms": float(game_result.game_duration_ms),
                }
            )
            for sample_idx, wait_sample in enumerate(game_result.wait_samples, start=1):
                phase = str(wait_sample.get("phase", "unknown"))
                turn_index = int(wait_sample.get("turn_index", 0))
                wait_ms = float(wait_sample.get("duration_ms", 0.0))
                rows.append(
                    {
                        **common,
                        "metric": "wait_response_duration_ms",
                        "phase": phase,
                        "turn_index": turn_index,
                        "sample_index": sample_idx,
                        "value_ms": wait_ms,
                    }
                )
    return pd.DataFrame(rows)


def _write_results_dataframe(results: list[ClientResult], out_path: Path) -> Path:
    """Write flattened metrics dataframe as CSV."""
    df = _build_metrics_dataframe(results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_path = out_path
    df.to_csv(df_path, index=False)
    print(f"Wrote metrics dataframe CSV: {df_path}")
    return df_path


async def _run(
    *,
    base_url: str,
    clients: int,
    games: int,
    turns: int,
    game: str | None,
    out: str,
) -> int:
    """Run load test clients against an already-running server."""
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8000
    base_url = f"http://{host}:{port}"

    await _wait_for_server(base_url)
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
    _write_results_dataframe(results, out_path=Path(out))
    return 0


def main(
    base_url: str = typer.Option("http://127.0.0.1:8000", help="Server base URL"),
    clients: int = typer.Option(10, help="Number of concurrent clients"),
    games: int = typer.Option(10, help="Max games per client"),
    turns: int = typer.Option(3, help="Advance turns per game"),
    game: str | None = typer.Option(None, help="Force a specific game name (optional)"),
    out: str = typer.Option("load_test_metrics.csv", help="Output CSV file path for flattened metrics"),
) -> None:
    """CLI entrypoint."""
    if clients < 1 or games < 1 or turns < 0:
        raise typer.BadParameter("Invalid arguments: clients>=1, games>=1, turns>=0 required")

    raise SystemExit(
        asyncio.run(
            _run(
                base_url=base_url,
                clients=clients,
                games=games,
                turns=turns,
                game=game,
                out=out,
            )
        )
    )


if __name__ == "__main__":
    typer.run(main)
