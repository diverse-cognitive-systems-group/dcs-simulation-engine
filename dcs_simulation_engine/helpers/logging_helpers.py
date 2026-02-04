"""Logging helpers for DI Simulation Engine."""

import sys
from pathlib import Path

from loguru import logger


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
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level:^7} "
            "| {file.name}:{line} | {message}"
        ),
    )

    # File handler — DEBUG+, rotated daily, keep 7 days, zipped
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    log_path = logs_dir / f"{source}_{'{time:YYYYMMDD}'}.log"

    logger.add(
        sink=str(log_path),
        level="DEBUG",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level:^7} "
            "| {file.name}:{line} | {message}"
        ),
        rotation="00:00",
        retention="7 days",
        compression="zip",
    )

    logger.info(
        f"Logger configured for source '{source}'. "
        f"Sinks: stderr (level=ERROR+), file (level=DEBUG+) at '{log_path}'. "
        f"Rotation daily at midnight, retention 7 days, zipped."
    )
