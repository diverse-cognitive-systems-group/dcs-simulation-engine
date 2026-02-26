"""CLI run command function."""

import os
from pathlib import Path
from typing import Optional

import gradio as gr
import typer
from loguru import logger

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.cli.common import check_localhost_http, done, step
from dcs_simulation_engine.cli.run_spec import RunConfig, parse_run_config
from dcs_simulation_engine.utils.file import load_yaml
from dcs_simulation_engine.widget.widget import build_widget_with_api

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def _run_local(cfg: RunConfig, config_path: Optional[Path]) -> None:
    """Run the simulation engine locally."""
    typer.echo()
    if config_path:
        typer.secho(
            f"Starting Simulation Engine using run config: {config_path}",
            bold=True,
        )
    else:
        typer.secho(
            "Starting Simulation Engine using default run configuration", bold=True
        )

    typer.echo(f"Run name: {cfg.run.name}")
    typer.echo()

    # init DB once for the whole run
    force_db_init = not IS_PROD
    step("Setting up database...")
    dbh.init_or_seed_database(force=force_db_init)
    done()

    apps = []
    try:
        typer.echo()
        step("Starting server...")

        if not cfg.games:
            raise typer.BadParameter("No games configured")

        # TODO: implement multiple games per link/run using multipage apps.
        # For now, just launch the first game and warn if multiple are provided.
        if len(cfg.games) > 1:
            logger.warning(
                f"Multiple games in run config isn't implemented yet. "
                f"Launching only the first game: '{cfg.games[0].name}'. "
                f"Ignoring: {[g.name for g in cfg.games[1:]]}"
            )

        game = cfg.games[0]
        banner = str(game.overrides.get("banner", game.name))

        extra_overrides = {k: v for k, v in game.overrides.items() if k != "banner"}
        if extra_overrides:
            logger.warning(
                f"Ignoring game overrides not supported: {list(extra_overrides.keys())}"
            )

        gradio_app = build_widget_with_api(game_name=game.name, banner=banner)
        apps.append(gradio_app)

        launch_info = gradio_app.launch(
            server_name="127.0.0.1",
            server_port=8080,
            quiet=True,
            prevent_thread_lock=True,
            theme=gr.themes.Default(primary_hue="violet"),
        )
        done()

        base_url = "http://localhost:8080"

        typer.echo()
        typer.secho(
            f"Simulation engine is running at {base_url}",
            bold=True,
        )

        public_url = (
            getattr(launch_info, "share_url", None) if launch_info is not None else None
        )
        if public_url:
            typer.echo(f"Public link: {public_url}")

        typer.echo()
        typer.secho("Press Ctrl+C to stop.", fg=typer.colors.YELLOW)
        typer.echo()

        import time

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received interrupt. Shutting down...")
        raise typer.Exit(code=130)
    except Exception:
        logger.exception("Failed while building, launching, or running widgets")
        raise typer.Exit(code=1)
    finally:
        for app in apps:
            try:
                app.close()
            except Exception:
                logger.debug(
                    "Suppressing exception during gradio_app.close()", exc_info=True
                )


def _run_fly(cfg: RunConfig, config_path: Optional[Path]) -> None:
    """Dispatch Fly deployments for each game."""
    try:
        from dcs_simulation_engine.infra.fly import FlyError, deploy_app
    except Exception as e:
        raise typer.BadParameter(
            "Fly provider selected but Fly deployment support isn't available/importable. "
            "Ensure deploy_app + FlyError are importable."
        ) from e

    typer.echo()
    if config_path:
        typer.secho(
            f"Starting Simulation Engine using run config: {config_path}",
            bold=True,
        )
    else:
        typer.secho(
            "Starting Simulation Engine using default run configuration", bold=True
        )

    typer.echo(f"Run name: {cfg.run.name}")
    step("Creating deployment on Fly.io...")

    try:
        if not cfg.games:
            raise typer.BadParameter("No games configured")

        # TODO: implement multiple games per link/run using multipage apps.
        # For now, just launch the first game and warn if multiple are provided.
        if len(cfg.games) > 1:
            logger.warning(
                f"Multiple games in run config isn't implemented yet. "
                f"Launching only the first game: '{cfg.games[0].name}'. "
                f"Ignoring: {[g.name for g in cfg.games[1:]]}"
            )

        game = cfg.games[0]
        res = deploy_app(
            game=game,
            app_name=cfg.run.name,
        )

        url = getattr(res, "url", None) or f"https://{cfg.run.name}.fly.dev"

    except FlyError as e:
        done()
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    done()

    typer.echo()
    typer.secho(
        f"Simulation engine is running at {url}",
        bold=True,
    )


def run(
    ctx: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Optional run config YAML.",
        exists=False,
        dir_okay=False,
        file_okay=True,
        readable=True,
    ),
    deploy: bool = typer.Option(
        False,
        "--deploy",
        help="Deploy publicly instead of running locally.",
        is_flag=True,
    ),
) -> None:
    """Start simulation engine."""
    cfg = RunConfig()  # defaults: local + explore

    if config is not None:
        if not config.exists():
            raise typer.BadParameter(f"Config file not found: {config}")
        data = load_yaml(config)
        cfg = parse_run_config(data)

    local_is_running = check_localhost_http()[0] == "Live"

    if deploy:
        _run_fly(cfg, config)
    else:
        if local_is_running:
            typer.secho(
                "A service is already running on localhost. Only one local instance is supported at a time.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        else:
            _run_local(cfg, config)

    typer.echo()
    typer.echo("To see what's running, use `dcs status`.")
    typer.echo()
