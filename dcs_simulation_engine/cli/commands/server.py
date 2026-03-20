"""CLI server command."""

from pathlib import Path
from typing import Optional

import typer
from dcs_simulation_engine.api.app import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SESSION_TTL_SECONDS,
    DEFAULT_SWEEP_INTERVAL_SECONDS,
    create_app,
)
from dcs_simulation_engine.cli.common import console, seed_database
from dcs_simulation_engine.games import ai_client


def server(
    ctx: typer.Context,
    host: str = typer.Option(
        DEFAULT_HOST,
        "--host",
        envvar="DCS_SERVER_HOST",
        help="Host to bind the server to.",
    ),
    port: int = typer.Option(
        DEFAULT_PORT,
        "--port",
        envvar="DCS_SERVER_PORT",
        help="Port to bind the server to.",
    ),
    ttl_seconds: int = typer.Option(
        DEFAULT_SESSION_TTL_SECONDS,
        "--session-ttl",
        envvar="DCS_SESSION_TTL_SECONDS",
        help="Session TTL in seconds.",
    ),
    sweep_interval_seconds: int = typer.Option(
        DEFAULT_SWEEP_INTERVAL_SECONDS,
        "--sweep-interval",
        envvar="DCS_SESSION_SWEEP_INTERVAL_SECONDS",
        help="Session sweep interval in seconds.",
    ),
    mongo_seed_dir: Optional[Path] = typer.Option(
        None,
        "--mongo-seed-dir",
        envvar="DCS_MONGO_SEED_DIR",
        help="Seed MongoDB from this directory of JSON/NDJSON files on startup.",
    ),
    dump_dir: Optional[Path] = typer.Option(
        None,
        "--dump",
        envvar="DCS_DUMP_DIR",
        help="Dump all Mongo collections to this directory when the server shuts down.",
    ),
    fake_ai_response: Optional[str] = typer.Option(
        None,
        "--fake-ai-response",
        help="Return this string for all AI responses instead of calling OpenRouter.",
    ),
    free_play: bool = typer.Option(
        False,
        "--free-play",
        help="Run the server in anonymous free play mode without registration or experiments.",
    ),
    remote_managed: bool = typer.Option(
        False,
        "--remote-managed",
        envvar="DCS_REMOTE_MANAGED",
        help="Run the server as a remote-managed deployment with bootstrap/export endpoints enabled.",
    ),
    default_experiment: Optional[str] = typer.Option(
        None,
        "--default-experiment",
        envvar="DCS_DEFAULT_EXPERIMENT_NAME",
        help="Default experiment name for experiment-centric deployments.",
    ),
    bootstrap_token: Optional[str] = typer.Option(
        None,
        "--bootstrap-token",
        envvar="DCS_REMOTE_BOOTSTRAP_TOKEN",
        help="One-time bootstrap token used to seed a remote-managed deployment.",
    ),
    cors_origin: Optional[list[str]] = typer.Option(
        None,
        "--cors-origin",
        help="Additional allowed CORS origin. Repeat the flag to allow multiple origins.",
    ),
) -> None:
    """Start the DCS API server."""
    import uvicorn

    mongo_uri = getattr(getattr(ctx, "obj", None), "mongo_uri", None)
    ai_client.set_fake_ai_response(fake_ai_response)
    ai_client.validate_openrouter_configuration()

    if mongo_seed_dir is not None:
        seed_database(ctx, mongo_seed_dir)

    try:
        app = create_app(
            provider=None,
            mongo_uri=mongo_uri,
            shutdown_dump_dir=dump_dir,
            server_mode="free_play" if free_play else "standard",
            default_experiment_name=default_experiment,
            remote_management_enabled=remote_managed,
            bootstrap_token=bootstrap_token,
            session_ttl_seconds=ttl_seconds,
            sweep_interval_seconds=sweep_interval_seconds,
            cors_origins=cors_origin or [],
        )
    except Exception:
        console.print_exception()
        raise typer.Exit(code=1)

    console.print(f"DCS server running at http://{host}:{port}", style="success")
    uvicorn.run(app, host=host, port=port, loop="uvloop", workers=1)
