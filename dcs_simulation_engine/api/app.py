"""FastAPI application factory for the DCS server."""

from contextlib import asynccontextmanager

from dcs_simulation_engine.api.registry import SessionRegistry
from dcs_simulation_engine.api.routers import (
    catalog_router,
    play_router,
    sessions_router,
    users_router,
)
from dcs_simulation_engine.cli.bootstrap import create_async_provider
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import DataProvider
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
        SessionManager.preload_game_configs()
        await registry.start()
        try:
            yield
        finally:
            await registry.stop()

    app.router.lifespan_context = lifespan
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins if cors_origins is not None else CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.provider = provider
    app.state.registry = registry

    app.include_router(users_router)
    app.include_router(sessions_router)
    app.include_router(play_router)
    app.include_router(catalog_router)

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
