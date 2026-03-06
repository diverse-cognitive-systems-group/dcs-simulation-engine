import logging
import os
from contextlib import asynccontextmanager

from dcs_db.engine import dispose_engine
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from dcs_simulation_engine.api.dal.postgress import PGDataLayer
from dcs_simulation_engine.api.requests import AdvanceRequest, APIRequest, CloseRequest, StatusRequest
from dcs_simulation_engine.api.responses import APIResponse, CreatedResponse
from dcs_simulation_engine.api.routers.users import make_router as make_users_router
from dcs_simulation_engine.api.session import SessionManager
from dcs_simulation_engine.game.llm import OpenRouterClient
from dcs_simulation_engine.game.prompt import EXPLORE_AI_PROMPT, RPG_CHAT_AI_PROMPT, Explore, RPGChat

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"

load_dotenv()
api_key = os.environ["OPENROUTER_API_KEY"]

GAME_TYPES = {
    "explore": (Explore, EXPLORE_AI_PROMPT),
    "rpg-chat": (RPGChat, RPG_CHAT_AI_PROMPT),
}

sessions = SessionManager()
dal = PGDataLayer()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the session TTL sweep on startup and stop it on shutdown."""
    async with sessions:
        yield
    await dispose_engine()


app = FastAPI(lifespan=lifespan)
app.include_router(make_users_router(dal), prefix="/users")


class CreateSessionRequest(BaseModel):
    api_key: str
    model: str = DEFAULT_MODEL
    game: str = "explore"


@app.post("/sessions")
async def create_session(body: CreateSessionRequest) -> JSONResponse:
    """Create a new session and return its ID."""
    user_id = await dal.authenticate(api_key=body.api_key)
    if user_id is None:
        return JSONResponse({"error": "Invalid access key"}, status_code=401)

    model = body.model
    game = body.game
    if game not in GAME_TYPES:
        return JSONResponse({"error": f"Unknown game type '{game}'. Choose from: {list(GAME_TYPES)}"}, status_code=400)
    game_class, prompt = GAME_TYPES[game]
    client = OpenRouterClient(model=model, system_prompt=prompt, api_key=api_key)
    session = sessions.add(game_class(client), user_id=user_id)
    await dal.create_session(session_id=session.id, user_id=user_id, game_name=game)
    return JSONResponse(CreatedResponse(session_id=session.id, status=session.status)._asdict())


@app.websocket("/sessions/{session_id}/ws")
async def session_ws(websocket: WebSocket, session_id: str, api_key: str | None = None) -> None:
    """WebSocket endpoint for interacting with a session."""
    await websocket.accept()

    if not api_key:
        await APIResponse.error(websocket, exception="Missing access key")
        await websocket.close()
        return

    user_id = await dal.authenticate(api_key=api_key)
    if user_id is None:
        await APIResponse.error(websocket, exception="Invalid access key")
        await websocket.close()
        return

    try:
        session = sessions[session_id]
    except KeyError:
        await APIResponse.error(websocket, exception=f"Session {session_id} not found")
        await websocket.close()
        return

    if session.user_id != user_id:
        await APIResponse.error(websocket, exception="Unauthorized for this session")
        await websocket.close()
        return

    try:
        # Send opening message
        state = await session.game.advance(None)
        sessions.touch(session_id)
        try:
            await dal.log_message(session_id=session_id, role="ai", content=state.message)
        except Exception:
            logger.exception("Failed to log opening message for session %s", session_id)
        await APIResponse.message(websocket, text=state.message, awaiting=state.awaiting)

        while True:
            req = APIRequest.parse(await websocket.receive_text())

            match req:
                case AdvanceRequest():
                    if session.status == "closed":
                        await APIResponse.error(websocket, exception="Session is closed")
                        continue
                    try:
                        await dal.log_message(session_id=session_id, role="human", content=req.text)
                    except Exception:
                        logger.exception("Failed to log human message for session %s", session_id)
                    state = await session.game.advance(req.text)
                    sessions.touch(session_id)
                    try:
                        await dal.log_message(session_id=session_id, role="ai", content=state.message)
                    except Exception:
                        logger.exception("Failed to log ai message for session %s", session_id)
                    await APIResponse.message(websocket, text=state.message, awaiting=state.awaiting)

                case StatusRequest():
                    await APIResponse.status(websocket, session_id=session.id, status=session.status)

                case CloseRequest():
                    session.game.reset()
                    sessions.close(session_id)
                    await APIResponse.closed(websocket)
                    break

    except WebSocketDisconnect:
        # Client disconnected without a close request — remove immediately rather than waiting for TTL
        sessions.pop(session_id)

    except Exception as e:
        await APIResponse.error(websocket, exception=e)
        raise
