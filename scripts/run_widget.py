"""Entrypoint to run the Gradio web UI.

This script launches the Gradio app defined in
`dcs_simulation_engine.widget.app.build_app`. It mirrors the CLI runner style and
adds a few convenient flags.

Example:
    python scripts/run_widget.py --sims-dir ./sims --host 0.0.0.0 --port 7860
"""

from __future__ import annotations

import argparse
import sys

from loguru import logger

from dcs_simulation_engine.helpers.logging_helpers import configure_logger
from dcs_simulation_engine.widget.app import build_app


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the web runner.

    Returns:
        Parsed argparse Namespace containing CLI options.
    """
    parser = argparse.ArgumentParser(description="Gradio web runner entrypoint")

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host interface to bind the Gradio server to (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Port to run the Gradio server on (default: 7860).",
    )
    parser.add_argument(
        "--log-config",
        type=str,
        default="configs/logger-widget.config.yml",
        help="Path to a logging config YAML for the web runner.",
    )
    parser.add_argument(
        "--game",
        type=str,
        default="explore",
        help="Name of the game to launch (default: explore).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Show info logs (-v) or debug (-vv) to console",
    )
    return parser.parse_args()


def main() -> None:
    """Main entrypoint for running the Gradio web UI."""
    args = parse_args()

    # Configure logging; fall back gracefully if the file isn't present.
    try:
        configure_logger(args.log_config)
    except Exception as e:
        logger.warning(
            f"Failed to load log config at '{args.log_config}'; \
                using default logger. ({e})"
        )

    # --- configure console side channel based on -v
    if args.verbose > 0:
        # logger.remove()  # remove all existing sinks (including default stderr)
        # re-add file log via configure_logger already called
        level = "DEBUG" if args.verbose > 1 else "INFO"
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
        )

    app = None
    try:
        app = build_app(args.game)
        logger.info(f"Launching Gradio on http://{args.host}:{args.port}")
        CREATE_PUBLIC_URL = False  # set to True to enable public link via Gradio
        app.launch(
            server_name=args.host, server_port=args.port, share=CREATE_PUBLIC_URL
        )
    except Exception as e:
        logger.exception(f"Exception occurred while running the web app: {e}")
        print("Error occurred while running web app. Stopping.")
    finally:
        if app is not None:
            app.close()


if __name__ == "__main__":
    main()
