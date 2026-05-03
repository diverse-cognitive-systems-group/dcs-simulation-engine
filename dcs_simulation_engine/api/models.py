"""Pydantic models and payload parsers for the API layer."""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

SessionStatus = Literal["active", "paused", "closed"]
EventType = Literal["ai", "info", "error", "warning"]
SetupDenialReason = Literal["no_valid_pc", "no_valid_npc"]
AssignmentStatus = Literal["assigned", "in_progress", "completed", "interrupted"]
NextAssignmentMode = Literal["locked", "choice", "blocked", "none"]
FormTriggerEvent = Literal[
    "before_all_assignments",
    "before_assignment",
    "after_assignment",
    "after_all_assignments",
]


class RegistrationRequest(BaseModel):
    """Payload for creating a new player and issuing an API key."""

    full_name: str = Field(min_length=1)
    email: str = Field(min_length=1)
    phone_number: str = Field(min_length=1)
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


class ServerConfigResponse(BaseModel):
    """Response payload describing server capabilities."""

    authentication_required: bool
    registration_enabled: bool
    run_name: str


class StatusResponse(BaseModel):
    """Response payload describing process liveness and uptime."""

    status: Literal["ok"] = "ok"
    started_at: datetime
    uptime: int


class RemoteBootstrapResponse(BaseModel):
    """Bootstrap response containing the newly issued remote admin key."""

    player_id: str
    admin_api_key: str
    run_name: str | None = None


class RemoteStatusResponse(BaseModel):
    """Public status payload for remote-managed deployments."""

    status: Literal["ok"] = "ok"
    started_at: datetime
    uptime: int
    run_name: str
    progress: "ProgressResponse | None" = None
    run_status: "RunStatusResponse | None" = None


class CreateGameRequest(BaseModel):
    """Payload for creating a new gameplay session."""

    api_key: str | None = None
    game: str = Field(min_length=1)
    pc_choice: str | None = None
    npc_choice: str | None = None
    source: str = Field(default="api", min_length=1)


class CreateGameResponse(BaseModel):
    """Response payload for newly created sessions."""

    session_id: str
    status: SessionStatus
    ws_path: str


class BranchSessionResponse(BaseModel):
    """Response payload for a branched paused child session."""

    session_id: str
    branch_from_session_id: str
    game_name: str
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


class AssignmentSummary(BaseModel):
    """Assignment summary returned by run endpoints."""

    assignment_id: str
    game_name: str
    pc_hid: str
    npc_hid: str
    status: AssignmentStatus
    active_session_id: str | None = None
    has_pending_forms: bool = False
    game_description: str = ""
    player_character_name: str = ""
    player_character_description: str = ""
    simulator_character_description: str = ""
    simulator_character_details_visible: bool = False


class ProgressResponse(BaseModel):
    """Finite progress payload for the usability run."""

    total: int
    completed: int
    is_complete: bool


class GameStatusResponse(BaseModel):
    """Per-game status counts for a run."""

    total: int
    completed: int
    in_progress: int


class RunStatusResponse(BaseModel):
    """Aggregate status payload for a run."""

    is_open: bool
    total: int
    completed: int
    per_game: dict[str, GameStatusResponse]


class NextAssignmentState(BaseModel):
    """Backend-derived state for the next participant action."""

    mode: NextAssignmentMode
    reason: str = ""
    assignment: AssignmentSummary | None = None
    options: list["EligibleAssignmentOption"] = Field(default_factory=list)


class FormTriggerResponse(BaseModel):
    """Canonical form trigger returned by setup APIs."""

    event: FormTriggerEvent
    match: None = None


class PendingFormGroupResponse(BaseModel):
    """Actionable group of forms the participant must submit."""

    group_id: str
    trigger: FormTriggerResponse
    forms: list[dict] = Field(default_factory=list)
    assignment_id: str | None = None


