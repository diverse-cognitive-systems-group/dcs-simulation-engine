"""Gameplay session creation and WebSocket interaction endpoints."""

import asyncio
from contextlib import suppress
from typing import Any

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    api_key_from_websocket,
    get_default_experiment_name_from_request,
    get_provider_from_request,
    get_provider_from_websocket,
    get_registry_from_request,
    get_registry_from_websocket,
    get_server_mode_from_request,
    get_server_mode_from_websocket,
    is_remote_management_enabled_from_request,
    maybe_await,
    require_player_async,
)
from dcs_simulation_engine.api.models import (
    CharacterChoice,
    CreateGameRequest,
    CreateGameResponse,
    GameSetupOptionsResponse,
    WSAdvanceRequest,
    WSCloseRequest,
    WSErrorFrame,
    WSEventFrame,
    WSSessionMetaFrame,
    WSStatusFrame,
    WSStatusRequest,
    WSTurnEndFrame,
    parse_ws_auth,
    parse_ws_request,
)
from dcs_simulation_engine.core.experiment_manager import ExperimentManager
from dcs_simulation_engine.core.session_manager import SessionManager
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from loguru import logger

router = APIRouter(prefix="/api/play", tags=["play"])


def _session_status(entry_status: str, exited: bool) -> str:
    """Compute user-facing status for session responses."""
    if entry_status == "closed" or exited:
        return "closed"
    return "active"


def _require_generic_play_enabled(request: Request) -> None:
    """Reject generic play paths when the server is running as an experiment-only deployment."""
    if is_remote_management_enabled_from_request(request) and get_default_experiment_name_from_request(request):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generic play is disabled on experiment-only deployments. Use the experiment flow instead.",
        )


async def _reject_if_experiment_gated(*, provider: Any, player_id: str) -> None:
    """Block generic play endpoints for players who are inside an experiment flow."""
    latest_assignment = await ExperimentManager.get_latest_assignment_for_player_async(
        provider=provider,
        player_id=player_id,
    )
    if latest_assignment is None:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            f"Player {player_id} is assigned through experiment '{latest_assignment.experiment_name}'. "
            "Use the experiment flow instead of the generic play endpoints."
        ),
    )


async def _sync_experiment_assignment_if_needed(*, provider: Any, entry: Any) -> None:
    """Update experiment assignment state when a session reaches a terminal state."""
    if entry.experiment_name is None or entry.assignment_id is None:
        return
    await ExperimentManager.handle_session_terminal_state_async(
        provider=provider,
        experiment_name=entry.experiment_name,
        assignment_id=entry.assignment_id,
        exit_reason=entry.manager.exit_reason,
    )


async def _send_error(websocket: WebSocket, detail: str) -> None:
    """Send a standardized error frame to the client."""
    await websocket.send_json(WSErrorFrame(detail=detail).model_dump(mode="json"))


async def _send_events(websocket: WebSocket, session_id: str, events: list[dict[str, Any]]) -> None:
    """Send zero or more event frames for one completed turn."""
    for event in events:
        event_type = str(event.get("type") or "info").lower()
        if event_type not in {"ai", "info", "error", "warning"}:
            event_type = "info"

        frame = WSEventFrame(
            session_id=session_id,
            event_type=event_type,  # type: ignore[arg-type]
            content=str(event.get("content") or ""),
            event_id=str(event.get("event_id")) if event.get("event_id") else None,
        )
        await websocket.send_json(frame.model_dump(mode="json"))


async def _send_turn_end(websocket: WebSocket, session_id: str, *, turns: int, exited: bool) -> None:
    """Send the standardized turn-end frame."""
    frame = WSTurnEndFrame(session_id=session_id, turns=turns, exited=exited)
    await websocket.send_json(frame.model_dump(mode="json"))


async def _send_status(websocket: WebSocket, session_id: str, *, status_value: str, turns: int, exited: bool) -> None:
    """Send the standardized status frame."""
    frame = WSStatusFrame(
        session_id=session_id,
        status=status_value,  # type: ignore[arg-type]
        turns=turns,
        exited=exited,
    )
    await websocket.send_json(frame.model_dump(mode="json"))


async def _finalize_exit_with_retry(*, manager: Any, reason: str, session_id: str, max_attempts: int = 3) -> None:
    """Attempt session finalization with bounded retries."""
    delay_s = 0.2
    for attempt in range(1, max_attempts + 1):
        try:
            await manager.exit_async(reason)
            return
        except Exception:
            logger.exception(
                "Session finalize failed for {} (attempt {}/{})",
                session_id,
                attempt,
                max_attempts,
            )
            if attempt == max_attempts:
                return
            await asyncio.sleep(delay_s)
            delay_s *= 2


