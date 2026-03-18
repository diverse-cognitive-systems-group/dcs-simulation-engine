"""Player registration, auth, and management endpoints."""

from typing import Any

from dcs_simulation_engine.api.auth import (
    get_provider_from_request,
    maybe_await,
    require_player_async,
    require_standard_mode_from_request,
)
from dcs_simulation_engine.api.models import (
    AuthRequest,
    AuthResponse,
    RegistrationRequest,
    RegistrationResponse,
)
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/player", tags=["player"])


def _consent_field(
    *,
    key: str,
    answer: Any,
    field_type: str,
    label: str,
    required: bool,
    pii: bool,
) -> dict[str, Any]:
    """Build a form-compatible stored field shape expected by existing access checks."""
    return {
        "key": key,
        "type": field_type,
        "label": label,
        "required": required,
        "pii": pii,
        "answer": answer,
    }


def _registration_to_player_data(body: RegistrationRequest) -> dict[str, Any]:
    """Map fixed registration payload into the stored consent-compatible structure."""
    return {
        "full_name": _consent_field(
            key="full_name",
            answer=body.full_name,
            field_type="text",
            label="Full Name",
            required=True,
            pii=True,
        ),
        "email": _consent_field(
            key="email",
            answer=body.email,
            field_type="email",
            label="Email",
            required=True,
            pii=True,
        ),
        "phone_number": _consent_field(
            key="phone_number",
            answer=body.phone_number,
            field_type="phone",
            label="Phone Number",
            required=True,
            pii=True,
        ),
        "prior_experience": _consent_field(
            key="prior_experience",
            answer=body.prior_experience,
            field_type="textarea",
            label="Prior Experience",
            required=True,
            pii=False,
        ),
        "additional_comments": _consent_field(
            key="additional_comments",
            answer=body.additional_comments,
            field_type="textarea",
            label="Additional Comments",
            required=False,
            pii=False,
        ),
        "consent_to_followup": _consent_field(
            key="consent_to_followup",
            answer=body.consent_to_followup,
            field_type="boolean",
            label="Consent To Follow-up",
            required=True,
            pii=False,
        ),
        "consent_signature": _consent_field(
            key="consent_signature",
            answer=[body.consent_signature],
            field_type="text",
            label="Consent Signature",
            required=True,
            pii=True,
        ),
    }


@router.post("/registration", response_model=RegistrationResponse)
async def register_user(body: RegistrationRequest, request: Request) -> RegistrationResponse:
    """Register a new player record and return a newly issued API key."""
    require_standard_mode_from_request(
        request,
        detail="Player registration is disabled when the server is running in free play mode.",
    )
    provider = get_provider_from_request(request)
    player_data = _registration_to_player_data(body)

    record, api_key = await maybe_await(provider.create_player(player_data=player_data, issue_access_key=True))
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to issue access key")

    return RegistrationResponse(player_id=record.id, api_key=api_key)


@router.post("/auth", response_model=AuthResponse)
async def auth_user(body: AuthRequest, request: Request) -> AuthResponse:
    """Authenticate a user API key and return the associated player id."""
    require_standard_mode_from_request(
        request,
        detail="Player authentication is disabled when the server is running in free play mode.",
    )
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=body.api_key)
    full_name = player.data.get("full_name", {}).get("answer", "")
    return AuthResponse(player_id=player.id, full_name=full_name, authenticated=True)
