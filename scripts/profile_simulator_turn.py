#!/usr/bin/env python3
# ruff: noqa: D102,D103,D107
"""Profile one simulator turn with py-spy and phase timing output.

Usage:
    uv run python scripts/profile_simulator_turn.py --fake-ai

    uv run python scripts/profile_simulator_turn.py \
        --real-ai --game explore --pc NA --npc FW --turns 3

    uv run python scripts/profile_simulator_turn.py \
        --fake-ai --no-py-spy --turns 5

Configuration:
    Real AI mode loads environment variables from the repo-root .env file
    before validating runtime configuration. OPENROUTER_API_KEY can also be
    exported in the shell; shell values win over .env values.

What this produces:
    1. A py-spy profile artifact, by default in speedscope JSON format under
       profiles/. Open it at https://www.speedscope.app/ or switch to
       --format flamegraph for an SVG.
    2. A timings JSON file next to the py-spy output.
    3. A concise terminal summary of session-step, phase, and LLM-call timings.

How to read the results:
    Fake AI mode is the local-code baseline. If fake mode is fast but real mode
    is slow, latency is mostly model/network time. If fake mode is also slow,
    inspect the py-spy profile and phase timings for Python-side hotspots.

    Player validators and updater generation run concurrently during normal
    turns, so phase totals are intentionally reported as inclusive timings.
    Do not add phase rows together and expect them to equal total turn time.
"""

import argparse
import asyncio
import contextvars
import json
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.games import ai_client
from dotenv import load_dotenv
from loguru import logger

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TURN_INPUT = "I look around the room."
DEFAULT_FAKE_RESPONSE = '{"type": "ai", "content": "The simulated response arrives."}'
DEFAULT_VALIDATOR_RESPONSE = '{"pass": true, "reason": "Accepted for profiling."}'
PROFILE_EXTENSIONS = {
    "flamegraph": "svg",
    "raw": "txt",
    "speedscope": "speedscope.json",
    "chrometrace": "chrometrace.json",
}

_CURRENT_PHASE = contextvars.ContextVar("simulator_profile_phase", default="unclassified")
_CURRENT_TURN = contextvars.ContextVar("simulator_profile_turn", default="unclassified")
_CURRENT_CALL_LABEL = contextvars.ContextVar("simulator_profile_call_label", default="openrouter")


