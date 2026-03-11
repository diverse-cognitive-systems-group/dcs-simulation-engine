"""Pydantic models and payload parsers for the API layer."""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

SessionStatus = Literal["active", "closed"]
EventType = Literal["ai", "info", "error", "warning"]
SetupDenialReason = Literal["not_allowed", "no_valid_pc", "no_valid_npc"]


class RegistrationRequest(BaseModel):
    """Payload for creating a new player and issuing an API key."""

    full_name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
    prior_experience: str = Field(min_length=1)
    additional_comments: str = ""
    consent_to_followup: bool
    consent_signature: str = Field(min_length=1)


class RegistrationResponse(BaseModel):
    """Response payload for registration."""

    player_id: str
    api_key: str


class AuthRequest(BaseModel):
    """Payload for API-key authentication checks."""

    api_key: str = Field(min_length=1)


class AuthResponse(BaseModel):
    """Response payload for successful API-key auth."""

    player_id: str
    full_name: str = ""
    authenticated: bool = True


class CreateGameRequest(BaseModel):
    """Payload for creating a new gameplay session."""

    api_key: str = Field(min_length=1)
    game: str = Field(min_length=1)
    pc_choice: str | None = None
    npc_choice: str | None = None
    source: str = Field(default="api", min_length=1)


class CreateGameResponse(BaseModel):
    """Response payload for newly created sessions."""

    session_id: str
    status: SessionStatus
    ws_path: str


class CharacterChoice(BaseModel):
    """A selectable character option for setup screens."""

    hid: str
    label: str


class GameSetupOptionsResponse(BaseModel):
    """Preflight setup data for a specific game + authenticated player."""

    game: str
    allowed: bool
    can_start: bool
    denial_reason: SetupDenialReason | None = None
    message: str | None = None
    pcs: list[CharacterChoice]
    npcs: list[CharacterChoice]


class SessionSummary(BaseModel):
    """A single in-memory session summary for list responses."""

    session_id: str
    game: str
    status: SessionStatus
    created_at: datetime
    last_active: datetime
    turns: int
    exited: bool


class SessionsListResponse(BaseModel):
    """Response payload for session list endpoint."""

    sessions: list[SessionSummary]


class WSAuthRequest(BaseModel):
    """WebSocket first-message auth frame (browser clients only)."""

    type: Literal["auth"]
    api_key: str = Field(min_length=1)


class WSAdvanceRequest(BaseModel):
    """WebSocket frame for advancing the game."""

    type: Literal["advance"]
    text: str = ""


class WSStatusRequest(BaseModel):
    """WebSocket frame for requesting session status."""

    type: Literal["status"]


class WSCloseRequest(BaseModel):
    """WebSocket frame for closing a session."""

    type: Literal["close"]


WSRequest = WSAdvanceRequest | WSStatusRequest | WSCloseRequest


class WSEventFrame(BaseModel):
    """WebSocket frame representing a single game event."""

    type: Literal["event"] = "event"
    session_id: str
    event_type: EventType
    content: str


class WSTurnEndFrame(BaseModel):
    """WebSocket frame emitted at the end of each completed turn."""

    type: Literal["turn_end"] = "turn_end"
    session_id: str
    turns: int
    exited: bool


class WSStatusFrame(BaseModel):
    """WebSocket frame reporting current session status."""

    type: Literal["status"] = "status"
    session_id: str
    status: SessionStatus
    turns: int
    exited: bool


class WSClosedFrame(BaseModel):
    """WebSocket frame indicating session closure."""

    type: Literal["closed"] = "closed"
    session_id: str


class WSErrorFrame(BaseModel):
    """WebSocket frame describing a protocol or auth error."""

    type: Literal["error"] = "error"
    detail: str


class GameSummary(BaseModel):
    """A single game entry."""

    name: str
    author: str
    description: str | None


class GamesListResponse(BaseModel):
    """Response payload for games list endpoint."""

    games: list[GameSummary]


class CharacterSummary(BaseModel):
    """A single character entry."""

    hid: str
    short_description: str


class CharactersListResponse(BaseModel):
    """Response payload for characters list endpoint."""

    characters: list[CharacterSummary]


class UpsertCharacterRequest(BaseModel):
    """Payload for creating or updating a character."""

    character_id: str | None = None
    data: dict


class UpsertCharacterResponse(BaseModel):
    """Response payload after upsert."""

    character_id: str


class DeleteCharacterResponse(BaseModel):
    """Response payload after deletion."""

    character_id: str


def parse_ws_auth(raw: str) -> WSAuthRequest | None:
    """Parse a first-message auth frame. Returns None if not an auth message."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or data.get("type") != "auth":
        return None
    try:
        return WSAuthRequest.model_validate(data)
    except ValidationError:
        return None


def parse_ws_request(raw: str) -> WSRequest:
    """Parse and validate a raw JSON websocket request payload."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Malformed JSON payload") from exc

    if not isinstance(data, dict):
        raise ValueError("Payload must be a JSON object")

    kind = data.get("type")
    try:
        if kind == "advance":
            return WSAdvanceRequest.model_validate(data)
        if kind == "status":
            return WSStatusRequest.model_validate(data)
        if kind == "close":
            return WSCloseRequest.model_validate(data)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc

    raise ValueError(f"Unknown request type: {kind!r}")
