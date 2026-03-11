"""Authentication and app-state access helpers for the FastAPI API layer."""

from typing import cast

from dcs_simulation_engine.api.registry import SessionRegistry
from dcs_simulation_engine.dal.base import DataProvider, PlayerRecord
from fastapi import HTTPException, Request, WebSocket, status


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
