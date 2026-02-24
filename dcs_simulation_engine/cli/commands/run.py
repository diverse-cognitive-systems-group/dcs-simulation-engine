"""CLI run command function."""

import os
from pathlib import Path
from typing import Any, Optional

import gradio as gr
import typer
from loguru import logger

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.cli.common import check_localhost_http, done, step
from dcs_simulation_engine.cli.config import RunConfig, parse_run_config
from dcs_simulation_engine.utils.file import load_yaml
from dcs_simulation_engine.utils.misc import validate_port
from dcs_simulation_engine.widget.widget import build_widget_with_api

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def _local_defaults(provider_cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "host": provider_cfg.get("host", "0.0.0.0"),
        "port": int(provider_cfg.get("port", provider_cfg.get("port", 8080))),
        "share": bool(provider_cfg.get("share", False)),
        "name": provider_cfg.get("name", "<b>DEFAULT</b>"),
    }


def _run_local(cfg: RunConfig, config_path: Optional[Path]) -> None:
    provider_cfg = _local_defaults(cfg.run.provider.config)

    host: str = str(provider_cfg["host"])
    port: int = int(provider_cfg["port"])
    share: bool = bool(provider_cfg["share"])
    name: str = str(provider_cfg["name"])

    if not validate_port(port):
        raise typer.BadParameter("run.provider.config.port must be between 1 and 65535")

    # Friendly header
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
    typer.echo(f"Location: {cfg.run.provider.location}")
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
        banner = str(game.overrides.get("banner", name))

        extra_overrides = {k: v for k, v in game.overrides.items() if k != "banner"}
        if extra_overrides:
            logger.warning(
                f"Ignoring game overrides not supported: {list(extra_overrides.keys())}"
            )

        logger.debug(f"Building widget for game='{game.name}' on {host}:{port} ...")
        gradio_app = build_widget_with_api(game_name=game.name, banner=banner)
        apps.append(gradio_app)

        launch_info = gradio_app.launch(
            server_name=host,
            server_port=port,
            share=share,
            quiet=True,
            prevent_thread_lock=True,
            theme=gr.themes.Default(primary_hue="violet"),
        )

        browser_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        base_url = f"http://{browser_host}:{port}"

        done()

        typer.echo()
        typer.secho(
            f"All set! Simulation engine is running at {base_url}",
            fg=typer.colors.GREEN,
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

    pcfg = cfg.run.provider.config
    run_name = cfg.run.name

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

    typer.echo(f"Run name: {run_name}")
    typer.echo(f"Location: {cfg.run.provider.location}")
    typer.echo(f"Games: {', '.join(g.name for g in cfg.games)}")
    typer.echo()

    step("Creating deployments on Fly.io...")

    app_tmpl = str(pcfg.get("app_name_template", "{name}"))
    fly_toml = Path(str(pcfg.get("fly_toml", "fly.toml")))
    env_file_raw = pcfg.get("env_file", ".env")
    env_file = Path(str(env_file_raw)) if env_file_raw is not None else None
    region = pcfg.get("region", None)
    version = str(pcfg.get("version", "latest"))

    created: list[tuple[str, str]] = []

    try:
        for game in cfg.games:
            deployment = app_tmpl.format(name=run_name, game=game.name)

            extra_overrides = dict(game.overrides)
            if extra_overrides:
                logger.warning(
                    f"Fly overrides present for game='{game.name}' but not yet wired into deploy_app: "
                    f"{list(extra_overrides.keys())}"
                )

            res = deploy_app(
                game=game.name,
                app_name=deployment,
                fly_toml=fly_toml,
                env_file=env_file,
                region=region,
                version=version,
            )

            app_name = getattr(res, "name", deployment)
            url = getattr(res, "url", None) or f"https://{app_name}.fly.dev"
            created.append((game.name, url))

    except FlyError as e:
        done()
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    done()

    typer.echo()
    typer.secho("All set!", fg=typer.colors.GREEN, bold=True)
    typer.echo("Your games are available here:")
    for name, url in created:
        typer.echo(f"• {name}: {url}")

    typer.echo()
    typer.echo("To see what's running later, use `dcs status`.")
    typer.echo()


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
) -> None:
    """Start simulation engine."""
    cfg = RunConfig()  # defaults: local + explore

    if config is not None:
        if not config.exists():
            raise typer.BadParameter(f"Config file not found: {config}")
        data = load_yaml(config)
        cfg = parse_run_config(data)

    provider = cfg.run.provider.location.strip().lower()
    logger.debug(f"Selected provider: {provider}")
    local_is_running = check_localhost_http()[0] == "Live"

    if provider == "local":
        if local_is_running:
            typer.secho(
                "A service is already running on localhost. Only one local instance is supported at a time.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        else:
            _run_local(cfg, config)

    elif provider == "fly":
        _run_fly(cfg, config)
    else:
        raise typer.BadParameter(f"Unknown provider: {provider}")
