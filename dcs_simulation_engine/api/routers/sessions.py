"""HTTP endpoints for listing in-memory API sessions."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    get_provider_from_request,
    get_registry_from_request,
    require_player,
)
from dcs_simulation_engine.api.models import (
    SessionStatus,
    SessionSummary,
    SessionsListResponse,
)
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_status(entry_status: str, exited: bool) -> SessionStatus:
    """Compute user-facing session status from registry + manager state."""
    if entry_status == "closed" or exited:
        return "closed"
    return "active"


@router.get("/list", response_model=SessionsListResponse)
def list_sessions(request: Request) -> SessionsListResponse:
    """List active in-memory sessions for the player tied to the provided API key."""
    provider = get_provider_from_request(request)
    registry = get_registry_from_request(request)

    player = require_player(provider=provider, api_key=api_key_from_request(request))
    sessions = []
    for entry in registry.list_for_player(player.id):
        status = _session_status(entry.status, entry.manager.exited)
        if status == "closed" and entry.status != "closed":
            registry.close(entry.session_id)

        sessions.append(
            SessionSummary(
                session_id=entry.session_id,
                game=entry.game_name,
                status=status,
                created_at=entry.created_at,
                last_active=entry.last_active,
                turns=entry.manager.turns,
                exited=entry.manager.exited,
            )
        )

    return SessionsListResponse(sessions=sessions)
