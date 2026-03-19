"""Experiment-scoped endpoints for assignment-driven study flows."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    get_provider_from_request,
    get_registry_from_request,
    require_player_async,
    require_standard_mode_from_request,
)
from dcs_simulation_engine.api.models import (
    CreateGameResponse,
    ExperimentAssignmentSummary,
    ExperimentGameStatusResponse,
    ExperimentPlayerRequest,
    ExperimentPlayerResponse,
    ExperimentPostPlayRequest,
    ExperimentProgressResponse,
    ExperimentSessionRequest,
    ExperimentSetupResponse,
    ExperimentStatusResponse,
)
from dcs_simulation_engine.core.experiment_manager import ExperimentManager
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _assignment_summary(assignment) -> ExperimentAssignmentSummary | None:
    if assignment is None:
        return None
    return ExperimentAssignmentSummary(
        assignment_id=assignment.assignment_id,
        game_name=assignment.game_name,
        character_hid=assignment.character_hid,
        status=assignment.status,
    )


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
    provider = get_provider_from_request(request)
    config = ExperimentManager.get_experiment_config_cached(experiment_name)
    await ExperimentManager.ensure_experiment_async(provider=provider, experiment_name=config.name)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    current_assignment = None
    pending_post_play = False
    assignment_completed = False
    player_state = await ExperimentManager.get_player_state_async(
        provider=provider,
        experiment_name=config.name,
        player_id=player.id,
    )
    current_assignment = player_state["active_assignment"]
    pending_post_play = player_state["pending_post_play"] is not None
    assignment_completed = bool(player_state["has_finished_experiment"])

    progress = await ExperimentManager.compute_progress_async(provider=provider, experiment_name=config.name)
    return ExperimentSetupResponse(
        experiment_name=config.name,
        description=config.description,
        is_open=not progress["is_complete"],
        forms=[form.model_dump(mode="json") for form in config.forms],
        progress=_progress_response(progress),
        current_assignment=_assignment_summary(current_assignment),
        pending_post_play=pending_post_play,
        assignment_completed=assignment_completed,
    )


@router.post("/{experiment_name}/players", response_model=ExperimentPlayerResponse)
async def register_experiment_player(
    experiment_name: str,
    body: ExperimentPlayerRequest,
    request: Request,
) -> ExperimentPlayerResponse:
    """Store before-play experiment forms for the authenticated participant and generate an assignment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
    try:
        assignment = await ExperimentManager.submit_before_play_async(
            provider=provider,
            experiment_name=experiment_name,
            player_id=player.id,
            responses=body.responses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return ExperimentPlayerResponse(assignment=_assignment_summary(assignment))


@router.post("/{experiment_name}/sessions", response_model=CreateGameResponse)
async def create_experiment_session(
    experiment_name: str,
    body: ExperimentSessionRequest,
    request: Request,
) -> CreateGameResponse:
    """Create a session for the authenticated player's current experiment assignment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
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


@router.post("/{experiment_name}/post-play", response_model=ExperimentAssignmentSummary)
async def submit_experiment_post_play(
    experiment_name: str,
    body: ExperimentPostPlayRequest,
    request: Request,
) -> ExperimentAssignmentSummary:
    """Store the experiment post-play form on the latest completed assignment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    provider = get_provider_from_request(request)
    player = await require_player_async(provider=provider, api_key=api_key_from_request(request))

    try:
        assignment = await ExperimentManager.store_post_play_async(
            provider=provider,
            experiment_name=experiment_name,
            player_id=player.id,
            responses=body.responses,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _assignment_summary(assignment)


@router.get("/{experiment_name}/progress", response_model=ExperimentProgressResponse)
async def experiment_progress(experiment_name: str, request: Request) -> ExperimentProgressResponse:
    """Return the current finite progress for the usability experiment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    provider = get_provider_from_request(request)
    await require_player_async(provider=provider, api_key=api_key_from_request(request))
    progress = await ExperimentManager.compute_progress_async(provider=provider, experiment_name=experiment_name)
    await ExperimentManager.ensure_experiment_async(provider=provider, experiment_name=experiment_name)
    return _progress_response(progress)


@router.get("/{experiment_name}/status", response_model=ExperimentStatusResponse)
async def experiment_status(experiment_name: str, request: Request) -> ExperimentStatusResponse:
    """Return the current aggregate status for one experiment."""
    require_standard_mode_from_request(
        request,
        detail="Experiment endpoints are disabled when the server is running in free play mode.",
    )
    provider = get_provider_from_request(request)
    await require_player_async(provider=provider, api_key=api_key_from_request(request))
    await ExperimentManager.ensure_experiment_async(provider=provider, experiment_name=experiment_name)
    status_payload = await ExperimentManager.compute_status_async(provider=provider, experiment_name=experiment_name)
    return _status_response(status_payload)
