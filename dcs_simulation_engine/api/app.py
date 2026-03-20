"""FastAPI application factory for the DCS server."""

from contextlib import asynccontextmanager
from pathlib import Path

from dcs_simulation_engine.api.auth import build_server_config
from dcs_simulation_engine.api.models import ServerConfigResponse, ServerMode, StatusResponse
from dcs_simulation_engine.api.registry import SessionRegistry
from dcs_simulation_engine.api.routers import (
    catalog_router,
    experiments_router,
    play_router,
    remote_router,
    sessions_router,
    users_router,
)
from dcs_simulation_engine.cli.bootstrap import create_async_provider
from dcs_simulation_engine.core.experiment_manager import ExperimentManager
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import DataProvider
from dcs_simulation_engine.dal.mongo.util import dump_all_collections_to_json_async
from dcs_simulation_engine.utils.time import utc_now
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_SESSION_TTL_SECONDS = 24 * 3600
DEFAULT_SWEEP_INTERVAL_SECONDS = 60


CORS_ORIGINS = [
    "http://localhost:5173",  # Vite dev server
]


def create_app(
    *,
    provider: DataProvider | object | None = None,
    mongo_uri: str | None = None,
    shutdown_dump_dir: Path | None = None,
    server_mode: ServerMode = "standard",
    default_experiment_name: str | None = None,
    remote_management_enabled: bool = False,
    bootstrap_token: str | None = None,
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    sweep_interval_seconds: int = DEFAULT_SWEEP_INTERVAL_SECONDS,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI server application."""
    registry = SessionRegistry(ttl_seconds=session_ttl_seconds, sweep_interval_seconds=sweep_interval_seconds)
    app = FastAPI(title="DCS Server")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if app.state.provider is None:
            app.state.provider = await create_async_provider(mongo_uri=mongo_uri)
        app.state.started_at = utc_now()
        SessionManager.preload_game_configs()
        ExperimentManager.preload_experiment_configs()
        await registry.start()
        try:
            yield
        finally:
            await registry.stop()
            if shutdown_dump_dir is not None:
                try:
                    db = app.state.provider.get_db()
                    dump_root = await dump_all_collections_to_json_async(db, shutdown_dump_dir)
                    logger.info("Wrote shutdown Mongo dump to {}", dump_root)
                except Exception:
                    logger.exception("Failed to write shutdown Mongo dump to {}", shutdown_dump_dir)

    app.router.lifespan_context = lifespan
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(dict.fromkeys((cors_origins or []) + CORS_ORIGINS)),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.provider = provider
    app.state.registry = registry
    app.state.server_mode = server_mode
    app.state.mongo_uri = mongo_uri
    app.state.default_experiment_name = default_experiment_name
    app.state.remote_management_enabled = remote_management_enabled
    app.state.bootstrap_token = bootstrap_token

    app.include_router(users_router)
    app.include_router(sessions_router)
    app.include_router(play_router)
    app.include_router(experiments_router)
    app.include_router(catalog_router)
    app.include_router(remote_router)

    @app.get("/api/server/config", response_model=ServerConfigResponse)
    def server_config() -> ServerConfigResponse:
        """Expose server capabilities so clients can adapt to the active mode."""
        return build_server_config(
            server_mode=server_mode,
            default_experiment_name=default_experiment_name,
        )

    @app.get("/api/status", response_model=StatusResponse)
    def status() -> StatusResponse:
        """Expose basic process liveness metadata for monitoring."""
        started_at = app.state.started_at
        uptime = int((utc_now() - started_at).total_seconds())
        return StatusResponse(started_at=started_at, uptime=max(uptime, 0))

    @app.get("/healthz")
    def health() -> dict[str, str]:
        """Simple liveness endpoint."""
        # TODO: Include
        #  - uptime
        #  - total sessions since start
        #  - active sessions
        #  - assignment status
        #  - last db writ
        #  - last request time
        return {"status": "ok"}

    return app