class SetupResponse(BaseModel):
    """Setup payload for the run landing page."""

    run_name: str
    description: str
    is_open: bool
    forms: list[dict] = Field(default_factory=list)
    pending_form_groups: list[PendingFormGroupResponse] = Field(default_factory=list)
    progress: ProgressResponse
    current_assignment: AssignmentSummary | None = None
    # True only when the participant has exhausted all assignments available to them.
    assignment_completed: bool = False
    next_assignment: NextAssignmentState | None = None
    allow_choice_if_multiple: bool = False
    require_completion: bool = True
    eligible_assignment_options: list["EligibleAssignmentOption"] = Field(default_factory=list)
    assignments: list[AssignmentSummary] = Field(default_factory=list)
    # Set when the current assignment has a paused session the player can resume.
    resumable_session_id: str | None = None


class EligibleAssignmentOption(BaseModel):
    """One eligible game+PC+NPC option returned when assignment choice is allowed."""

    game_name: str
    pc_hid: str
    npc_hid: str
    game_description: str = ""
    player_character_name: str = ""
    player_character_description: str = ""
    simulator_character_description: str = ""
    simulator_character_details_visible: bool = False


class EligibleAssignmentOptionsResponse(BaseModel):
    """List of eligible assignment options for a player."""

    options: list[EligibleAssignmentOption]


class SelectAssignmentRequest(BaseModel):
    """Payload for player-directed assignment selection."""

    game_name: str
    pc_hid: str
    npc_hid: str


class FormSubmitRequest(BaseModel):
    """Payload for submitting one pending run form group."""

    group_id: str = Field(min_length=1)
    responses: dict[str, dict]


class FormSubmitResponse(BaseModel):
    """Response after storing one pending run form group."""

    group_id: str
    trigger: FormTriggerResponse
    assignment_id: str | None = None


class AssignmentSessionRequest(BaseModel):
    """Payload for creating a session from the current assignment."""

    source: str = Field(default="run", min_length=1)
    assignment_id: str | None = None


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


class SessionEventFeedback(BaseModel):
    """Stored reaction, comment, and issue flags attached to one assistant message."""

    liked: bool
    comment: str = ""
    doesnt_make_sense: bool
    out_of_character: bool
    other: bool = False
    submitted_at: datetime


class SubmitSessionEventFeedbackRequest(BaseModel):
    """Payload for storing feedback on a single assistant session event."""

    liked: bool
    comment: str = ""
    doesnt_make_sense: bool
    out_of_character: bool
    other: bool = False


class SubmitSessionEventFeedbackResponse(BaseModel):
    """Response payload after feedback is stored on a session event."""

    session_id: str
    event_id: str
    feedback: SessionEventFeedback


class ClearSessionEventFeedbackResponse(BaseModel):
    """Response payload after feedback is removed from a session event."""

    session_id: str
    event_id: str
    cleared: bool = True


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


class WSSessionMetaFrame(BaseModel):
    """WebSocket frame sent once after auth, carrying session metadata."""

    type: Literal["session_meta"] = "session_meta"
    session_id: str
    pc_hid: str | None = None
    npc_hid: str | None = None
    has_game_feedback: bool = False


class WSEventFrame(BaseModel):
    """WebSocket frame representing a single game event."""

    type: Literal["event"] = "event"
    session_id: str
    event_type: EventType
    content: str
    event_id: str | None = None


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


class WSReplayStartFrame(BaseModel):
    """WebSocket frame signaling the start of a historical event replay burst."""

    type: Literal["replay_start"] = "replay_start"
    session_id: str


class WSReplayEventFrame(BaseModel):
    """WebSocket frame carrying one historical event during replay."""

    type: Literal["replay_event"] = "replay_event"
    session_id: str
    event_type: EventType
    content: str
    event_id: str | None = None
    role: Literal["user", "ai"] = "ai"


class WSReplayEndFrame(BaseModel):
    """WebSocket frame signaling the end of a historical event replay burst."""

    type: Literal["replay_end"] = "replay_end"
    session_id: str
    turns: int


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
