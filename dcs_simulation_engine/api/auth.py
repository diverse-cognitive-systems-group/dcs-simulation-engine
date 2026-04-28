"""Authentication and app-state access helpers for the FastAPI API layer."""

from typing import Any, cast

from dcs_simulation_engine.api.models import (
    RemoteDeploymentMode,
    ServerConfigResponse,
    ServerMode,
)
from dcs_simulation_engine.api.registry import SessionRegistry
from dcs_simulation_engine.dal.base import DataProvider, PlayerRecord
from dcs_simulation_engine.utils.async_utils import maybe_await
from fastapi import HTTPException, Request, WebSocket, status

REMOTE_ADMIN_ROLE = "remote_admin"


def get_provider_from_request(request: Request) -> DataProvider:
    """Fetch the data provider stored on app state for an HTTP request."""
    return cast(DataProvider, request.app.state.provider)


def get_registry_from_request(request: Request) -> SessionRegistry:
    """Fetch the session registry stored on app state for an HTTP request."""
    return cast(SessionRegistry, request.app.state.registry)


def get_provider_from_websocket(websocket: WebSocket) -> DataProvider:
    """Fetch the data provider stored on app state for a WebSocket connection."""
    return cast(DataProvider, websocket.app.state.provider)


def get_registry_from_websocket(websocket: WebSocket) -> SessionRegistry:
    """Fetch the session registry stored on app state for a WebSocket connection."""
    return cast(SessionRegistry, websocket.app.state.registry)


def get_server_mode_from_request(request: Request) -> ServerMode:
    """Fetch the configured server mode from app state for an HTTP request."""
    return cast(ServerMode, getattr(request.app.state, "server_mode", "standard"))


def get_server_mode_from_websocket(websocket: WebSocket) -> ServerMode:
    """Fetch the configured server mode from app state for a WebSocket connection."""
    return cast(ServerMode, getattr(websocket.app.state, "server_mode", "standard"))


def get_default_experiment_name_from_request(request: Request) -> str | None:
    """Fetch the configured default experiment name from app state for an HTTP request."""
    return cast(str | None, getattr(request.app.state, "default_experiment_name", None))


def get_default_experiment_name_from_websocket(websocket: WebSocket) -> str | None:
    """Fetch the configured default experiment name from app state for a websocket."""
    return cast(str | None, getattr(websocket.app.state, "default_experiment_name", None))


def is_remote_management_enabled_from_request(request: Request) -> bool:
    """Return whether the app is running in remote-managed mode for this request."""
    return bool(getattr(request.app.state, "remote_management_enabled", False))


def is_remote_management_enabled_from_websocket(websocket: WebSocket) -> bool:
    """Return whether the app is running in remote-managed mode for this websocket."""
    return bool(getattr(websocket.app.state, "remote_management_enabled", False))


def build_server_config(
    *,
    server_mode: ServerMode,
    default_experiment_name: str | None = None,
    registration_required: bool = True,
) -> ServerConfigResponse:
    """Translate the active mode into frontend-readable capability flags."""
    is_standard = server_mode == "standard"
    authentication_required = is_standard and registration_required
    return ServerConfigResponse(
        mode=server_mode,
        authentication_required=authentication_required,
        registration_enabled=authentication_required,
        experiments_enabled=True,
        default_experiment_name=default_experiment_name,
    )


def resolve_remote_deployment_mode(
    *,
    server_mode: ServerMode,
    default_experiment_name: str | None,
) -> RemoteDeploymentMode:
    """Collapse app state into a public deployment mode for remote status."""
    if server_mode == "free_play":
        return "free_play"
    if default_experiment_name:
        return "experiment"
    return "standard"


def require_standard_mode(*, server_mode: ServerMode, detail: str) -> None:
    """Raise a 409 when an endpoint is disabled in free-play mode."""
    if server_mode != "standard":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def require_standard_mode_from_request(request: Request, *, detail: str) -> None:
    """Ensure an HTTP endpoint is only used while the server runs in standard mode."""
    require_standard_mode(server_mode=get_server_mode_from_request(request), detail=detail)


def require_remote_management_from_request(request: Request, *, detail: str) -> None:
    """Raise a 409 when remote-management-only endpoints are used outside remote mode."""
    if not is_remote_management_enabled_from_request(request):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def is_remote_admin(player: PlayerRecord) -> bool:
    """Return True when the player carries the remote admin role."""
    return str(player.data.get("role") or "") == REMOTE_ADMIN_ROLE


async def has_remote_admin_async(*, provider: Any) -> bool:
    """Return True when any player currently holds the remote admin role."""
    records = await maybe_await(provider.get_players())
    if not isinstance(records, list):
        return False
    return any(is_remote_admin(record) for record in records)


def _extract_bearer(authorization: str | None) -> str | None:
    """Return the token from 'Authorization: Bearer <token>', or None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def api_key_from_request(request: Request) -> str | None:
    """Extract api_key from Authorization: Bearer header."""
    return _extract_bearer(request.headers.get("authorization"))


def api_key_from_websocket(websocket: WebSocket) -> str | None:
    """Extract api_key from Authorization: Bearer header on a WebSocket."""
    return _extract_bearer(websocket.headers.get("authorization"))


def authenticate_player(*, provider: DataProvider, api_key: str | None) -> PlayerRecord | None:
    """Return the player for a raw API key, or None if invalid."""
    if api_key is None:
        return None

    key = api_key.strip()
    if not key:
        return None

    record = provider.get_players(access_key=key)
    if isinstance(record, PlayerRecord):
        return record
    return None


def require_player(*, provider: DataProvider, api_key: str | None) -> PlayerRecord:
    """Return authenticated player or raise a 401 HTTPException."""
    player = authenticate_player(provider=provider, api_key=api_key)
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access key")
    return player


async def authenticate_player_async(*, provider: Any, api_key: str | None) -> PlayerRecord | None:
    """Async variant of authenticate_player that supports sync/async providers."""
    if api_key is None:
        return None

    key = api_key.strip()
    if not key:
        return None

    record = await maybe_await(provider.get_players(access_key=key))
    if isinstance(record, PlayerRecord):
        return record
    return None


async def require_player_async(*, provider: Any, api_key: str | None) -> PlayerRecord:
    """Return authenticated player or raise 401 for sync/async providers."""
    player = await authenticate_player_async(provider=provider, api_key=api_key)
    if player is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access key")
    return player


async def require_remote_admin_async(*, provider: Any, api_key: str | None) -> PlayerRecord:
    """Return the authenticated remote admin player or raise 403."""
    player = await require_player_async(provider=provider, api_key=api_key)
    if not is_remote_admin(player):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access key required")
    return player
