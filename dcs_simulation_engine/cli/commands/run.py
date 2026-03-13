"""CLI run command function."""

import os
from typing import Optional

import typer
from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.cli.bootstrap import (
    create_provider_admin,
)
from dcs_simulation_engine.cli.common import console, step
from dcs_simulation_engine.games import ai_client
from dcs_simulation_engine.helpers.run_helpers import (
    STATUS,
    BadRunNameError,
    RunNotFoundError,
    local_run_name,
    run_status,
    update_run,
    validate_run_name,
)
from loguru import logger

IS_PROD = os.environ.get("DCS_ENV", "dev").lower() == "prod"


def _run_local(
    run_name: str,
    status: Optional[STATUS] = None,
    mongo_uri: Optional[str] = None,
) -> None:
    """Run the FastAPI server locally."""
    try:
        import uvicorn

        # no existing run with this name -> must initialize db and create new run
        if not status:
            force_db_init = not IS_PROD
            with step("Starting database"):
                _ = force_db_init
                # Ensure DB is reachable and default indexes exist.
                create_provider_admin(mongo_uri=mongo_uri)

        with step("Starting API server"):
            ai_client.validate_openrouter_configuration()
            server = os.getenv("DCS_SERVER_HOST", "127.0.0.1")
            port = int(os.getenv("DCS_SERVER_PORT", "8080"))
            ttl_seconds = int(os.getenv("DCS_SESSION_TTL_SECONDS", str(24 * 3600)))
            sweep_interval_seconds = int(os.getenv("DCS_SESSION_SWEEP_INTERVAL_SECONDS", "60"))
            app = create_app(
                provider=None,
                mongo_uri=mongo_uri,
                session_ttl_seconds=ttl_seconds,
                sweep_interval_seconds=sweep_interval_seconds,
            )
            base_url = f"http://{server}:{port}"
            update_run(run_name, status=STATUS.RUNNING, link=base_url)

        console.print(f"Simulation engine API is running at {base_url}", style="success")
        typer.echo()
        typer.secho("Press Ctrl+C to stop.")
        typer.echo()
        uvicorn.run(app, host=server, port=port, loop="uvloop", workers=1)

    except KeyboardInterrupt:
        logger.info("Received interrupt. Shutting down...")
        raise typer.Exit(code=130)
    except Exception:
        logger.exception("Failed while building, launching, or running API server")
        raise typer.Exit(code=1)
    finally:
        try:
            logger.debug("Cleaning up resources and stopping run...")
            update_run(run_name, status=STATUS.STOPPED)
            logger.debug("Run stopped and resources cleaned up.")
        except Exception:
            logger.debug("Suppressing exception during update_run()", exc_info=True)


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
        help="Deprecated. Ignored by the FastAPI server.",
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

    if game_name:
        console.print("`--game-name` is deprecated and ignored by the FastAPI server.", style="warning")

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
        _run_local(run_name, status=None, mongo_uri=mongo_uri)
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

        _run_local(run_name, status=status, mongo_uri=mongo_uri)
        return

    console.print(f"Run '{run_name}' is in an unknown status: {status}", style="error")
    raise typer.Exit(code=1)
