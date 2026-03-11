"""Gameplay session creation and WebSocket interaction endpoints."""

from dcs_simulation_engine.api.auth import (
    api_key_from_request,
    api_key_from_websocket,
    authenticate_player,
    get_provider_from_request,
    get_provider_from_websocket,
    get_registry_from_request,
    get_registry_from_websocket,
    require_player,
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
    WSStatusFrame,
    WSStatusRequest,
    WSTurnEndFrame,
    parse_ws_auth,
    parse_ws_request,
)
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import DataProvider
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from loguru import logger

router = APIRouter(prefix="/api/play", tags=["play"])


def _session_status(entry_status: str, exited: bool) -> str:
    """Compute user-facing status for session responses."""
    if entry_status == "closed" or exited:
        return "closed"
    return "active"


async def _send_error(websocket: WebSocket, detail: str) -> None:
    """Send a standardized error frame to the client."""
    await websocket.send_json(WSErrorFrame(detail=detail).model_dump(mode="json"))


async def _send_events(websocket: WebSocket, session_id: str, events: list[dict[str, str]]) -> None:
    """Send zero or more event frames for one completed turn."""
    for event in events:
        event_type = str(event.get("type") or "info").lower()
        if event_type not in {"ai", "info", "error", "warning"}:
            event_type = "info"

        frame = WSEventFrame(
            session_id=session_id,
            event_type=event_type,  # type: ignore[arg-type]
            content=str(event.get("content") or ""),
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


def _build_setup_options(
    *,
    game_name: str,
    player_id: str,
    provider: DataProvider,
) -> GameSetupOptionsResponse:
    """Compute setup authorization + character choices for one player and game."""
    try:
        game_config_path = get_game_config(game_name)
        game_config = GameConfig.load(game_config_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not game_config.is_player_allowed(player_id=player_id, provider=provider):
        return GameSetupOptionsResponse(
            game=game_config.name,
            allowed=False,
            can_start=False,
            denial_reason="not_allowed",
            message="Your account is not authorized to access this game.",
            pcs=[],
            npcs=[],
        )

    valid_pcs, valid_npcs = game_config.get_valid_characters(player_id=player_id, provider=provider)
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


@router.get("/setup/{game_name}", response_model=GameSetupOptionsResponse)
def setup_options(game_name: str, request: Request) -> GameSetupOptionsResponse:
    """Return setup-ready authorization and valid character choices for a game."""
    provider = get_provider_from_request(request)
    player = require_player(provider=provider, api_key=api_key_from_request(request))
    return _build_setup_options(game_name=game_name, player_id=player.id, provider=provider)


@router.post("/game", response_model=CreateGameResponse)
def create_game(body: CreateGameRequest, request: Request) -> CreateGameResponse:
    """Create a session-owned game instance and return websocket connect info."""
    provider = get_provider_from_request(request)
    registry = get_registry_from_request(request)
    player = require_player(provider=provider, api_key=body.api_key)

    try:
        manager = SessionManager.create(
            game=body.game,
            provider=provider,
            source=body.source,
            pc_choice=body.pc_choice,
            npc_choice=body.npc_choice,
            player_id=player.id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to create session manager")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    entry = registry.add(player_id=player.id, game_name=manager.game_config.name, manager=manager)
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

    try:
        # Try header-based auth first (Python client), then first-message auth (browser).
        api_key = api_key_from_websocket(websocket)
        if api_key is None:
            raw = await websocket.receive_text()
            auth_frame = parse_ws_auth(raw)
            if auth_frame is not None:
                api_key = auth_frame.api_key

        player = authenticate_player(provider=provider, api_key=api_key)
        if player is None:
            await _send_error(websocket, "Invalid access key")
            await websocket.close()
            return

        entry = registry.get(session_id)
        if entry is None:
            await _send_error(websocket, f"Session {session_id} not found")
            await websocket.close()
            return

        if entry.player_id != player.id:
            await _send_error(websocket, "Unauthorized for this session")
            await websocket.close()
            return

        if not entry.opening_sent and entry.status != "closed":
            opening_events = await entry.manager.step_async(None)
            registry.mark_opening_sent(session_id)
            registry.touch(session_id)
            if entry.manager.exited:
                registry.close(session_id)

            await _send_events(websocket, session_id, opening_events)
            await _send_turn_end(
                websocket,
                session_id,
                turns=entry.manager.turns,
                exited=entry.manager.exited,
            )

        while True:
            raw_message = await websocket.receive_text()
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
                    entry.manager.exit("received close request")
                registry.close(session_id)
                await websocket.send_json({"type": "closed", "session_id": session_id})
                await websocket.close()
                return

    except WebSocketDisconnect as exc:
        logger.info(
            "WebSocket disconnected for session {} (code={}, reason={})",
            session_id,
            exc.code,
            exc.reason,
        )

    except Exception:
        logger.exception("Unhandled websocket error for session {}", session_id)
        try:
            await _send_error(websocket, "Internal server error")
            await websocket.close()
        except Exception:
            logger.debug("WebSocket already closed while sending internal error frame")
