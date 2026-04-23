"""HTTP endpoints for listing in-memory API sessions."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    get_provider_from_request,
    get_registry_from_request,
    get_server_mode_from_request,
    maybe_await,
    require_player_async,
    require_standard_mode_from_request,
)
from dcs_simulation_engine.api.infer_intent_evaluation import (
    InferIntentEvaluationUnavailableError,
    generate_or_get_infer_intent_evaluation,
)
from dcs_simulation_engine.api.models import (
    BranchSessionResponse,
    ClearSessionEventFeedbackResponse,
    InferIntentEvaluationResponse,
    SessionEventFeedback,
    SessionStatus,
    SessionSummary,
    SessionsListResponse,
    SubmitSessionEventFeedbackRequest,
    SubmitSessionEventFeedbackResponse,
)
from dcs_simulation_engine.core.experiment_manager import ExperimentManager
from dcs_simulation_engine.utils.time import utc_now
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session_status(entry_status: str, exited: bool) -> SessionStatus:
    """Compute user-facing session status from registry + manager state."""
    if entry_status == "closed" or exited:
        return "closed"
    if entry_status == "paused":
        return "paused"
    return "active"


async def _flush_live_session_feedback_target(
    *,
    request: Request,
    session_id: str,
    player_id: str | None,
) -> None:
    """Flush queued live-session events so feedback can target freshly emitted rows."""
    registry = get_registry_from_request(request)
    entry = registry.get(session_id)
    if entry is None or entry.player_id != player_id:
        return

    flush_hook = getattr(entry.manager, "flush_persistence_async", None)
    if callable(flush_hook):
        await maybe_await(flush_hook())


async def _flush_live_session_branch_source(
    *,
    request: Request,
    session_id: str,
    player_id: str | None,
) -> None:
    """Persist the latest in-memory transcript and runtime snapshot before branching."""
    registry = get_registry_from_request(request)
    entry = registry.get(session_id)
    if entry is None or entry.player_id != player_id:
        return

    flush_hook = getattr(entry.manager, "flush_persistence_async", None)
    if callable(flush_hook):
        await maybe_await(flush_hook())

    snapshot_hook = getattr(entry.manager, "persist_runtime_snapshot_async", None)
    if callable(snapshot_hook):
        await maybe_await(snapshot_hook())


async def _resolve_session_player_id(*, request: Request, session_id: str) -> str | None:
    """Resolve the session owner for standard or anonymous free-play sessions."""
    provider = get_provider_from_request(request)
    if get_server_mode_from_request(request) == "standard":
        player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
        return player.id

    registry = get_registry_from_request(request)
    entry = registry.get(session_id)
    if entry is not None:
        return entry.player_id

    session_record = await maybe_await(provider.get_session(session_id=session_id, player_id=None))
    if session_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session_record.player_id


@router.get("/{session_id}/status")
async def get_session_status(session_id: str, request: Request) -> dict:
    """Return the current status of a session. Works in both standard and free-play modes.

    Used by the frontend to verify a stored session_id is still paused and resumable.
    """
    registry = get_registry_from_request(request)
    entry = registry.get(session_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    computed = _session_status(entry.status, entry.manager.exited)
    return {"status": computed, "game_name": entry.game_name, "turns": entry.manager.turns}


@router.post("/{session_id}/branch", response_model=BranchSessionResponse)
async def branch_session(session_id: str, request: Request) -> BranchSessionResponse:
    """Clone a persisted paused child session from an existing root session."""
    provider = get_provider_from_request(request)
    player_id = await _resolve_session_player_id(request=request, session_id=session_id)

    await _flush_live_session_branch_source(
        request=request,
        session_id=session_id,
        player_id=player_id,
    )

    brancher = getattr(provider, "branch_session", None)
    if brancher is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Session branching is unavailable for this provider.",
        )

    try:
        session_record = await maybe_await(
            brancher(
                session_id=session_id,
                player_id=player_id,
                branched_at=utc_now(),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    branch_from_session_id = str(session_record.data.get("branch_from_session_id") or "")
    return BranchSessionResponse(
        session_id=session_record.session_id,
        branch_from_session_id=branch_from_session_id,
        game_name=session_record.game_name,
        status="paused",
        ws_path=f"/api/play/game/{session_record.session_id}/ws",
    )


@router.get("/list", response_model=SessionsListResponse)
async def list_sessions(request: Request) -> SessionsListResponse:
    """List active in-memory sessions for the player tied to the provided API key."""
    require_standard_mode_from_request(
        request,
        detail="Session endpoints are disabled when the server is running in free play mode.",
    )
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
    require_standard_mode_from_request(
        request,
        detail="Session endpoints are disabled when the server is running in free play mode.",
    )
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


@router.post(
    "/{session_id}/infer-intent/evaluation",
    response_model=InferIntentEvaluationResponse,
)
async def request_infer_intent_evaluation(
    session_id: str,
    request: Request,
) -> InferIntentEvaluationResponse:
    """Return a cached Infer Intent evaluation or generate and persist it on first request."""
    provider = get_provider_from_request(request)
    player_id = await _resolve_session_player_id(request=request, session_id=session_id)

    if getattr(provider, "append_session_event", None) is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Infer Intent evaluation is unavailable for this provider.",
        )

    condition: str | None = None
    get_assignment_fn = getattr(provider, "get_assignment_for_session_id", None)
    if get_assignment_fn is not None:
        assignment = await maybe_await(get_assignment_fn(session_id=session_id))
        if assignment is not None and assignment.experiment_name:
            try:
                config = ExperimentManager.get_experiment_config_cached(assignment.experiment_name)
                condition = config.condition
            except Exception:
                pass

    try:
        response = await generate_or_get_infer_intent_evaluation(
            provider=provider,
            session_id=session_id,
            player_id=player_id,
            condition=condition,
        )
    except InferIntentEvaluationUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)) from exc

    if response is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return response


@router.post(
    "/{session_id}/events/{event_id}/feedback",
    response_model=SubmitSessionEventFeedbackResponse,
)
async def submit_session_event_feedback(
    session_id: str,
    event_id: str,
    body: SubmitSessionEventFeedbackRequest,
    request: Request,
) -> SubmitSessionEventFeedbackResponse:
    """Store or overwrite feedback on one persisted NPC-message event."""
    provider = get_provider_from_request(request)
    player_id = await _resolve_session_player_id(request=request, session_id=session_id)

    await _flush_live_session_feedback_target(request=request, session_id=session_id, player_id=player_id)

    writer = getattr(provider, "set_session_event_feedback", None)
    if writer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Session event feedback is unavailable for this provider.",
        )

    now = utc_now()
    doesnt_make_sense = False if body.liked else body.doesnt_make_sense
    out_of_character = False if body.liked else body.out_of_character
    other = False if body.liked else body.other
    feedback = SessionEventFeedback(
        liked=body.liked,
        comment=body.comment.strip(),
        doesnt_make_sense=doesnt_make_sense,
        out_of_character=out_of_character,
        other=other,
        submitted_at=now,
    )
    stored = await maybe_await(
        writer(
            session_id=session_id,
            player_id=player_id,
            event_id=event_id,
            feedback=feedback.model_dump(),
        )
    )
    if not stored:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NPC message not found")

    return SubmitSessionEventFeedbackResponse(
        session_id=session_id,
        event_id=event_id,
        feedback=SessionEventFeedback.model_validate(stored),
    )


@router.delete(
    "/{session_id}/events/{event_id}/feedback",
    response_model=ClearSessionEventFeedbackResponse,
)
async def clear_session_event_feedback(
    session_id: str,
    event_id: str,
    request: Request,
) -> ClearSessionEventFeedbackResponse:
    """Remove feedback from one persisted NPC-message event."""
    provider = get_provider_from_request(request)
    player_id = await _resolve_session_player_id(request=request, session_id=session_id)

    await _flush_live_session_feedback_target(request=request, session_id=session_id, player_id=player_id)

    clearer = getattr(provider, "clear_session_event_feedback", None)
    if clearer is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Session event feedback clearing is unavailable for this provider.",
        )

    cleared = await maybe_await(
        clearer(
            session_id=session_id,
            player_id=player_id,
            event_id=event_id,
        )
    )
    if not cleared:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="NPC message not found")

    return ClearSessionEventFeedbackResponse(session_id=session_id, event_id=event_id, cleared=True)
