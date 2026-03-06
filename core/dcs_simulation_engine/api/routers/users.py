from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dcs_simulation_engine.api.dal.base import DataLayer

router = APIRouter()


class RegisterRequest(BaseModel):
    password: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    prior_experience: str | None = None
    additional_comments: str | None = None
    consent_to_followup: list[str] | None = None
    consent_signature: bool | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


def make_router(dal: DataLayer) -> APIRouter:
    """Return the users router bound to the given data layer."""

    @router.post("/login")
    async def login_user(body: LoginRequest) -> JSONResponse:
        """Verify credentials and return a new access key."""
        result = await dal.login_user(email=body.email, password=body.password)
        if result is None:
            return JSONResponse({"error": "Invalid email or password"}, status_code=401)
        return JSONResponse({"user_id": result.user_id, "api_key": result.api_key})

    @router.post("/register", status_code=201)
    async def register_user(body: RegisterRequest) -> JSONResponse:
        """Create a new user and return a one-time access key."""
        result = await dal.register_user(
            password=body.password,
            full_name=body.full_name,
            email=body.email,
            phone_number=body.phone_number,
            prior_experience=body.prior_experience,
            additional_comments=body.additional_comments,
            consent_to_followup=body.consent_to_followup,
            consent_signature=body.consent_signature,
        )
        return JSONResponse(
            {"user_id": result.user_id},
            status_code=201,
        )

    return router