@dataclass
class TimingRecorder:
    """Collects timing records while the profile target runs."""

    records: list[dict[str, Any]] = field(default_factory=list)
    _next_index: int = 0

    def add(self, **record: Any) -> None:
        self._next_index += 1
        record["index"] = self._next_index
        self.records.append(record)

    async def measure(
        self,
        *,
        kind: str,
        label: str,
        phase: str,
        func: Callable[..., Awaitable[Any]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        start = time.perf_counter()
        status = "ok"
        try:
            return await func(*args, **kwargs)
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            status = "error"
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.add(
                kind=kind,
                label=label,
                phase=phase,
                turn=_CURRENT_TURN.get(),
                status=status,
                duration_ms=duration_ms,
            )


class SeedDataProvider:
    """Tiny provider backed by database_seeds characters for local profiling."""

    def __init__(self, characters: list[CharacterRecord]) -> None:
        self._characters = list(characters)
        self._by_hid = {record.hid: record for record in self._characters}

    async def get_characters(self, *, hid: str | None = None) -> list[CharacterRecord] | CharacterRecord:
        if hid is None:
            return list(self._characters)
        try:
            return self._by_hid[hid]
        except KeyError as exc:
            raise ValueError(f"Character with hid={hid!r} not found") from exc

    async def get_character(self, *, hid: str) -> CharacterRecord:
        result = await self.get_characters(hid=hid)
        if not isinstance(result, CharacterRecord):
            raise ValueError(f"Character with hid={hid!r} not found")
        return result

    async def list_characters(self) -> list[CharacterRecord]:
        return list(self._characters)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile a DCS simulator turn.", allow_abbrev=False)
    parser.add_argument("--game", default="explore", help="Game name understood by SessionManager.")
    parser.add_argument("--pc", default="NA", help="Player character HID.")
    parser.add_argument("--npc", default="FW", help="Non-player character HID.")
    parser.add_argument("--turns", type=int, default=1, help="Number of normal simulator turns to run after opening.")
    parser.add_argument(
        "--input",
        action="append",
        dest="inputs",
        help="Player input for a turn. Repeat to provide multiple inputs; values cycle when --turns is larger.",
    )
    parser.add_argument(
        "--seed-dir",
        type=Path,
        default=Path("database_seeds/dev"),
        help="Seed directory containing characters.json.",
    )
    parser.add_argument(
        "--fake-ai",
        action="store_false",
        dest="real_ai",
        help="Use deterministic fake AI calls. This is the default.",
    )
    parser.add_argument("--real-ai", action="store_true", help="Use real OpenRouter calls. Requires OPENROUTER_API_KEY.")
    parser.set_defaults(real_ai=False)
    parser.add_argument(
        "--fake-ai-response",
        default=DEFAULT_FAKE_RESPONSE,
        help="JSON simulator response used in fake AI mode.",
    )
    parser.add_argument("--output", type=Path, help="py-spy output path. Defaults under profiles/.")
    parser.add_argument("--timings-output", type=Path, help="Timing JSON output path. Defaults next to --output.")
    parser.add_argument(
        "--format",
        choices=sorted(PROFILE_EXTENSIONS),
        default="speedscope",
        help="py-spy output format.",
    )
    parser.add_argument("--rate", type=int, default=100, help="py-spy sampling rate.")
    parser.add_argument("--no-idle", action="store_true", help="Do not include idle/waiting stacks in py-spy output.")
    parser.add_argument("--no-py-spy", action="store_true", help="Run only the phase timings, without py-spy.")
    parser.add_argument("--verbose", action="store_true", help="Show engine logs while profiling.")
    parser.add_argument("--profile-target", action="store_true", help=argparse.SUPPRESS)
    return parser


def main() -> int:
    load_environment()
    args = build_parser().parse_args()
    if args.turns < 0:
        raise SystemExit("--turns must be >= 0")
    if args.rate < 1:
        raise SystemExit("--rate must be >= 1")

    if args.profile_target or args.no_py_spy:
        configure_logging(args)
        return asyncio.run(run_profile_target(args))
    return run_with_py_spy(args)


def load_environment() -> None:
    load_dotenv(REPO_ROOT / ".env")


def run_with_py_spy(args: argparse.Namespace) -> int:
    output = args.output or default_profile_path(args)
    timings_output = args.timings_output or default_timings_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    timings_output.parent.mkdir(parents=True, exist_ok=True)

    command = py_spy_command()
    command.extend(
        [
            "record",
            "--output",
            str(output),
            "--format",
            args.format,
            "--rate",
            str(args.rate),
        ]
    )
    if not args.no_idle:
        command.append("--idle")

    command.extend(["--", sys.executable, str(Path(__file__).resolve())])
    command.extend(child_args(args, timings_output=timings_output))

    print(f"Writing py-spy profile to {output}")
    print(f"Writing phase timings to {timings_output}")
    completed = subprocess.run(command, check=False)
    return completed.returncode


def child_args(args: argparse.Namespace, *, timings_output: Path) -> list[str]:
    values = [
        "--profile-target",
        "--game",
        args.game,
        "--pc",
        args.pc,
        "--npc",
        args.npc,
        "--turns",
        str(args.turns),
        "--seed-dir",
        str(args.seed_dir),
        "--timings-output",
        str(timings_output),
        "--format",
        args.format,
        "--rate",
        str(args.rate),
        "--fake-ai-response",
        args.fake_ai_response,
    ]
    if args.real_ai:
        values.append("--real-ai")
    if args.no_idle:
        values.append("--no-idle")
    if args.verbose:
        values.append("--verbose")
    for value in args.inputs or []:
        values.extend(["--input", value])
    return values


def py_spy_command() -> list[str]:
    direct = shutil.which("py-spy")
    if direct:
        return [direct]

    sibling = Path(sys.executable).resolve().parent / "py-spy"
    if sibling.exists():
        return [str(sibling)]

    if shutil.which("uv"):
        return ["uv", "run", "py-spy"]

    raise RuntimeError("Could not find py-spy. Try running this with `uv run python ...`.")


def configure_logging(args: argparse.Namespace) -> None:
    if args.verbose:
        return
    logger.remove()
    logger.add(sys.stderr, level="WARNING")


async def run_profile_target(args: argparse.Namespace) -> int:
    configure_ai(args)

    provider = SeedDataProvider(load_seed_characters(args.seed_dir))
    recorder = TimingRecorder()

    session = await SessionManager.create_async(
        game=args.game,
        provider=provider,
        source="profile",
        pc_choice=args.pc,
        npc_choice=args.npc,
    )
    install_timing_hooks(session, recorder)

    started_at = datetime.now(timezone.utc)
    events_by_turn: list[dict[str, Any]] = []

    opening_events = await run_timed_step(recorder, "opening", session.step_async(""))
    events_by_turn.append({"turn": "opening", "event_types": [event.get("type") for event in opening_events]})

    inputs = args.inputs or [DEFAULT_TURN_INPUT]
    for index in range(args.turns):
        turn_name = f"turn_{index + 1}"
        user_input = inputs[index % len(inputs)]
        events = await run_timed_step(recorder, turn_name, session.step_async(user_input))
        events_by_turn.append(
            {
                "turn": turn_name,
                "input": user_input,
                "event_types": [event.get("type") for event in events],
            }
        )

    payload = {
        "metadata": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "mode": "real-ai" if args.real_ai else "fake-ai",
            "game": args.game,
            "pc": args.pc,
            "npc": args.npc,
            "turns": args.turns,
            "seed_dir": str(args.seed_dir),
        },
        "events": events_by_turn,
        "timings": recorder.records,
    }

    timings_output = args.timings_output or default_timings_path(default_profile_path(args))
    timings_output.parent.mkdir(parents=True, exist_ok=True)
    timings_output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print_timing_summary(payload)
    return 0


def configure_ai(args: argparse.Namespace) -> None:
    if args.real_ai:
        ai_client.set_fake_ai_response(None)
        ai_client.validate_openrouter_configuration()
        return

    fake_response = args.fake_ai_response

    async def fake_call_openrouter(messages: list[dict[str, str]], model: str) -> str:
        if len(messages) == 1 and messages[0].get("role") == "system":
            return DEFAULT_VALIDATOR_RESPONSE
        return fake_response

    ai_client._call_openrouter = fake_call_openrouter  # type: ignore[assignment]


def install_timing_hooks(session: SessionManager, recorder: TimingRecorder) -> None:
    original_call = ai_client._call_openrouter_with_retry

    async def timed_call_openrouter_with_retry(messages: list[dict[str, str]], model: str) -> str:
        start = time.perf_counter()
        status = "ok"
        try:
            return await original_call(messages, model)
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception:
            status = "error"
            raise
        finally:
            prompt_chars = sum(len(str(message.get("content", ""))) for message in messages)
            recorder.add(
                kind="llm_call",
                label=_CURRENT_CALL_LABEL.get(),
                phase=_CURRENT_PHASE.get(),
                turn=_CURRENT_TURN.get(),
                status=status,
                duration_ms=(time.perf_counter() - start) * 1000.0,
                model=model,
                message_count=len(messages),
                prompt_chars=prompt_chars,
            )

    ai_client._call_openrouter_with_retry = timed_call_openrouter_with_retry  # type: ignore[assignment]

    engine = getattr(session.game, "_engine", None)
    if engine is None:
        return

    wrap_engine_method(recorder, engine, "chat", "opening", call_label="opener")
    wrap_engine_method(recorder, engine, "_collect_player_validation_failures", "player_validators")
    wrap_engine_method(recorder, engine, "_generate_simulator_response", "updater_generation", call_label="updater")
    wrap_engine_method(recorder, engine, "_validate_simulator_response", "simulator_validators")
    wrap_engine_method(recorder, engine, "_run_updater_with_retry", "updater_validation_and_retry")
    wrap_validator_method(recorder, engine, "_run_player_validator", phase="player_validators", fallback="player validator")
    wrap_validator_method(recorder, engine, "_run_simulator_validator", phase="simulator_validators")


def wrap_engine_method(
    recorder: TimingRecorder,
    engine: Any,
    method_name: str,
    phase: str,
    *,
    call_label: str | None = None,
) -> None:
    original = getattr(engine, method_name, None)
    if original is None:
        return

    async def timed_method(*args: Any, **kwargs: Any) -> Any:
        phase_token = _CURRENT_PHASE.set(phase)
        label_token = _CURRENT_CALL_LABEL.set(call_label) if call_label is not None else None
        try:
            return await recorder.measure(
                kind="phase",
                label=method_name,
                phase=phase,
                func=original,
                args=args,
                kwargs=kwargs,
            )
        finally:
            if label_token is not None:
                _CURRENT_CALL_LABEL.reset(label_token)
            _CURRENT_PHASE.reset(phase_token)

    setattr(engine, method_name, timed_method)


def wrap_validator_method(
    recorder: TimingRecorder,
    engine: Any,
    method_name: str,
    *,
    phase: str,
    fallback: str | None = None,
) -> None:
    original = getattr(engine, method_name, None)
    if original is None:
        return

    async def timed_method(*args: Any, **kwargs: Any) -> Any:
        label = validator_label(engine, args, kwargs, fallback=fallback)
        phase_token = _CURRENT_PHASE.set(phase)
        label_token = _CURRENT_CALL_LABEL.set(label)
        try:
            return await original(*args, **kwargs)
        finally:
            _CURRENT_CALL_LABEL.reset(label_token)
            _CURRENT_PHASE.reset(phase_token)

    setattr(engine, method_name, timed_method)


def validator_label(engine: Any, args: tuple[Any, ...], kwargs: dict[str, Any], *, fallback: str | None) -> str:
    template = str(args[0]) if args else str(kwargs.get("validator_template", ""))
    fallback_name = str(kwargs.get("fallback") or fallback or "validator")
    raw_name = engine._validator_name(template, fallback=fallback_name)
    return raw_name.split("\u2014", 1)[0].strip()


async def run_timed_step(
    recorder: TimingRecorder,
    turn_name: str,
    awaitable: Awaitable[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    token = _CURRENT_TURN.set(turn_name)
    start = time.perf_counter()
    status = "ok"
    try:
        return await awaitable
    except Exception:
        status = "error"
        raise
    finally:
        recorder.add(
            kind="session_step",
            label="SessionManager.step_async",
            phase="session",
            turn=turn_name,
            status=status,
            duration_ms=(time.perf_counter() - start) * 1000.0,
        )
        _CURRENT_TURN.reset(token)


def load_seed_characters(seed_dir: Path) -> list[CharacterRecord]:
    path = seed_dir / "characters.json"
    if not path.exists():
        raise FileNotFoundError(f"Character seed file not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected {path} to contain a JSON list")

    characters: list[CharacterRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        hid = str(item.get("hid", "")).strip()
        if not hid:
            continue
        known = {"hid", "_id", "name", "short_description"}
        characters.append(
            CharacterRecord(
                hid=hid,
                name=str(item.get("name", "")),
                short_description=str(item.get("short_description", "")),
                data={key: value for key, value in item.items() if key not in known},
            )
        )

    if not characters:
        raise ValueError(f"No characters loaded from {path}")
    return characters


def default_profile_path(args: argparse.Namespace) -> Path:
    mode = "real" if args.real_ai else "fake"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    extension = PROFILE_EXTENSIONS[args.format]
    return Path("profiles") / f"simulator-turn-{args.game}-{mode}-{timestamp}.{extension}"


def default_timings_path(profile_path: Path) -> Path:
    return profile_path.parent / f"{profile_path.stem}.timings.json"


def print_timing_summary(payload: dict[str, Any]) -> None:
    timings = payload["timings"]
    metadata = payload["metadata"]
    print()
    print(f"Simulator profile timings ({metadata['mode']}, game={metadata['game']}, pc={metadata['pc']}, npc={metadata['npc']})")
    print(
        "Architecture Note: each turn runs player validators and updater generation concurrently with fast-fail cancellation; "
        "simulator validators run after updater generation; one updater+simulator-validation retry is allowed."
    )
    print()

    opening = first_record(timings, kind="session_step", turn="opening")
    if opening is not None:
        opener_calls = records_for(timings, kind="llm_call", turn="opening", phase="opening")
        print("Opening:")
        print(f"  total={format_duration(opening['duration_ms'])} opener={call_summary(opener_calls)}")
        print_slowest_calls(opener_calls, indent="    ")
        print()

    print("Turn critical path:")
    turn_steps = [record for record in timings if record.get("kind") == "session_step" and record.get("turn") != "opening"]
    if not turn_steps:
        print("  none")
    for step in turn_steps:
        turn = str(step["turn"])
        player_phase = records_for(timings, kind="phase", turn=turn, phase="player_validators")
        updater_phase = records_for(timings, kind="phase", turn=turn, phase="updater_generation")
        simulator_phase = records_for(timings, kind="phase", turn=turn, phase="simulator_validators")

        initial_updater_ms = duration_at(updater_phase, 0)
        retry_updater_ms = sum(row["duration_ms"] for row in updater_phase[1:])
        player_wall_ms = sum(row["duration_ms"] for row in player_phase)
        simulator_wall_ms = sum(row["duration_ms"] for row in simulator_phase)
        gate_ms = max(player_wall_ms, initial_updater_ms)
        retries = max(0, len(simulator_phase) - 1)
        explained_ms = gate_ms + simulator_wall_ms + retry_updater_ms
        overhead_ms = float(step["duration_ms"]) - explained_ms

        player_calls = records_for(timings, kind="llm_call", turn=turn, phase="player_validators")
        updater_calls = records_for(timings, kind="llm_call", turn=turn, phase="updater_generation")
        simulator_calls = records_for(timings, kind="llm_call", turn=turn, phase="simulator_validators")

        print(f"  {turn}: total={format_duration(step['duration_ms'])} retries={retries}")
        print(f"    concurrent gate wall={format_duration(gate_ms)}")
        print(f"      player validators wall={format_duration(player_wall_ms)} {call_summary(player_calls)}")
        print_slowest_calls(player_calls, indent="        ")
        print(f"      updater generation wall={format_duration(initial_updater_ms)} {call_summary(updater_calls[:1])}")
        print_slowest_calls(updater_calls[:1], indent="        ")
        if retry_updater_ms:
            print(f"    retry updater generation wall={format_duration(retry_updater_ms)} {call_summary(updater_calls[1:])}")
            print_slowest_calls(updater_calls[1:], indent="      ")
        print(
            f"    simulator validators wall={format_duration(simulator_wall_ms)} "
            f"attempts={len(simulator_phase)} {call_summary(simulator_calls)}"
        )
        print_slowest_calls(simulator_calls, indent="      ")
        if abs(overhead_ms) > 50.0:
            print(f"    other session overhead={format_duration(overhead_ms)}")


def format_duration(duration_ms: float) -> str:
    return f"{duration_ms:.1f} ms ({duration_ms / 1000.0:.2f}s)"


def records_for(timings: list[dict[str, Any]], *, kind: str, turn: str, phase: str | None = None) -> list[dict[str, Any]]:
    rows = [record for record in timings if record.get("kind") == kind and record.get("turn") == turn]
    if phase is not None:
        rows = [record for record in rows if record.get("phase") == phase]
    return sorted(rows, key=lambda record: int(record.get("index", 0)))


def first_record(timings: list[dict[str, Any]], *, kind: str, turn: str, phase: str | None = None) -> dict[str, Any] | None:
    rows = records_for(timings, kind=kind, turn=turn, phase=phase)
    return rows[0] if rows else None


def duration_at(rows: list[dict[str, Any]], index: int) -> float:
    try:
        return float(rows[index]["duration_ms"])
    except IndexError:
        return 0.0


def call_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "calls=0"

    statuses: dict[str, int] = defaultdict(int)
    for row in rows:
        statuses[str(row.get("status", "unknown"))] += 1
    status_text = " ".join(f"{name}={count}" for name, count in sorted(statuses.items()))
    slowest = max(float(row["duration_ms"]) for row in rows)
    models = ", ".join(sorted({str(row.get("model")) for row in rows}))
    return f"calls={len(rows)} {status_text} slowest_call={format_duration(slowest)} models={models}"


def print_slowest_calls(rows: list[dict[str, Any]], *, indent: str, limit: int = 3) -> None:
    if not rows:
        return
    print(f"{indent}slowest calls:")
    slowest = sorted(rows, key=lambda row: float(row["duration_ms"]), reverse=True)[:limit]
    for row in slowest:
        print(
            f"{indent}  {row['label']}: {format_duration(row['duration_ms'])} "
            f"status={row.get('status')} model={row.get('model')} prompt_chars={row.get('prompt_chars')}"
        )


if __name__ == "__main__":
    raise SystemExit(main())
