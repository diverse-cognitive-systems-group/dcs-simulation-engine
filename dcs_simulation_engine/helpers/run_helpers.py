"""Helper functions for managing CLI DCS Simulation Engine run instances."""

import json
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from dcs_simulation_engine.core.constants import OUTPUT_FPATH

RUNS_FILE = Path.home() / ".dcs_se_runs"
RUN_FILE = "run-metadata.json"


class STATUS(Enum):
    """Represents the lifecycle status of a run instance."""

    RUNNING = "running"  # start or resume
    STOPPED = "stopped"  # stop
    DESTROYED = "destroyed"  # archive + delete


class RunNotFoundError(Exception):
    """Raised when a run with the specified name is not found."""

    pass


class InvalidRunTransitionError(Exception):
    """Raised when an invalid status transition is attempted on a run."""

    pass


def _now() -> float:
    return time.time()


def _save_runs(runs: Dict[str, Dict[str, Any]]) -> None:
    RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = RUNS_FILE.with_suffix(RUNS_FILE.suffix + ".tmp")
    with open(tmp, "w") as f:
        json.dump(runs, f, indent=2, sort_keys=True)
    tmp.replace(RUNS_FILE)


def _ensure_run(runs: Dict[str, Dict[str, Any]], name: str) -> Dict[str, Any]:
    if name not in runs:
        runs[name] = {
            "name": name,
            "link": None,
            "created_at": _now(),
            "start_times": [],  # list[float]
            "stop_times": [],  # list[float]
            "destroy_time": None,  # float|None
        }
    return runs[name]


def _derived_status(run: Dict[str, Any]) -> STATUS:
    if run.get("destroy_time") is not None:
        return STATUS.DESTROYED
    starts = run.get("start_times") or []
    stops = run.get("stop_times") or []
    return STATUS.RUNNING if len(starts) > len(stops) else STATUS.STOPPED


def load_runs() -> Dict[str, Dict[str, Any]]:
    """Returns a dict of run_name -> run_metadata."""
    if not RUNS_FILE.exists():
        return {}
    with open(RUNS_FILE, "r") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def run_status(name: str) -> STATUS:
    """Returns the current STATUS of the run with the given name."""
    runs = load_runs()
    if name not in runs:
        raise RunNotFoundError(f"Run '{name}' not found.")
    return _derived_status(runs[name])


def update_run(name: str, status: STATUS, link: Optional[str] = None) -> STATUS:
    """Creates the run if missing, otherwise updates it.

    Semantics:
      - RUNNING: if currently stopped -> append a new start time
                 if currently running -> no-op
      - STOPPED: if currently running -> append a stop time
                 if currently stopped -> no-op
      - DESTROYED: set destroy_time, write results/<name>/run.json, remove from dotfile

    Returns resulting STATUS.
    """
    runs = load_runs()
    run = _ensure_run(runs, name)

    if link is not None:
        run["link"] = link

    if run.get("destroy_time") is not None:
        if status == STATUS.DESTROYED:
            _archive_and_delete(runs, name, run)  # idempotent-ish
            return STATUS.DESTROYED
        raise InvalidRunTransitionError(
            f"Run '{name}' is destroyed; cannot transition to {status.value}"
        )

    current = _derived_status(run)

    if status == STATUS.RUNNING:
        if current == STATUS.STOPPED:
            run["start_times"].append(_now())
        # if already running: no-op
        runs[name] = run
        _save_runs(runs)
        return _derived_status(run)

    if status == STATUS.STOPPED:
        if current == STATUS.RUNNING:
            run["stop_times"].append(_now())
        # if already stopped: no-op
        runs[name] = run
        _save_runs(runs)
        return _derived_status(run)

    if status == STATUS.DESTROYED:
        run["destroy_time"] = _now()
        _archive_and_delete(runs, name, run)
        return STATUS.DESTROYED

    raise ValueError(f"Unsupported status: {status}")


def _archive_and_delete(
    runs: Dict[str, Dict[str, Any]], name: str, run: Dict[str, Any]
) -> None:
    results_dir = OUTPUT_FPATH / name
    results_dir.mkdir(parents=True, exist_ok=True)
    with open(results_dir / RUN_FILE, "w") as f:
        json.dump(run, f, indent=2, sort_keys=True)

    if name in runs:
        del runs[name]
    _save_runs(runs)


def _format_duration(seconds: float) -> str:
    seconds = int(seconds)

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    if days:
        return f"{days}d"
    if hours:
        return f"{hours}h"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def run_uptime(
    name: str,
    *,
    all_segments: bool = False,
    include_current: bool = True,
    format: bool = False,
) -> Union[float, str, List[float], List[str]]:
    """Returns uptime(s).

    - all_segments=False (default):
        returns the latest segment uptime.
        If include_current=True and the run is running, latest is (now - last_start).
        If the run has never started, returns 0.0.

    - all_segments=True:
        returns a list of uptimes for each start/stop segment.
        If include_current=True and the run is running, includes the current running segment.

    - format=True:
        returns compact strings like '6d', '3h', '12m', '45s'.
    """
    runs = load_runs()
    if name not in runs:
        raise RunNotFoundError(f"Run '{name}' not found")

    run = runs[name]
    starts: List[float] = list(run.get("start_times") or [])
    stops: List[float] = list(run.get("stop_times") or [])

    segs: List[float] = []
    pair_count = min(len(starts), len(stops))
    for i in range(pair_count):
        segs.append(max(0.0, stops[i] - starts[i]))

    is_running = len(starts) > len(stops)
    if include_current and is_running and starts:
        segs.append(max(0.0, _now() - starts[-1]))

    if all_segments:
        return [_format_duration(s) for s in segs] if format else segs

    latest = segs[-1] if segs else 0.0
    return _format_duration(latest) if format else latest


def local_run_name(patterns: Optional[List[str]] = None) -> Optional[str]:
    """Return the run name whose link points to a local address.

    Matches substrings like 'localhost', '127.0.0.1', or any custom patterns.
    Returns None if no such run exists.
    """
    runs = load_runs()
    if not runs:
        return None

    pats = [p.lower() for p in (patterns or ["localhost", "127.0.0.1"])]

    for name, run in runs.items():
        link = run.get("link")
        if not isinstance(link, str):
            continue
        link_l = link.lower()
        if any(p in link_l for p in pats):
            return name

    return None
