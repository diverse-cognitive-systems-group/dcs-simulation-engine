"""Run-scoped endpoints for assignment-driven study flows."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    get_provider_from_request,
    get_registry_from_request,
    require_player_async,
)
from dcs_simulation_engine.api.models import (
    AssignmentSessionRequest,
    AssignmentSummary,
    CreateGameResponse,
    EligibleAssignmentOption,
    EligibleAssignmentOptionsResponse,
    FormSubmitRequest,
    FormSubmitResponse,
    GameStatusResponse,
    NextAssignmentState,
    PendingFormGroupResponse,
    ProgressResponse,
    RunStatusResponse,
    SelectAssignmentRequest,
    SetupResponse,
)
from dcs_simulation_engine.core.engine_run_manager import EngineRunManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/run", tags=["run"])


def _get_run_manager(request: Request) -> EngineRunManager:
    return request.app.state.engine_run_manager


async def _assignment_summary(
    provider,
    assignment,
    *,
    pending_assignment_form_ids: set[str] | None = None,
) -> AssignmentSummary | None:
    if assignment is None:
        return None
    assignment_data = getattr(assignment, "data", {}) or {}
    metadata = await EngineRunManager.assignment_display_metadata_async(
        provider=provider,
        game_name=assignment.game_name,
        pc_hid=assignment.pc_hid,
        npc_hid=assignment.npc_hid,
    )
    return AssignmentSummary(
        assignment_id=assignment.assignment_id,
        game_name=assignment.game_name,
        pc_hid=assignment.pc_hid,
        npc_hid=assignment.npc_hid,
        status=assignment.status,
        active_session_id=assignment_data.get(MongoColumns.ACTIVE_SESSION_ID) or None,
        has_pending_forms=assignment.assignment_id in (pending_assignment_form_ids or set()),
        **metadata,
    )


async def _assignment_summaries(
    provider,
    assignments,
    *,
    pending_assignment_form_ids: set[str] | None = None,
) -> list[AssignmentSummary]:
    summaries = []
    for assignment in assignments:
        summary = await _assignment_summary(provider, assignment, pending_assignment_form_ids=pending_assignment_form_ids)
        if summary is not None:
            summaries.append(summary)
    return summaries


async def _eligible_assignment_options(provider, options) -> list[EligibleAssignmentOption]:
    enriched = []
    for option in options:
        item = await EngineRunManager.enrich_assignment_option_async(provider=provider, option=option)
        enriched.append(EligibleAssignmentOption(**item))
    return enriched


def _pending_form_group_response(group) -> PendingFormGroupResponse:
    return PendingFormGroupResponse(
        group_id=group["group_id"],
        trigger=group["trigger"],
        forms=[form.model_dump(mode="json") for form in group.get("forms", [])],
        assignment_id=group.get("assignment_id"),
    )


async def _next_assignment_state(
    provider,
    *,
    current_assignment,
    eligible_options,
    has_pending_assignment_forms: bool,
    assignment_completed: bool,
    is_open: bool,
    has_pending_initial_forms: bool,
    pending_assignment_form_ids: set[str] | None = None,
) -> NextAssignmentState:
    if has_pending_assignment_forms:
        return NextAssignmentState(mode="blocked", reason="pending_assignment_forms")
    if current_assignment is not None:
        summary = await _assignment_summary(
            provider,
            current_assignment,
            pending_assignment_form_ids=pending_assignment_form_ids,
        )
        reason = current_assignment.status
        if current_assignment.status == "assigned":
            reason = "locked"
        return NextAssignmentState(mode="locked", reason=reason, assignment=summary)
    if eligible_options:
        return NextAssignmentState(
            mode="choice",
            reason="choice_allowed",
            options=await _eligible_assignment_options(provider, eligible_options),
        )
    if assignment_completed:
        return NextAssignmentState(mode="none", reason="complete")
    if not is_open:
        return NextAssignmentState(mode="none", reason="quota_closed")
    if has_pending_initial_forms:
        return NextAssignmentState(mode="blocked", reason="pending_forms")
    return NextAssignmentState(mode="none", reason="unavailable")


def _progress_response(progress: dict) -> ProgressResponse:
    return ProgressResponse(
        total=int(progress["total"]),
        completed=int(progress["completed"]),
        is_complete=bool(progress["is_complete"]),
    )


def _status_response(status_payload: dict) -> RunStatusResponse:
    return RunStatusResponse(
        is_open=bool(status_payload["is_open"]),
        total=int(status_payload["total"]),
        completed=int(status_payload["completed"]),
        per_game={
            str(game_name): GameStatusResponse(
                total=int(counts["total"]),
                completed=int(counts["completed"]),
                in_progress=int(counts["in_progress"]),
            )
            for game_name, counts in dict(status_payload["per_game"]).items()
        },
    )


@router.get("/setup", response_model=SetupResponse)
async def run_setup(request: Request) -> SetupResponse:
    """Return run metadata, form schemas, and current player assignment state."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    config = manager.run_config
    await manager.ensure_run_async(provider=provider)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    player_state = await manager.get_player_state_async(
        provider=provider,
        player_id=player.id,
    )
    current_assignment = player_state["active_assignment"]
    pending_assignment_form_ids = set(player_state.get("pending_assignment_form_ids", []))
    has_pending_assignment_forms = bool(pending_assignment_form_ids)
    pending_form_groups = player_state.get("pending_form_groups", [])
    assignment_completed = bool(player_state["has_finished_run"])
    eligible_options = player_state.get("eligible_assignment_options", [])

    # Surface resumable_session_id so the frontend can show a Resume CTA.
    resumable_session_id: str | None = None
    if current_assignment is not None and current_assignment.status == "in_progress":
        current_assignment_data = getattr(current_assignment, "data", {}) or {}
        resumable_session_id = current_assignment_data.get(MongoColumns.ACTIVE_SESSION_ID) or None

    progress = await manager.compute_progress_async(provider=provider)
    is_open = not progress["is_complete"]
    has_pending_initial_forms = any(group["trigger"]["event"] == "before_all_assignments" for group in pending_form_groups)
    return SetupResponse(
        run_name=config.name,
        description=config.description,
        is_open=is_open,
        forms=[form.model_dump(mode="json") for form in config.forms],
        pending_form_groups=[_pending_form_group_response(group) for group in pending_form_groups],
        progress=_progress_response(progress),
        current_assignment=await _assignment_summary(
            provider,
            current_assignment,
            pending_assignment_form_ids=pending_assignment_form_ids,
        ),
        assignment_completed=assignment_completed,
        next_assignment=await _next_assignment_state(
            provider,
            current_assignment=current_assignment,
            eligible_options=eligible_options,
            has_pending_assignment_forms=has_pending_assignment_forms,
            assignment_completed=assignment_completed,
            is_open=is_open,
            has_pending_initial_forms=has_pending_initial_forms,
            pending_assignment_form_ids=pending_assignment_form_ids,
        ),
        allow_choice_if_multiple=config.assignment_strategy.allow_choice_if_multiple,
        require_completion=config.assignment_strategy.require_completion,
        eligible_assignment_options=await _eligible_assignment_options(provider, eligible_options),
        assignments=await _assignment_summaries(
            provider,
            player_state.get("assignments", []),
            pending_assignment_form_ids=pending_assignment_form_ids,
        ),
        resumable_session_id=resumable_session_id,
    )


