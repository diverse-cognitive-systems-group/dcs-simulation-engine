"""CLI run command function."""

import os
from typing import Optional

import typer
from dcs_simulation_engine.cli.bootstrap import (
    create_provider,
    create_provider_admin,
)
from dcs_simulation_engine.cli.common import console, step
from dcs_simulation_engine.helpers.game_helpers import (
    BadGameNameError,
    validate_game_name,
)
from dcs_simulation_engine.helpers.run_helpers import (
    STATUS,
    BadRunNameError,
    RunNotFoundError,
    local_run_name,
    run_status,
    update_run,
    validate_run_name,
)
from dcs_simulation_engine.widget import (
    api as widget_api,
)
from dcs_simulation_engine.widget import (
    handlers as widget_handlers,
)
from dcs_simulation_engine.widget.widget import (
    build_widget_with_api,
)
from gradio.themes import Default
from loguru import logger

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def _run_local(
    run_name: str,
    game_name: str,
    status: Optional[STATUS] = None,
    mongo_uri: Optional[str] = None,
) -> None:
    """Run the simulation engine locally."""
    try:
        provider = create_provider(mongo_uri=mongo_uri)

        # no existing run with this name -> must initialize db and create new run
        if not status:
            force_db_init = not IS_PROD
            with step("Starting database"):
                create_provider_admin(provider).init_or_seed_database(force=force_db_init)

        widget_handlers.set_provider(provider)
        widget_api.set_provider(provider)

        # start the widget
        with step("Starting widget"):
            gradio_app = build_widget_with_api(game_name=game_name, banner=run_name, provider=provider)

            server = "127.0.0.1"
            port = 8080
            base_url = f"http://{server}:{port}"
            launch_info = gradio_app.launch(
                server_name=server,
                server_port=port,
                quiet=True,
                prevent_thread_lock=True,
                theme=Default(primary_hue="violet"),
            )
            update_run(run_name, status=STATUS.RUNNING, link=base_url)

        console.print(f"Simulation engine is running at {base_url}", style="success")

        public_url = getattr(launch_info, "share_url", None) if launch_info is not None else None
        if public_url:
            typer.echo(f"Public link: {public_url}")

        typer.echo()
        typer.secho("Press Ctrl+C to stop.")
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
        try:
            logger.debug("Cleaning up resources and stopping run...")
            update_run(run_name, status=STATUS.STOPPED)
            gradio_app.close()
            logger.debug("Run stopped and resources cleaned up.")
        except Exception:
            logger.debug(
                "Suppressing exception during gradio_app.close() and update_run()",
                exc_info=True,
            )


def _run_fly(run_name: str, game_name: str) -> None:
    """Dispatch Fly deployments for each game."""
    try:
        from dcs_simulation_engine.infra.fly import (
            FlyError,
            deploy_app,
        )
    except Exception as e:
        raise typer.BadParameter(
            "Fly provider selected but Fly deployment support isn't available/importable. "
            "Ensure deploy_app + FlyError are importable."
        ) from e

    typer.echo()
    typer.echo(f"Run name: {run_name}")

    try:
        res = deploy_app(
            game=game_name,
            app_name=run_name,
        )

        url = getattr(res, "url", None) or f"https://{run_name}.fly.dev"

    except FlyError as e:
        typer.secho(str(e), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo()
    typer.secho(
        f"Simulation engine is running at {url}",
        bold=True,
    )


def run(
    ctx: typer.Context,
    deploy: bool = typer.Option(
        False,
        "--deploy",
        help="Deploy publicly instead of running locally.",
    ),
    run_name: Optional[str] = typer.Option(
        None,
        "--run-name",
        "-r",
        prompt="Run name",
    ),
    game_name: Optional[str] = typer.Option(
        None,
        "--game-name",
        "-g",
        prompt="Game name",
    ),
) -> None:
    """Start simulation engine.

    Note:
    - Running only one local instance at a time is supported.
    - Multiple remote (e.g. Fly) deployments are supported.
    """
    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)

    # 0) Validate run name
    try:
        run_name = validate_run_name(run_name)
    except BadRunNameError as e:
        console.print(str(e), style="error")
        raise typer.Exit(code=1)

    # 1) Determine if the named run exists and its status
    try:
        status = run_status(run_name)  # returns STATUS.RUNNING or STATUS.STOPPED
    except RunNotFoundError:
        status = None  # means run "doesn't exist"

    # 2) Validate game name (required for both create and restart)
    try:
        game_name = validate_game_name(game_name)
    except BadGameNameError as e:
        console.print(str(e), style="error")
        raise typer.Exit(code=1)

    # 3) Only one local instance total, regardless of name.
    # If some *other* local run is already running, we cannot start/restart this one.
    if not deploy:
        existing_local = local_run_name()  # None if no local run exists
        if existing_local and existing_local != run_name:
            console.print(
                f"Another local run '{existing_local}' is already running. "
                "Only one local instance is supported at a time.",
                style="error",
            )
            raise typer.Exit(code=1)

    # 4) If run doesn't exist -> create
    if status is None:
        console.print(f"Creating run instance: '{run_name}'")
        if deploy:
            console.print("Not implemented.", style="error")
            raise typer.Exit(code=1)
        _run_local(run_name, game_name, status=None, mongo_uri=mongo_uri)
        return

    # 5) Run exists -> handle status
    if status == STATUS.RUNNING:
        console.print(
            f"Run '{run_name}' is already running. Only one instance with the same name can run at a time.",
            style="error",
        )
        raise typer.Exit(code=1)

    if status == STATUS.STOPPED:
        restart = typer.confirm(
            f"Run '{run_name}' already exists but is stopped. Restart it?",
            default=True,
        )
        if not restart:
            console.print("Aborting.", style="warning")
            raise typer.Exit(code=0)

        if deploy:
            console.print("Not implemented.", style="error")
            raise typer.Exit(code=1)

        _run_local(run_name, game_name, status=status, mongo_uri=mongo_uri)
        return

    console.print(f"Run '{run_name}' is in an unknown status: {status}", style="error")
    raise typer.Exit(code=1)
