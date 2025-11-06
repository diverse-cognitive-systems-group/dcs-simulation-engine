"""Run-related API routes (create, step, play, state, save, delete)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Response
from loguru import logger

from dcs_simulation_engine.api.deps import (
    get_manager,  # should resolve a RunManager by {run_id}
)
from dcs_simulation_engine.api.models import (
    CharacterSummary,
    CreateRunRequest,
    CreateRunResponse,
    Message,
    PlayRequest,
    PlayResponse,
    RunMeta,
    SaveRequest,
    SaveResponse,
    StateResponse,
    StepRequest,
    StepResponse,
)
from dcs_simulation_engine.api.services.registry import RunRegistry, get_registry
from dcs_simulation_engine.core.run_manager import RunManager

router = APIRouter()


# ---------------------------
# Helpers
# ---------------------------


def _meta(run: RunManager) -> RunMeta:
    return RunMeta(
        name=run.name,
        turns=run.turns,
        runtime_seconds=run.runtime_seconds,
        runtime_string=run.runtime_string,
        exited=run.exited,
        exit_reason=run.exit_reason,
        saved=run.saved,
        output_path=(
            str(run.state.get("output_path")) if run.state.get("output_path") else None
        ),
    )


def _char_summary(obj: Any) -> CharacterSummary:
    """Create CharacterSummary from various object types."""
    # Context pc/npc are dict-like (from db helpers). Be tolerant.
    hid = getattr(obj, "hid", None) or (
        obj.get("hid") if isinstance(obj, Mapping) else None
    )
    name = getattr(obj, "name", None) or (
        obj.get("name") if isinstance(obj, Mapping) else None
    )
    archetype = getattr(obj, "archetype", None) or (
        obj.get("archetype") if isinstance(obj, Mapping) else None
    )
    return CharacterSummary(
        hid=str(hid) if hid is not None else "", name=name, archetype=archetype
    )


def _normalize_messages(state: Dict[str, Any]) -> List[Message]:
    """Convert state['messages'] to List[Message]."""
    msgs = state.get("messages", [])
    out: List[Message] = []
    for m in msgs:
        if isinstance(m, Mapping):
            out.append(
                Message(
                    role=str(m.get("role", "system")), content=str(m.get("content", ""))
                )
            )
        else:
            # best-effort fallback
            role = getattr(m, "role", "system")
            content = getattr(m, "content", str(m))
            out.append(Message(role=str(role), content=str(content)))
    return out


# ---------------------------
# Routes
# ---------------------------


@router.post(
    "/runs/create",
    response_model=CreateRunResponse,
    summary="Create a new run from a game config",
)
def create_run(
    payload: CreateRunRequest, registry: RunRegistry = Depends(get_registry)
) -> CreateRunResponse:
    """Create a new RunManager and register it."""
    try:
        run = RunManager.create(
            game=payload.game,
            source=payload.source,
            pc_choice=payload.pc_choice,
            npc_choice=payload.npc_choice,
            access_key=payload.access_key,
            player_id=payload.player_id,
        )
        registry.add(run.name, run)
        pc = run.context.get("pc")
        npc = run.context.get("npc")
        return CreateRunResponse(
            run_id=run.name,
            game_name=run.game_config.name,
            pc=_char_summary(pc),
            npc=_char_summary(npc),
            meta=_meta(run),
        )
    except Exception as e:
        logger.exception("Failed to create run")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/runs/{run_id}/step",
    response_model=StepResponse,
    summary="Advance one step; optionally pass user input (string or mapping)",
)
def step(
    run_id: str, body: StepRequest, run: RunManager = Depends(get_manager)
) -> StepResponse:
    """Advance the simulation one step."""
    try:
        # RunManager.step supports str or Mapping directly.
        user_input: Optional[Union[str, Mapping[str, Any]]] = body.user_input  # type: ignore[assignment]
        run.step(user_input=user_input)
        state = run.state or {}
        return StepResponse(state=state, meta=_meta(run))
    except Exception as e:
        logger.exception("Step failed")
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/runs/{run_id}/play",
    response_model=PlayResponse,
    summary="Feed a finite list of inputs; steps until exit or inputs exhausted",
)
def play(
    run_id: str, body: PlayRequest, run: RunManager = Depends(get_manager)
) -> PlayResponse:
    """Run play() with a finite list of inputs; server will iterate."""
    try:
        # RunManager.play does not accept max_steps; we emulate by stepping over provided inputs.
        # If you need strict step caps beyond inputs, enforce via stopping_conditions in GameConfig.
        for text in body.inputs:
            if run.exited:
                break
            run.step(user_input=text)
        # If last event was user, one extra step may be needed to let the graph respond.
        if not run.exited and run.state.get("events"):
            last = run.state["events"][-1]
            if getattr(last, "type", None) == "user" or (
                isinstance(last, dict) and last.get("type") == "user"
            ):
                run.step(None)
        return PlayResponse(final_state=run.state or {}, meta=_meta(run))
    except Exception as e:
        logger.exception("Play failed")
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/runs/{run_id}/state",
    response_model=StateResponse,
    summary="Get current run state and metadata",
)
def get_state(run_id: str, run: RunManager = Depends(get_manager)) -> StateResponse:
    """Retrieve the current state snapshot and metadata."""
    return StateResponse(state=run.state or {}, meta=_meta(run))


@router.post(
    "/runs/{run_id}/save",
    response_model=SaveResponse,
    summary="Persist run outputs (filesystem or DB)",
)
def save_outputs(
    run_id: str, body: SaveRequest, run: RunManager = Depends(get_manager)
) -> SaveResponse:
    """Trigger a save to filesystem or DB."""
    try:
        out_path = (
            run.save(path=body.output_dir) if body and body.output_dir else run.save()
        )
        files = [str(out_path)] if out_path else []
        return SaveResponse(
            saved=True, output_path=str(out_path) if out_path else None, files=files
        )
    except Exception as e:
        logger.exception("Save failed")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/runs/{run_id}",
    status_code=204,
    response_class=Response,
)
def delete_run(run_id: str, registry: RunRegistry = Depends(get_registry)) -> Response:
    """Delete a run from the registry."""
    registry.remove(run_id)
    return Response(status_code=204)
