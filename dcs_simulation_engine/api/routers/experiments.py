"""Experiment-scoped endpoints for assignment-driven study flows."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    get_default_experiment_name_from_request,
    get_provider_from_request,
    get_registry_from_request,
    is_remote_management_enabled_from_request,
    require_player_async,
    require_standard_mode_from_request,
)
from dcs_simulation_engine.api.models import (
    CreateGameResponse,
    EligibleAssignmentOption,
    EligibleAssignmentOptionsResponse,
    ExperimentAssignmentSummary,
    ExperimentFormSubmitRequest,
    ExperimentFormSubmitResponse,
    ExperimentGameStatusResponse,
    ExperimentProgressResponse,
    ExperimentSessionRequest,
    ExperimentSetupResponse,
    ExperimentStatusResponse,
    NextAssignmentState,
    PendingFormGroupResponse,
    SelectAssignmentRequest,
)
from dcs_simulation_engine.core.experiment_manager import ExperimentManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _require_allowed_experiment(*, experiment_name: str, request: Request) -> None:
    """Restrict experiment-only deployments to their configured experiment slug."""
    if not is_remote_management_enabled_from_request(request):
        return
    allowed = get_default_experiment_name_from_request(request)
    if allowed is None:
        return
    if experiment_name.strip().lower() != allowed.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Experiment '{experiment_name}' is not hosted on this deployment.",
        )


async def _assignment_summary(
    provider,
    assignment,
    *,
    pending_post_play_ids: set[str] | None = None,
) -> ExperimentAssignmentSummary | None:
    if assignment is None:
        return None
    assignment_data = getattr(assignment, "data", {}) or {}
    metadata = await ExperimentManager.assignment_display_metadata_async(
        provider=provider,
        game_name=assignment.game_name,
        pc_hid=assignment.pc_hid,
        npc_hid=assignment.npc_hid,
    )
    return ExperimentAssignmentSummary(
        assignment_id=assignment.assignment_id,
        game_name=assignment.game_name,
        pc_hid=assignment.pc_hid,
        npc_hid=assignment.npc_hid,
        status=assignment.status,
        active_session_id=assignment_data.get(MongoColumns.ACTIVE_SESSION_ID) or None,
        needs_post_play=assignment.assignment_id in (pending_post_play_ids or set()),
        **metadata,
    )


async def _assignment_summaries(
    provider,
    assignments,
    *,
    pending_post_play_ids: set[str] | None = None,
) -> list[ExperimentAssignmentSummary]:
    summaries = []
    for assignment in assignments:
        summary = await _assignment_summary(provider, assignment, pending_post_play_ids=pending_post_play_ids)
        if summary is not None:
            summaries.append(summary)
    return summaries


async def _eligible_assignment_options(provider, options) -> list[EligibleAssignmentOption]:
    enriched = []
    for option in options:
        item = await ExperimentManager.enrich_assignment_option_async(provider=provider, option=option)
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
    pending_post_play: bool,
    assignment_completed: bool,
    is_open: bool,
    has_submitted_before_forms: bool,
    pending_post_play_ids: set[str] | None = None,
) -> NextAssignmentState:
    if pending_post_play:
        return NextAssignmentState(mode="blocked", reason="pending_post_play")
    if current_assignment is not None:
        summary = await _assignment_summary(
            provider,
            current_assignment,
            pending_post_play_ids=pending_post_play_ids,
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
    if not has_submitted_before_forms:
        return NextAssignmentState(mode="blocked", reason="pending_forms")
    return NextAssignmentState(mode="none", reason="unavailable")


def _progress_response(progress: dict) -> ExperimentProgressResponse:
    return ExperimentProgressResponse(
        total=int(progress["total"]),
        completed=int(progress["completed"]),
        is_complete=bool(progress["is_complete"]),
    )


def _status_response(status_payload: dict) -> ExperimentStatusResponse:
    return ExperimentStatusResponse(
        is_open=bool(status_payload["is_open"]),
        total=int(status_payload["total"]),
        completed=int(status_payload["completed"]),
        per_game={
            str(game_name): ExperimentGameStatusResponse(
                total=int(counts["total"]),
                completed=int(counts["completed"]),
                in_progress=int(counts["in_progress"]),
            )
            for game_name, counts in dict(status_payload["per_game"]).items()
        },
    )


@router.get("/{experiment_name}/setup", response_model=ExperimentSetupResponse)
async def experiment_setup(experiment_name: str, request: Request) -> ExperimentSetupResponse:
    """Return experiment metadata, form schemas, and current player assignment state."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    config = ExperimentManager.get_experiment_config_cached(experiment_name)
    await ExperimentManager.ensure_experiment_async(provider=provider, experiment_name=config.name)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    player_state = await ExperimentManager.get_player_state_async(
        provider=provider,
        experiment_name=config.name,
        player_id=player.id,
    )
    current_assignment = player_state["active_assignment"]
    pending_post_play_ids = set(player_state.get("pending_post_play_ids", []))
    pending_post_play = bool(pending_post_play_ids)
    pending_form_groups = player_state.get("pending_form_groups", [])
    assignment_completed = bool(player_state["has_finished_experiment"])
    eligible_options = player_state.get("eligible_assignment_options", [])

    # Surface resumable_session_id so the frontend can show a Resume CTA.
    resumable_session_id: str | None = None
    if current_assignment is not None and current_assignment.status == "in_progress":
        current_assignment_data = getattr(current_assignment, "data", {}) or {}
        resumable_session_id = current_assignment_data.get(MongoColumns.ACTIVE_SESSION_ID) or None

    progress = await ExperimentManager.compute_progress_async(provider=provider, experiment_name=config.name)
    is_open = not progress["is_complete"]
    has_submitted_before_forms = bool(player_state.get("has_submitted_before_forms"))
    return ExperimentSetupResponse(
        experiment_name=config.name,
        description=config.description,
        is_open=is_open,
        forms=[form.model_dump(mode="json") for form in config.forms],
        pending_form_groups=[_pending_form_group_response(group) for group in pending_form_groups],
        progress=_progress_response(progress),
        current_assignment=await _assignment_summary(
            provider,
            current_assignment,
            pending_post_play_ids=pending_post_play_ids,
        ),
        pending_post_play=pending_post_play,
        before_play_complete=bool(player_state["has_submitted_before_forms"]),
        assignment_completed=assignment_completed,
        next_assignment=await _next_assignment_state(
            provider,
            current_assignment=current_assignment,
            eligible_options=eligible_options,
            pending_post_play=pending_post_play,
            assignment_completed=assignment_completed,
            is_open=is_open,
            has_submitted_before_forms=has_submitted_before_forms,
            pending_post_play_ids=pending_post_play_ids,
        ),
        allow_choice_if_multiple=config.assignment_strategy.allow_choice_if_multiple,
        require_completion=config.assignment_strategy.require_completion,
        has_submitted_before_forms=has_submitted_before_forms,
        eligible_assignment_options=await _eligible_assignment_options(provider, eligible_options),
        assignments=await _assignment_summaries(
            provider,
            player_state.get("assignments", []),
            pending_post_play_ids=pending_post_play_ids,
        ),
        resumable_session_id=resumable_session_id,
    )


