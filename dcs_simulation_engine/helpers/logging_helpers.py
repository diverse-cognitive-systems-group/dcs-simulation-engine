"""Logging helpers for DI Simulation Engine."""

import sys
from pathlib import Path
from typing import Dict, Optional

from loguru import logger

_RUN_SINK_IDS: Dict[str, int] = {}


def configure_logger(source: str, quiet: bool = False, verbose: int = 0) -> None:
    """Configure Loguru logging."""
    # Clear any previously added handlers
    logger.remove()

    if quiet:
        console_level = "ERROR"
    elif verbose == 1:
        console_level = "INFO"
    elif verbose >= 2:
        console_level = "DEBUG"
    else:
        console_level = "WARNING"

    # Console handler — ERROR and above
    logger.add(
        sink=sys.stderr,
        level=console_level,
        format=("{time:YYYY-MM-DD HH:mm:ss} | {level:^7} | {file.name}:{line} | {message}"),
    )

    # File handler — DEBUG+, rotated daily, keep 7 days, zipped
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    log_path = logs_dir / f"{source}_{'{time:YYYYMMDD}'}.log"

    logger.add(
        sink=str(log_path),
        level="DEBUG",
        format=("{time:YYYY-MM-DD HH:mm:ss} | {level:^7} | {file.name}:{line} | {message}"),
        rotation="00:00",
        retention="7 days",
        compression="zip",
    )

    logger.info(
        f"Logger configured for source '{source}'. "
        f"Sinks: stderr (level=ERROR+), file (level=DEBUG+) at '{log_path}'. "
        f"Rotation daily at midnight, retention 7 days, zipped."
    )


def add_run_logger(run_name: str, run_results_dir: Path) -> int:
    """Add (or reuse) a per-run file sink under results/<run_name>/logs/."""
    existing = _RUN_SINK_IDS.get(run_name)
    if existing is not None:
        return existing

    logs_dir = Path(run_results_dir) / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    run_log_path = logs_dir / "{time:YYYYMMDD}.log"

    sink_id = logger.add(
        sink=str(run_log_path),
        level="DEBUG",
        format=("{time:YYYY-MM-DD HH:mm:ss} | {level:^7} | {file.name}:{line} | {message}"),
        rotation="00:00",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )

    _RUN_SINK_IDS[run_name] = sink_id
    return sink_id


def remove_run_logger(run_name: str) -> None:
    """Remove the per-run sink for run_name (if present)."""
    sink_id = _RUN_SINK_IDS.pop(run_name, None)
    if sink_id is None:
        return
    logger.remove(sink_id)


def get_run_logger_id(run_name: str) -> Optional[int]:
    """Get the sink ID for the per-run logger for run_name, if it exists."""
    return _RUN_SINK_IDS.get(run_name)