@router.post("/forms/submit", response_model=FormSubmitResponse)
async def submit_run_form_group(
    body: FormSubmitRequest,
    request: Request,
) -> FormSubmitResponse:
    """Store responses for one pending run form group."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    try:
        group = await manager.submit_form_group_async(
            provider=provider,
            player_id=player.id,
            group_id=body.group_id,
            responses=body.responses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return FormSubmitResponse(
        group_id=group["group_id"],
        trigger=group["trigger"],
        assignment_id=group.get("assignment_id"),
    )


@router.post("/sessions", response_model=CreateGameResponse)
async def create_run_session(
    body: AssignmentSessionRequest,
    request: Request,
) -> CreateGameResponse:
    """Create or resume a session for one run assignment."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    registry = get_registry_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))

    try:
        entry, _assignment = await manager.start_assignment_session_async(
            provider=provider,
            registry=registry,
            player=player,
            source=body.source,
            assignment_id=body.assignment_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return CreateGameResponse(
        session_id=entry.session_id,
        status="active",
        ws_path=f"/api/play/game/{entry.session_id}/ws",
    )


@router.get("/progress", response_model=ProgressResponse)
async def run_progress(request: Request) -> ProgressResponse:
    """Return the current finite progress for the run."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    await require_player_async(provider=provider, api_key=api_key_from_request(request))
    progress = await manager.compute_progress_async(provider=provider)
    await manager.ensure_run_async(provider=provider)
    return _progress_response(progress)


@router.get("/eligible-options", response_model=EligibleAssignmentOptionsResponse)
async def get_eligible_options(request: Request) -> EligibleAssignmentOptionsResponse:
    """Return eligible game/PC/NPC triplets for the authenticated player."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    options = await manager.get_eligible_options_async(
        provider=provider,
        player=player,
    )
    return EligibleAssignmentOptionsResponse(options=[option for option in await _eligible_assignment_options(provider, options)])


@router.post("/assignments/select", response_model=AssignmentSummary)
async def select_assignment(
    body: SelectAssignmentRequest,
    request: Request,
) -> AssignmentSummary:
    """Create an assignment for the authenticated player based on their explicit triplet selection."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    try:
        assignment = await manager.create_player_choice_assignment_async(
            provider=provider,
            player=player,
            game_name=body.game_name,
            pc_hid=body.pc_hid,
            npc_hid=body.npc_hid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _assignment_summary(provider, assignment)


@router.get("/status", response_model=RunStatusResponse)
async def run_status(request: Request) -> RunStatusResponse:
    """Return the current aggregate status for the run."""
    manager = _get_run_manager(request)
    provider = get_provider_from_request(request)
    await require_player_async(provider=provider, api_key=api_key_from_request(request))
    await manager.ensure_run_async(provider=provider)
    status_payload = await manager.compute_status_async(provider=provider)
    return _status_response(status_payload)