@router.post("/{experiment_name}/forms/submit", response_model=ExperimentFormSubmitResponse)
async def submit_experiment_form_group(
    experiment_name: str,
    body: ExperimentFormSubmitRequest,
    request: Request,
) -> ExperimentFormSubmitResponse:
    """Store responses for one pending experiment form group."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    try:
        group = await ExperimentManager.submit_form_group_async(
            provider=provider,
            experiment_name=experiment_name,
            player_id=player.id,
            group_id=body.group_id,
            responses=body.responses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ExperimentFormSubmitResponse(
        group_id=group["group_id"],
        trigger=group["trigger"],
        assignment_id=group.get("assignment_id"),
    )


@router.post("/{experiment_name}/sessions", response_model=CreateGameResponse)
async def create_experiment_session(
    experiment_name: str,
    body: ExperimentSessionRequest,
    request: Request,
) -> CreateGameResponse:
    """Create or resume a session for one experiment assignment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    registry = get_registry_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))

    try:
        entry, _assignment = await ExperimentManager.start_assignment_session_async(
            provider=provider,
            registry=registry,
            experiment_name=experiment_name,
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


@router.get("/{experiment_name}/progress", response_model=ExperimentProgressResponse)
async def experiment_progress(experiment_name: str, request: Request) -> ExperimentProgressResponse:
    """Return the current finite progress for the usability experiment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    await require_player_async(provider=provider, api_key=api_key_from_request(request))
    progress = await ExperimentManager.compute_progress_async(provider=provider, experiment_name=experiment_name)
    await ExperimentManager.ensure_experiment_async(provider=provider, experiment_name=experiment_name)
    return _progress_response(progress)


@router.get("/{experiment_name}/eligible-options", response_model=EligibleAssignmentOptionsResponse)
async def get_eligible_options(experiment_name: str, request: Request) -> EligibleAssignmentOptionsResponse:
    """Return eligible game/PC/NPC triplets for the authenticated player."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    options = await ExperimentManager.get_eligible_options_async(
        provider=provider,
        experiment_name=experiment_name,
        player=player,
    )
    return EligibleAssignmentOptionsResponse(options=[option for option in await _eligible_assignment_options(provider, options)])


@router.post("/{experiment_name}/assignments/select", response_model=ExperimentAssignmentSummary)
async def select_assignment(
    experiment_name: str,
    body: SelectAssignmentRequest,
    request: Request,
) -> ExperimentAssignmentSummary:
    """Create an assignment for the authenticated player based on their explicit triplet selection."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    try:
        assignment = await ExperimentManager.create_player_choice_assignment_async(
            provider=provider,
            experiment_name=experiment_name,
            player=player,
            game_name=body.game_name,
            pc_hid=body.pc_hid,
            npc_hid=body.npc_hid,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return await _assignment_summary(provider, assignment)


@router.get("/{experiment_name}/status", response_model=ExperimentStatusResponse)
async def experiment_status(experiment_name: str, request: Request) -> ExperimentStatusResponse:
    """Return the current aggregate status for one experiment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    _require_allowed_experiment(experiment_name=experiment_name, request=request)
    provider = get_provider_from_request(request)
    await require_player_async(provider=provider, api_key=api_key_from_request(request))
    await ExperimentManager.ensure_experiment_async(provider=provider, experiment_name=experiment_name)
    status_payload = await ExperimentManager.compute_status_async(provider=provider, experiment_name=experiment_name)
    return _status_response(status_payload)