def _spawn_background_finalize(*, manager: Any, reason: str, session_id: str) -> asyncio.Task[None]:
    """Run finalize-with-retry in background so close ACK isn't blocked by durability."""
    task = asyncio.create_task(_finalize_exit_with_retry(manager=manager, reason=reason, session_id=session_id))

    def _on_done(done_task: asyncio.Task[None]) -> None:
        with suppress(asyncio.CancelledError):
            exc = done_task.exception()
            if exc is not None:
                logger.error("Background finalize task crashed for {}: {}", session_id, exc)

    task.add_done_callback(_on_done)
    return task


@router.get("/setup/{game_name}", response_model=GameSetupOptionsResponse)
async def setup_options(game_name: str, request: Request) -> GameSetupOptionsResponse:
    """Return setup-ready authorization and valid character choices for a game."""
    _require_generic_play_enabled(request)
    provider = get_provider_from_request(request)
    server_mode = get_server_mode_from_request(request)
    player_id: str | None = None
    if server_mode == "standard":
        player = await require_player_async(provider=provider, api_key=api_key_from_request(request))
        player_id = player.id
        await _reject_if_experiment_gated(provider=provider, player_id=player.id)

    try:
        game_config = SessionManager.get_game_config_cached(game_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    get_valid = getattr(game_config, "get_valid_characters_async", None)
    if get_valid is None:
        valid_pcs, valid_npcs = await maybe_await(game_config.get_valid_characters(player_id=player_id, provider=provider))
    else:
        valid_pcs, valid_npcs = await maybe_await(get_valid(player_id=player_id, provider=provider))
    pcs = [CharacterChoice(hid=hid, label=label) for label, hid in valid_pcs]
    npcs = [CharacterChoice(hid=hid, label=label) for label, hid in valid_npcs]

    if not pcs:
        return GameSetupOptionsResponse(
            game=game_config.name,
            allowed=True,
            can_start=False,
            denial_reason="no_valid_pc",
            message=("No valid player characters are available for your account for this game."),
            pcs=pcs,
            npcs=npcs,
        )
    if not npcs:
        return GameSetupOptionsResponse(
            game=game_config.name,
            allowed=True,
            can_start=False,
            denial_reason="no_valid_npc",
            message=("No valid non-player characters are available for your account for this game."),
            pcs=pcs,
            npcs=npcs,
        )

    return GameSetupOptionsResponse(
        game=game_config.name,
        allowed=True,
        can_start=True,
        denial_reason=None,
        message=None,
        pcs=pcs,
        npcs=npcs,
    )


@router.post("/game", response_model=CreateGameResponse)
async def create_game(body: CreateGameRequest, request: Request) -> CreateGameResponse:
    """Create a session-owned game instance and return websocket connect info."""
    _require_generic_play_enabled(request)
    provider = get_provider_from_request(request)
    registry = get_registry_from_request(request)
    server_mode = get_server_mode_from_request(request)
    player_id: str | None = None
    if server_mode == "standard":
        player = await require_player_async(provider=provider, api_key=body.api_key)
        player_id = player.id
        await _reject_if_experiment_gated(provider=provider, player_id=player.id)

    try:
        manager = await SessionManager.create_async(
            game=body.game,
            provider=provider,
            source=body.source,
            pc_choice=body.pc_choice,
            npc_choice=body.npc_choice,
            player_id=player_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to create session manager")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    entry = registry.add(player_id=player_id, game_name=manager.game_config.name, manager=manager)
    start_hook = getattr(manager, "start_persistence", None)
    if start_hook is not None:
        await maybe_await(start_hook(session_id=entry.session_id))

    return CreateGameResponse(
        session_id=entry.session_id,
        status="active",
        ws_path=f"/api/play/game/{entry.session_id}/ws",
    )


@router.websocket("/game/{session_id}/ws")
async def play_ws(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for game play requests and streamed turn events."""
    await websocket.accept()

    provider = get_provider_from_websocket(websocket)
    registry = get_registry_from_websocket(websocket)
    server_mode = get_server_mode_from_websocket(websocket)

    try:
        entry = registry.get(session_id)
        if entry is None:
            await _send_error(websocket, f"Session {session_id} not found")
            await websocket.close()
            return

        if server_mode == "standard":
            # Try header-based auth first (Python client), then first-message auth (browser).
            api_key = api_key_from_websocket(websocket)
            if api_key is None:
                raw = await websocket.receive_text()
                auth_frame = parse_ws_auth(raw)
                if auth_frame is not None:
                    api_key = auth_frame.api_key

            player = await require_player_async(provider=provider, api_key=api_key)
            if entry.player_id != player.id:
                await _send_error(websocket, "Unauthorized for this session")
                await websocket.close()
                return

        # Send session metadata (pc/npc) immediately after auth, before any events.
        game = entry.manager.game
        pc = getattr(game, "_pc", None)
        npc = getattr(game, "_npc", None)
        game_config = SessionManager.get_game_config_cached(entry.game_name)
        has_game_feedback = any(f.before_or_after == "after" for f in game_config.forms)
        meta_frame = WSSessionMetaFrame(
            session_id=session_id,
            pc_hid=getattr(pc, "hid", None),
            npc_hid=getattr(npc, "hid", None),
            has_game_feedback=has_game_feedback,
        )
        await websocket.send_json(meta_frame.model_dump(mode="json"))

        if not entry.opening_sent and entry.status != "closed":
            opening_events = await entry.manager.step_async(None)
            registry.mark_opening_sent(session_id)
            registry.touch(session_id)
            if entry.manager.exited:
                registry.close(session_id)
                await _sync_experiment_assignment_if_needed(provider=provider, entry=entry)

            await _send_events(websocket, session_id, opening_events)
            await _send_turn_end(
                websocket,
                session_id,
                turns=entry.manager.turns,
                exited=entry.manager.exited,
            )

        while True:
            raw_message = await websocket.receive_text()
            if parse_ws_auth(raw_message) is not None:
                continue
            try:
                req = parse_ws_request(raw_message)
            except ValueError as exc:
                await _send_error(websocket, str(exc))
                continue

            if isinstance(req, WSAdvanceRequest):
                if _session_status(entry.status, entry.manager.exited) == "closed":
                    await _send_error(websocket, "Session is closed")
                    continue

                events = await entry.manager.step_async(req.text)
                registry.touch(session_id)
                if entry.manager.exited:
                    registry.close(session_id)
                    await _sync_experiment_assignment_if_needed(provider=provider, entry=entry)

                await _send_events(websocket, session_id, events)
                await _send_turn_end(
                    websocket,
                    session_id,
                    turns=entry.manager.turns,
                    exited=entry.manager.exited,
                )
                continue

            if isinstance(req, WSStatusRequest):
                status_value = _session_status(entry.status, entry.manager.exited)
                await _send_status(
                    websocket,
                    session_id,
                    status_value=status_value,
                    turns=entry.manager.turns,
                    exited=entry.manager.exited,
                )
                continue

            if isinstance(req, WSCloseRequest):
                if not entry.manager.exited:
                    if entry.assignment_id is not None:
                        await _finalize_exit_with_retry(
                            manager=entry.manager,
                            reason="received close request",
                            session_id=session_id,
                        )
                    else:
                        _spawn_background_finalize(
                            manager=entry.manager,
                            reason="received close request",
                            session_id=session_id,
                        )
                registry.close(session_id)
                await _sync_experiment_assignment_if_needed(provider=provider, entry=entry)
                await websocket.send_json({"type": "closed", "session_id": session_id})
                await websocket.close()
                return

    except WebSocketDisconnect as exc:
        entry = registry.get(session_id)
        if entry is not None and not entry.manager.exited:
            try:
                await _finalize_exit_with_retry(
                    manager=entry.manager,
                    reason="websocket_disconnect",
                    session_id=session_id,
                )
                registry.close(session_id)
                await _sync_experiment_assignment_if_needed(provider=provider, entry=entry)
            except Exception:
                logger.exception("Failed to finalize session after websocket disconnect: {}", session_id)
        logger.info(
            "WebSocket disconnected for session {} (code={}, reason={})",
            session_id,
            exc.code,
            exc.reason,
        )

    except Exception:
        entry = registry.get(session_id)
        if entry is not None and not entry.manager.exited:
            try:
                await _finalize_exit_with_retry(
                    manager=entry.manager,
                    reason="server_error",
                    session_id=session_id,
                )
                registry.close(session_id)
                await _sync_experiment_assignment_if_needed(provider=provider, entry=entry)
            except Exception:
                logger.exception("Failed to finalize session after internal websocket error: {}", session_id)
        logger.exception("Unhandled websocket error for session {}", session_id)
        try:
            await _send_error(websocket, "Internal server error")
            await websocket.close()
        except Exception:
            logger.debug("WebSocket already closed while sending internal error frame")
