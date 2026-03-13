"""HTTP endpoints for listing in-memory API sessions."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    get_provider_from_request,
    get_registry_from_request,
    maybe_await,
    require_player_async,
)
from dcs_simulation_engine.api.models import (
    SessionStatus,
    SessionSummary,
    SessionsListResponse,
)
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_status(entry_status: str, exited: bool) -> SessionStatus:
    """Compute user-facing session status from registry + manager state."""
    if entry_status == "closed" or exited:
        return "closed"
    return "active"


@router.get("/list", response_model=SessionsListResponse)
async def list_sessions(request: Request) -> SessionsListResponse:
    """List active in-memory sessions for the player tied to the provided API key."""
    provider = get_provider_from_request(request)
    registry = get_registry_from_request(request)

    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
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


@router.get("/{session_id}/reconstruction")
async def get_session_reconstruction(session_id: str, request: Request) -> dict:
    """Return complete persisted metadata + event stream for transcript replay."""
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))

    loader = getattr(provider, "get_session_reconstruction", None)
    if loader is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Session reconstruction is unavailable for this provider.",
        )

    payload = await maybe_await(loader(session_id=session_id, player_id=player.id))
    if not payload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return payload
