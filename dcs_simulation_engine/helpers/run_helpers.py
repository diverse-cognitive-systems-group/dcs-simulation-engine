"""Helper functions for managing CLI DCS Simulation Engine run instances."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from dcs_simulation_engine.core.constants import OUTPUT_FPATH
from dcs_simulation_engine.helpers.logging_helpers import (
    add_run_logger,
    remove_run_logger,
)
from dcs_simulation_engine.utils.paths import package_root

RUNS_FILE = package_root() / ".dcs_se_runs"
RUN_FILE = "metadata.json"

_RUN_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_RUN_NAME_LEN = 15


class STATUS(Enum):
    """Represents the lifecycle status of a run instance."""

    RUNNING = "running"  # start or resume
    STOPPED = "stopped"  # stop
    DESTROYED = "destroyed"  # archive + delete


class RunNameError(ValueError):
    """Base class for run-name validation errors."""


@dataclass(frozen=True)
class BadRunNameError(RunNameError):
    """Raised when a provided run name is invalid."""

    run_name: str

    def __str__(self) -> str:
        """Returns a message indicating that the run name is invalid and provides the rules for valid names."""
        return (
            f"Invalid run name {self.run_name!r}. "
            "Use lowercase letters or numbers separated by dashes "
            "(max length 8, e.g. 'test1', 'run-2')."
        )


@dataclass(frozen=True)
class RunNameNotUniqueError(RunNameError):
    """Raised when a run with the specified name already exists."""

    run_name: str
    status: object  # STATUS enum type if you have it

    def __str__(self) -> str:
        """Returns a message indicating that the run name is not unique and includes the existing run's status."""
        return f"Run {self.run_name!r} already exists (status={self.status})."


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
        logger.debug(f"Creating new run '{name}'")
        runs[name] = {
            "name": name,
            "link": None,
            "created_at": _now(),
            "start_times": [],  # list[float]
            "stop_times": [],  # list[float]
            "destroy_time": None,  # float|None
        }
        logger.debug(f"Adding a file sink for run '{name}'")
        run_results_dir = OUTPUT_FPATH / name
        add_run_logger(name, run_results_dir)
    return runs[name]


def _derived_status(run: Dict[str, Any]) -> STATUS:
    if run.get("destroy_time") is not None:
        return STATUS.DESTROYED
    starts = run.get("start_times") or []
    stops = run.get("stop_times") or []
    return STATUS.RUNNING if len(starts) > len(stops) else STATUS.STOPPED


def validate_run_name(run_name: Optional[str]) -> str:
    """Validate and normalize run name.

    Rules:
    - lowercase letters or numbers
    - dash separated segments
    - max length 8
    """
    if run_name is None:
        raise BadRunNameError("")

    v = run_name.strip()

    if len(v) > MAX_RUN_NAME_LEN:
        raise BadRunNameError(v)

    if not _RUN_NAME_RE.fullmatch(v):
        raise BadRunNameError(v)

    return v


def load_runs() -> Dict[str, Dict[str, Any]]:
    """Returns a dict of run_name -> run_metadata."""
    if not RUNS_FILE.exists():
        return {}
    with open(RUNS_FILE, "r") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def ensure_run_name_unique(run_name: str):
    """Raise if a run with this name already exists."""
    status = run_status(run_name)
    if status is not None:
        raise RunNameNotUniqueError(run_name=run_name, status=status)
    return True


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
        raise InvalidRunTransitionError(f"Run '{name}' is destroyed; cannot transition to {status.value}")

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
        remove_run_logger(name)
        return STATUS.DESTROYED

    raise ValueError(f"Unsupported status: {status}")


def _archive_and_delete(runs: Dict[str, Dict[str, Any]], name: str, run: Dict[str, Any]) -> None:
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
