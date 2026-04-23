"""Python client wrapper for the DCS FastAPI server.

Provides APIClient and SimulationRun for ergonomic use in research scripts.
"""

import json
from typing import Any, Optional, Self
from urllib.parse import urlparse

import httpx
from dcs_simulation_engine.api.models import (
    AuthRequest,
    AuthResponse,
    BranchSessionResponse,
    CharactersListResponse,
    CreateGameRequest,
    CreateGameResponse,
    DeleteCharacterResponse,
    GameSetupOptionsResponse,
    GamesListResponse,
    InferIntentEvaluationResponse,
    RegistrationRequest,
    RegistrationResponse,
    ServerConfigResponse,
    SessionsListResponse,
    UpsertCharacterRequest,
    UpsertCharacterResponse,
    WSAdvanceRequest,
    WSCloseRequest,
    WSClosedFrame,
    WSEventFrame,
    WSReplayEndFrame,
    WSReplayEventFrame,
    WSReplayStartFrame,
    WSSessionMetaFrame,
    WSStatusFrame,
    WSStatusRequest,
    WSTurnEndFrame,
)
from dcs_simulation_engine.errors import APIRequestError
from pydantic import BaseModel
from websockets.sync.client import connect


class SimulationRun:
    """Lightweight wrapper around an active server-side simulation session."""

    def __init__(
        self,
        client: "APIClient",
        session_id: str,
        game_name: str,
        api_key: str | None,
        *,
        resume_on_first_connect: bool = False,
    ) -> None:
        """Initialize a SimulationRun bound to an existing server-side session."""
        self._client = client
        self.session_id = session_id
        self.game_name = game_name
        self._api_key = api_key
        self._resume_on_first_connect = resume_on_first_connect
        self._opened = False
        self._events: list[WSEventFrame] = []
        self._session_meta: WSSessionMetaFrame | None = None
        self._turn_end: WSTurnEndFrame | None = None

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context manager, closing the session silently on error."""
        try:
            self.close()
        except Exception:
            pass

    def step(self, user_input: str = "") -> Self:
        """Advance the simulation by one step."""
        if not self._opened:
            first_text: str | None = user_input if user_input != "" else None
            session_meta, events, turn_end = self._client._ws_open_and_advance(
                session_id=self.session_id,
                api_key=self._api_key,
                text=first_text,
                include_opening=not self._resume_on_first_connect,
                expect_replay=self._resume_on_first_connect,
            )
            self._opened = True
        else:
            session_meta, events, turn_end = self._client._ws_open_and_advance(
                session_id=self.session_id,
                api_key=self._api_key,
                text=user_input,
                include_opening=False,
                expect_replay=True,
            )

        self._session_meta = session_meta
        self._events.extend(events)
        self._turn_end = turn_end
        return self

    def get_state(self) -> Self:
        """Fetch current session status without advancing a turn."""
        session_meta, status_frame = self._client._ws_status(
            session_id=self.session_id,
            api_key=self._api_key,
            include_opening=(not self._opened) and (not self._resume_on_first_connect),
            expect_replay=self._resume_on_first_connect or self._opened,
        )
        self._opened = True
        self._session_meta = session_meta
        # Mirror turn_end shape from status frame for consistent meta access.
        self._turn_end = WSTurnEndFrame(
            session_id=status_frame.session_id,
            turns=status_frame.turns,
            exited=status_frame.exited,
        )
        return self

    def close(self) -> None:
        """Close the server-side session."""
        self._session_meta = self._client._ws_close(
            session_id=self.session_id,
            api_key=self._api_key,
            include_opening=(not self._opened) and (not self._resume_on_first_connect),
            expect_replay=self._resume_on_first_connect or self._opened,
        )
        self._opened = True

    @property
    def is_complete(self) -> bool:
        """True if the simulation has reached an exit condition."""
        return self._turn_end.exited if self._turn_end else False

    @property
    def simulator_output(self) -> Optional[str]:
        """Content of the latest AI event, if any."""
        for event in reversed(self._events):
            if event.event_type == "ai":
                return event.content
        return None

    @property
    def history(self) -> list[WSEventFrame]:
        """All WSEventFrames received so far, in order."""
        return list(self._events)

    @property
    def session_meta(self) -> WSSessionMetaFrame | None:
        """Most recent session metadata frame received from the server."""
        return self._session_meta

    @property
    def turns(self) -> int:
        """Number of completed turns, or 0 if no turn has ended yet."""
        return self._turn_end.turns if self._turn_end else 0


class APIClient:
    """Client for the DCS FastAPI server."""

    def __init__(self, url: str = "http://localhost:8080", api_key: str = "", timeout: float = 30.0) -> None:
        """Initialize the API client with a base URL, default API key, and request timeout."""
        self._base_url = url.rstrip("/")
        self._default_api_key = api_key
        self._http = httpx.Client(base_url=self._base_url, timeout=timeout)

    def close(self) -> None:
        """Close the underlying HTTP client transport."""
        self._http.close()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the context manager, closing the HTTP client."""
        self.close()

    def register_player(self, body: RegistrationRequest) -> RegistrationResponse:
        """Register a new player and return player_id + api_key."""
        return self._request("POST", "/api/player/registration", body, RegistrationResponse)

    def auth(self, *, api_key: Optional[str] = None) -> AuthResponse:
        """Validate an API key and return player_id + authenticated."""
        key = self._resolve_api_key(api_key)
        assert key is not None
        return self._request("POST", "/api/player/auth", AuthRequest(api_key=key), AuthResponse)

    def server_config(self) -> ServerConfigResponse:
        """Fetch server capability flags for the active runtime mode."""
        return self._request("GET", "/api/server/config", None, ServerConfigResponse)

    def list_sessions(self, *, api_key: Optional[str] = None) -> SessionsListResponse:
        """List active in-memory sessions for the authenticated player."""
        key = self._resolve_api_key(api_key)
        assert key is not None
        return self._request(
            "GET",
            "/api/sessions/list",
            None,
            SessionsListResponse,
            headers={"Authorization": f"Bearer {key}"},
        )

    def request_infer_intent_evaluation(
        self,
        session_id: str,
        *,
        api_key: Optional[str] = None,
    ) -> InferIntentEvaluationResponse:
        """Generate or fetch the cached Infer Intent evaluation for one completed session."""
        key = self._resolve_api_key(api_key, required=False)
        headers: dict[str, str] = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return self._request(
            "POST",
            f"/api/sessions/{session_id}/infer-intent/evaluation",
            None,
            InferIntentEvaluationResponse,
            headers=headers,
        )

    def list_games(self) -> GamesListResponse:
        """List available games."""
        return self._request("GET", "/api/games/list", None, GamesListResponse)

    def list_characters(self) -> CharactersListResponse:
        """List available characters."""
        return self._request("GET", "/api/characters/list", None, CharactersListResponse)

    def create_character(self, body: UpsertCharacterRequest) -> UpsertCharacterResponse:
        """Create a new character. Returns character_id."""
        return self._request("POST", "/api/characters", body, UpsertCharacterResponse)

    def update_character(self, character_id: str, body: UpsertCharacterRequest) -> UpsertCharacterResponse:
        """Update an existing character by id. Returns character_id."""
        return self._request("PUT", f"/api/characters/{character_id}", body, UpsertCharacterResponse)

    def delete_character(self, character_id: str) -> DeleteCharacterResponse:
        """Delete a character by id. Returns character_id."""
        return self._request("DELETE", f"/api/characters/{character_id}", None, DeleteCharacterResponse)

    def start_game(self, body: CreateGameRequest) -> SimulationRun:
        """Create a new simulation session and return a SimulationRun."""
        key = self._resolve_api_key(body.api_key, required=False)
        response = self._request("POST", "/api/play/game", body, CreateGameResponse)
        return SimulationRun(client=self, session_id=response.session_id, game_name=body.game, api_key=key)

    def branch_session(self, session_id: str, *, api_key: Optional[str] = None) -> SimulationRun:
        """Create a paused child branch session and return a resumed-style SimulationRun."""
        key = self._resolve_api_key(api_key, required=False)
        headers: dict[str, str] = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        response = self._request(
            "POST",
            f"/api/sessions/{session_id}/branch",
            None,
            BranchSessionResponse,
            headers=headers,
        )
        return SimulationRun(
            client=self,
            session_id=response.session_id,
            game_name=response.game_name,
            api_key=key,
            resume_on_first_connect=True,
        )

    def setup_options(self, *, game_name: str, api_key: Optional[str] = None) -> GameSetupOptionsResponse:
        """Fetch setup authorization and valid character choices for a game."""
        key = self._resolve_api_key(api_key, required=False)
        headers: dict[str, str] = {}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        return self._request(
            "GET",
            f"/api/play/setup/{game_name}",
            None,
            GameSetupOptionsResponse,
            headers=headers,
        )

    def health(self) -> dict:
        """Check server liveness."""
        response = self._http.get("/healthz")
        response.raise_for_status()
        return response.json()

    def _resolve_api_key(self, api_key: Optional[str], *, required: bool = True) -> str | None:
        key = (api_key or self._default_api_key).strip()
        if not key and required:
            raise APIRequestError("API key is required.")
        return key or None

    def _request(
        self,
        method: str,
        path: str,
        body: BaseModel | None,
        response_model: type[BaseModel],
        **kwargs: Any,
    ) -> Any:
        """Send an HTTP request with an optional Pydantic body and parse the response into a model."""
        try:
            if body is not None:
                kwargs["content"] = body.model_dump_json()
                kwargs.setdefault("headers", {})["Content-Type"] = "application/json"
            response = self._http.request(method, path, **kwargs)
            response.raise_for_status()
            return response_model.model_validate_json(response.text)
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                payload = exc.response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("detail") or payload.get("error") or detail)
            except Exception:
                pass
            raise APIRequestError(detail) from exc
        except httpx.HTTPError as exc:
            raise APIRequestError(str(exc)) from exc

    def _build_ws_url(self, *, session_id: str) -> str:
        parsed = urlparse(self._base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}/api/play/game/{session_id}/ws"

    def _recv_frame(
        self,
        ws: Any,
    ) -> (
        WSEventFrame
        | WSSessionMetaFrame
        | WSReplayStartFrame
        | WSReplayEventFrame
        | WSReplayEndFrame
        | WSTurnEndFrame
        | WSStatusFrame
        | WSClosedFrame
    ):
        """Receive one WebSocket frame and parse it into a typed model.

        Raises APIRequestError on non-text frames, non-object JSON, or
        server-side error frames (type="error").
        """
        raw = ws.recv()
        if not isinstance(raw, str):
            raise APIRequestError("Expected text websocket frame")

        data = json.loads(raw)
        if not isinstance(data, dict):
            raise APIRequestError("Expected JSON object websocket frame")

        # Server signals protocol/auth errors with a dedicated error frame type.
        if data.get("type") == "error":
            raise APIRequestError(str(data.get("detail") or data.get("message") or "Unknown websocket error"))

        frame_type = data.get("type")
        if frame_type == "session_meta":
            return WSSessionMetaFrame.model_validate(data)
        if frame_type == "event":
            return WSEventFrame.model_validate(data)
        if frame_type == "replay_start":
            return WSReplayStartFrame.model_validate(data)
        if frame_type == "replay_event":
            return WSReplayEventFrame.model_validate(data)
        if frame_type == "replay_end":
            return WSReplayEndFrame.model_validate(data)
        if frame_type == "turn_end":
            return WSTurnEndFrame.model_validate(data)
        if frame_type == "status":
            return WSStatusFrame.model_validate(data)
        if frame_type == "closed":
            return WSClosedFrame.model_validate(data)

        raise APIRequestError(f"Unexpected websocket frame type: {frame_type!r}")

    def _recv_session_meta(self, ws: Any) -> WSSessionMetaFrame:
        """Receive the required session metadata frame sent at the start of each WS connection."""
        frame = self._recv_frame(ws)
        if not isinstance(frame, WSSessionMetaFrame):
            raise APIRequestError("Expected session_meta websocket frame")
        return frame

    def _drain_replay(self, ws: Any, *, replay_start_consumed: bool = False) -> None:
        """Discard the replay burst the server sends when resuming a paused session."""
        if not replay_start_consumed:
            frame = self._recv_frame(ws)
            if not isinstance(frame, WSReplayStartFrame):
                raise APIRequestError("Expected replay_start websocket frame")
        while True:
            frame = self._recv_frame(ws)
            if isinstance(frame, WSReplayEventFrame):
                continue
            if isinstance(frame, WSReplayEndFrame):
                return
            raise APIRequestError("Expected replay_event or replay_end websocket frame")

    def _recv_until_turn_end(self, ws: Any) -> tuple[list[WSEventFrame], WSTurnEndFrame]:
        """Drain frames until the server signals the end of a turn.

        The server streams zero or more WSEventFrame (AI output, info, etc.)
        followed by exactly one terminal frame:
          - WSTurnEndFrame — normal turn completion; may or may not be the final turn
          - WSClosedFrame  — session was closed mid-stream (e.g. game exited)

        Returns (events, turn_end).
        """
        events: list[WSEventFrame] = []
        while True:
            frame = self._recv_frame(ws)
            if isinstance(frame, WSReplayStartFrame):
                self._drain_replay(ws, replay_start_consumed=True)
                continue
            if isinstance(frame, WSEventFrame):
                # Accumulate content frames; event_type distinguishes ai/info/warning/error.
                events.append(frame)
                continue
            if isinstance(frame, WSTurnEndFrame):
                return events, frame
            if isinstance(frame, WSClosedFrame):
                # Session was already closed before a full turn completed; synthesize a turn_end.
                return events, WSTurnEndFrame(session_id=frame.session_id, turns=0, exited=True)

    def _ws_open_and_advance(
        self,
        *,
        session_id: str,
        api_key: str | None,
        text: Optional[str],
        include_opening: bool,
        expect_replay: bool = False,
    ) -> tuple[WSSessionMetaFrame, list[WSEventFrame], WSTurnEndFrame]:
        """Open a WebSocket connection, optionally consume the opening turn, then advance.

        The server always sends an unsolicited opening turn the first time a
        session is connected to. include_opening=True consumes that opening turn
        before optionally sending a user advance. Subsequent calls should pass
        include_opening=False to skip straight to sending the advance message.

        text=None sends no advance message (used for opening-only fetches).
        """
        events: list[WSEventFrame] = []
        # Default turn_end in case no frames are received (e.g. text=None, include_opening=False).
        turn_end = WSTurnEndFrame(session_id=session_id, turns=0, exited=False)

        ws_url = self._build_ws_url(session_id=session_id)
        connect_kwargs: dict[str, Any] = {}
        if api_key:
            connect_kwargs["additional_headers"] = {"Authorization": f"Bearer {api_key}"}
        with connect(ws_url, **connect_kwargs) as ws:
            session_meta = self._recv_session_meta(ws)
            if expect_replay:
                self._drain_replay(ws)
            if include_opening:
                # Consume the server-initiated opening turn before sending anything.
                opening_events, opening_turn_end = self._recv_until_turn_end(ws)
                events.extend(opening_events)
                turn_end = opening_turn_end

            if text is not None:
                # Send the player's input and drain the resulting turn.
                ws.send(WSAdvanceRequest(type="advance", text=text).model_dump_json())
                step_events, step_turn_end = self._recv_until_turn_end(ws)
                events.extend(step_events)
                turn_end = step_turn_end

        return session_meta, events, turn_end

    def _ws_status(
        self,
        *,
        session_id: str,
        api_key: str | None,
        include_opening: bool,
        expect_replay: bool = False,
    ) -> tuple[WSSessionMetaFrame, WSStatusFrame]:
        """Fetch session status via WebSocket without advancing a turn.

        If include_opening=True, the unsolicited opening turn is consumed first
        (required on first connect before any other message can be sent).
        Sends a WSStatusRequest and returns the WSStatusFrame payload.
        """
        ws_url = self._build_ws_url(session_id=session_id)
        connect_kwargs: dict[str, Any] = {}
        if api_key:
            connect_kwargs["additional_headers"] = {"Authorization": f"Bearer {api_key}"}
        with connect(ws_url, **connect_kwargs) as ws:
            session_meta = self._recv_session_meta(ws)
            if expect_replay:
                self._drain_replay(ws)
            if include_opening:
                # Must drain the opening turn before the server will accept requests.
                self._recv_until_turn_end(ws)
            ws.send(WSStatusRequest(type="status").model_dump_json())
            while True:
                frame = self._recv_frame(ws)
                if isinstance(frame, WSReplayStartFrame):
                    self._drain_replay(ws, replay_start_consumed=True)
                    continue
                break

        if not isinstance(frame, WSStatusFrame):
            raise APIRequestError("Expected status websocket frame")

        return session_meta, frame

    def _ws_close(
        self,
        *,
        session_id: str,
        api_key: str | None,
        include_opening: bool,
        expect_replay: bool = False,
    ) -> WSSessionMetaFrame:
        """Close a session via WebSocket.

        Sends a WSCloseRequest and waits for the server's WSClosedFrame confirmation.
        If include_opening=True, the opening turn is consumed first so the server
        is ready to accept the close message.
        """
        ws_url = self._build_ws_url(session_id=session_id)
        connect_kwargs: dict[str, Any] = {}
        if api_key:
            connect_kwargs["additional_headers"] = {"Authorization": f"Bearer {api_key}"}
        with connect(ws_url, **connect_kwargs) as ws:
            session_meta = self._recv_session_meta(ws)
            if expect_replay:
                self._drain_replay(ws)
            if include_opening:
                self._recv_until_turn_end(ws)
            ws.send(WSCloseRequest(type="close").model_dump_json())
            while True:
                frame = self._recv_frame(ws)
                if isinstance(frame, WSReplayStartFrame):
                    self._drain_replay(ws, replay_start_consumed=True)
                    continue
                break
            if not isinstance(frame, WSClosedFrame):
                raise APIRequestError("Expected closed websocket frame")
        return session_meta
