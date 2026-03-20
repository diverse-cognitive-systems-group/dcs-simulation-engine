"""API router exports."""

from dcs_simulation_engine.api.routers.catalog import router as catalog_router
from dcs_simulation_engine.api.routers.experiments import router as experiments_router
from dcs_simulation_engine.api.routers.play import router as play_router
from dcs_simulation_engine.api.routers.remote import router as remote_router
from dcs_simulation_engine.api.routers.sessions import router as sessions_router
from dcs_simulation_engine.api.routers.users import router as users_router

__all__ = ["catalog_router", "experiments_router", "play_router", "remote_router", "sessions_router", "users_router"]
