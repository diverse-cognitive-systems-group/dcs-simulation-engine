"""CLI commands for running resources."""

import os

import gradio as gr
import typer
from loguru import logger

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.utils.misc import validate_port
from dcs_simulation_engine.widget.widget import build_widget_with_api

run_app = typer.Typer(help="Run resources.")

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"

@run_app.command("game")
def run_game(
    ctx: typer.Context,
    name: str = typer.Argument(
        "explore", help="Game name to run (default: explore).", show_default=True
    ),
    host: str = typer.Option(
        "0.0.0.0", "--host", help="Host interface to bind the Gradio server to."
    ),
    port: int = typer.Option(
        8080,
        "--port",
        callback=lambda v: (
            v
            if validate_port(v)
            else (_ for _ in ()).throw(
                typer.BadParameter("port must be between 1 and 65535")
            )
        ),
        help="Port to run the Gradio server on.",
    ),
    banner: str = typer.Option(
        None,
        "--banner",
        help="Optional markdown banner to show at the top of the widget.",
    ),
    share: bool = typer.Option(False, "--share", help="Create a public Gradio link."),
) -> None:
    """Run a game locally."""
    gradio_app = None
    try:
        # force_db_init should be True by default only for
        # development environments
        force_db_init = not IS_PROD  
        dbh.init_or_seed_database(force=force_db_init)

        logger.debug("Building Gradio widget...")
        gradio_app = build_widget_with_api(game_name=name, banner=banner)

        browser_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        base_url = f"http://{browser_host}:{port}"

        typer.echo()
        typer.secho("Game server starting…", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"• Play in your browser: {base_url}")
        typer.secho(
            "When you're ready to close it, press Ctrl+C.", fg=typer.colors.YELLOW
        )
        typer.echo()

        logger.info(f"Launching Gradio widget ({host}:{port})...")
        launch_info = gradio_app.launch(
            server_name=host,
            server_port=port,
            share=share,
            quiet=True,
            prevent_thread_lock=True,
            theme=gr.themes.Default(primary_hue="violet"),
        )

        public_url = (
            getattr(launch_info, "share_url", None) if launch_info is not None else None
        )
        if public_url:
            typer.secho(f"Public link: {public_url}", fg=typer.colors.CYAN)

        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt. Shutting down...")
            raise typer.Exit(code=130)

    except Exception:
        logger.exception("Failed while building, launching, or running the widget")
        raise typer.Exit(code=1)
    finally:
        if gradio_app is not None:
            try:
                gradio_app.close()
            except Exception:
                logger.debug(
                    "Suppressing exception during gradio_app.close()", exc_info=True
                )
