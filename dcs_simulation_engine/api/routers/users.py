"""Player registration, auth, and management endpoints."""

from typing import Any

from dcs_simulation_engine.api.auth import (
    REMOTE_ADMIN_ROLE,
    get_provider_from_request,
    has_remote_admin_async,
    is_remote_management_enabled_from_request,
    maybe_await,
    require_player_async,
)
from dcs_simulation_engine.api.models import (
    AuthRequest,
    AuthResponse,
    RegistrationRequest,
    RegistrationResponse,
)
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/player", tags=["player"])


def _registration_field(
    *,
    key: str,
    answer: Any,
    field_type: str,
    label: str,
    required: bool,
    pii: bool,
) -> dict[str, Any]:
    """Build a form-compatible stored field shape for registration data."""
    return {
        "key": key,
        "type": field_type,
        "label": label,
        "required": required,
        "pii": pii,
        "answer": answer,
    }


def _registration_to_player_data(body: RegistrationRequest) -> dict[str, Any]:
    """Map fixed registration payload into the stored player data structure."""
    return {
        "full_name": _registration_field(
            key="full_name",
            answer=body.full_name,
            field_type="text",
            label="Full Name",
            required=True,
            pii=True,
        ),
        "email": _registration_field(
            key="email",
            answer=body.email,
            field_type="email",
            label="Email",
            required=True,
            pii=True,
        ),
        "phone_number": _registration_field(
            key="phone_number",
            answer=body.phone_number,
            field_type="phone",
            label="Phone Number",
            required=True,
            pii=True,
        ),
    }


@router.post("/registration", response_model=RegistrationResponse)
async def register_user(body: RegistrationRequest, request: Request) -> RegistrationResponse:
    """Register a new player record and return a newly issued API key."""
    run_config = request.app.state.run_config
    if not run_config.registration_required:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Player registration is disabled for this run.")
    provider = get_provider_from_request(request)
    player_data = _registration_to_player_data(body)
    if is_remote_management_enabled_from_request(request) and not await has_remote_admin_async(provider=provider):
        player_data["role"] = REMOTE_ADMIN_ROLE

    record, api_key = await maybe_await(provider.create_player(player_data=player_data, issue_access_key=True))
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to issue access key")

    return RegistrationResponse(player_id=record.id, api_key=api_key)


@router.post("/anonymous", response_model=RegistrationResponse)
async def anonymous_user(request: Request) -> RegistrationResponse:
    """Create an ephemeral anonymous player for runs that do not require registration."""
    run_config = request.app.state.run_config
    if run_config.registration_required:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Anonymous players are disabled for this run.")
    provider = get_provider_from_request(request)
    record, api_key = await maybe_await(
        provider.create_player(
            player_data={"anonymous": True},
            issue_access_key=True,
        )
    )
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to issue access key")
    return RegistrationResponse(player_id=record.id, api_key=api_key)


@router.post("/auth", response_model=AuthResponse)
async def auth_user(body: AuthRequest, request: Request) -> AuthResponse:
    """Authenticate a user API key and return the associated player id."""
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=body.api_key)
    full_name = player.data.get("full_name", {}).get("answer", "")
    return AuthResponse(player_id=player.id, full_name=full_name, authenticated=True)
