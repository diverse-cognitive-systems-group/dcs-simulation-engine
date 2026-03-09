"""CLI bootstrap: single entrypoint for backend wiring and lifecycle."""

import os

from dcs_simulation_engine.dal.base import DataProvider
from dcs_simulation_engine.dal.mongo import (
    MongoAdmin,
    MongoProvider,
)
from dcs_simulation_engine.dal.mongo.const import (
    DEFAULT_MONGO_URI,
)
from dcs_simulation_engine.dal.mongo.util import connect_db
from dcs_simulation_engine.infra.docker import (
    ensure_mongo_service_down,
    ensure_mongo_service_up,
    get_mongodb_ip,
)


def _resolve_mongo_uri(*, mongo_uri: str | None = None) -> str:
    """Resolve the Mongo URI from explicit input, env, or local docker fallback."""
    if mongo_uri:
        return mongo_uri

    env_uri = os.getenv("MONGO_URI")
    if env_uri:
        return env_uri

    ensure_mongo_service_up()
    ip = get_mongodb_ip()
    if ip:
        return f"mongodb://{ip}:27017/"
    return DEFAULT_MONGO_URI


def create_provider(*, mongo_uri: str | None = None) -> DataProvider:
    """Return a DataProvider wired to a resolved MongoDB URI."""
    uri = _resolve_mongo_uri(mongo_uri=mongo_uri)
    return MongoProvider(db=connect_db(uri=uri))


def create_provider_admin(provider: DataProvider) -> MongoAdmin:
    """Return a MongoAdmin for the given provider.

    The provider must be a MongoProvider instance.
    """
    if not isinstance(provider, MongoProvider):
        raise TypeError(f"create_provider_admin requires MongoProvider, got {type(provider).__name__}")
    return MongoAdmin(provider.get_db())


def teardown_local_backend(*, wipe: bool = False) -> bool:
    """Tear down local backend resources."""
    return ensure_mongo_service_down(wipe=wipe)
