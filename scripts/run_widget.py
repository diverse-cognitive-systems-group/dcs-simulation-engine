"""Entrypoint to run the widget UI.

Example:
    poetry run python -m scripts.run_widget
    poetry run python scripts/run_widget.py --game Explore --banner "<b>W.I.P.</b>"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

from dcs_simulation_engine.helpers.logging_helpers import configure_logger
from dcs_simulation_engine.widget.widget import build_widget


def _port(value: str) -> int:
    """Validate and return a TCP port."""
    try:
        port = int(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError("port must be an integer") from e
    if not (1 <= port <= 65535):
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the web runner."""
    parser = argparse.ArgumentParser(description="Gradio web runner entrypoint")

    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host interface to bind the Gradio server to (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=_port,
        default=8080,
        help="Port to run the Gradio server on (default: 8080).",
    )
    parser.add_argument(
        "--log-config",
        type=Path,
        default=Path("configs/logger-widget.config.yml"),
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
        help="Increase console verbosity: -v for INFO, -vv for DEBUG.",
    )
    parser.add_argument(
        "--banner",
        type=str,
        default="<b>DEMO</b>",
        help="Optional markdown banner to show at the top of the widget.",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public Gradio link.",
    )
    parser.add_argument(
        "--hide-npc-selector",
        action="store_true",
        help="Hide the non-player character (NPC) selector in the widget.",
    )
    parser.add_argument(
        "--hide-pc-selector",
        action="store_true",
        help="Hide the player character (PC) selector in the widget.",
    )
    parser.add_argument(
        "--source",
        type=str,
        default=None,
        help="Source helps track the origin of the simulation in database entries, etc.",
    )
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    """Run the Gradio app with the provided arguments."""
    app = None
    try:
        logger.debug("Building Gradio widget...")
        # TODO: add source
        app = build_widget(
            game_name=args.game,
            banner=args.banner,
            show_npc_selector=not args.hide_npc_selector,
            show_pc_selector=not args.hide_pc_selector,
            # source=args.source,
        )

        logger.info(f"Launching Gradio widget ({args.host}:{args.port})...")
        app.launch(
            server_name=args.host,
            server_port=args.port,
            share=args.share,
        )
        return 0  # normal exit after blocking launch returns
    except KeyboardInterrupt:
        logger.info("Received interrupt. Shutting down...")
        return 130  # conventional SIGINT exit code
    except Exception:
        logger.exception("Failed while building, launching, or running the widget")
        return 1
    finally:
        if app is not None:
            try:
                # TODO: will this stop/clean up state resources from inside the app?
                app.close()
            except Exception:
                logger.debug("Suppressing exception during app.close()", exc_info=True)


def main() -> None:
    """Main entrypoint for running the widget."""
    args = parse_args()

    if args.source is None:
        logger.warning(
            "No source was provided for WIDGET run, defaulting to 'widget-default'."
            " Source helps track the origin of the simulation in database entries, etc."
        )
        args.source = "widget-default"

    try:
        configure_logger(source=args.source)
    except Exception as e:
        logger.warning(f"Failed to configure logger with source '{args.source}': {e}")

    # --- configure console side channel based on -v
    if args.verbose > 0:
        level = "DEBUG" if args.verbose > 1 else "INFO"
        logger.add(
            sys.stderr,
            level=level,
            format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>",
        )

    code = run(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
