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
    fake_ai_response: Optional[str] = typer.Option(
        None,
        "--fake-ai-response",
        help="Return this string for all AI responses instead of calling OpenRouter.",
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
            session_ttl_seconds=ttl_seconds,
            sweep_interval_seconds=sweep_interval_seconds,
        )
    except Exception:
        console.print_exception()
        raise typer.Exit(code=1)

    console.print(f"DCS server running at http://{host}:{port}", style="success")
    uvicorn.run(app, host=host, port=port, loop="uvloop", workers=1)
