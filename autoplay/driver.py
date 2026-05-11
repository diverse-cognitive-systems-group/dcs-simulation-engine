"""Client-side autoplay driver."""

import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx
from autoplay.players import ApiPlayer
from autoplay.types import (
    AssignmentResult,
    HarnessResult,
    PlayerContext,
    PlayerTurn,
)
from dcs_simulation_engine.api.models import (
    WSAdvanceRequest,
)
from websockets.asyncio.client import connect

logger = logging.getLogger(__name__)


class PlayerHarness:
    """Drive API-visible player actions against a running DCS API server."""

    def __init__(
        self,
        *,
        base_url: str,
        player: ApiPlayer,
        max_turns_per_assignment: int = 20,
        timeout: float = 60.0,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """Create a harness for one API player."""
        self.base_url = base_url.rstrip("/")
        self.player = player
        self.max_turns_per_assignment = max_turns_per_assignment
        self.timeout = timeout
        self._on_event = on_event

    async def run(self) -> HarnessResult:
        """Create one API player and play assignments until the run is complete."""
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            server_config = await self._request_json(client, "GET", "/api/server/config")
            auth = await self._create_player(client, registration_required=bool(server_config["registration_enabled"]))
            api_key = str(auth["api_key"])
            player_id = str(auth["player_id"])
            result = HarnessResult(
                model_id=self.player.model_id,
                player_id=player_id,
                api_key=api_key,
                run_name=str(server_config["run_name"]),
            )
            logger.info("autoplay player_started model=%s player_id=%s", self.player.model_id, player_id)
            self._emit("player_started", player_id=player_id, run_name=result.run_name)

            while True:
                setup = await self._run_setup(client, api_key=api_key)
                self._reject_pending_forms(setup)
                if setup.get("assignment_completed"):
                    logger.info("autoplay player_completed model=%s player_id=%s", self.player.model_id, player_id)
                    self._emit("player_completed", player_id=player_id)
                    return result

                assignment = await self._resolve_assignment(client, setup=setup, api_key=api_key)
                if assignment is None:
                    logger.info("autoplay no_assignment model=%s player_id=%s", self.player.model_id, player_id)
                    self._emit("no_assignment", player_id=player_id)
                    return result

                session = await self._start_session(client, api_key=api_key, assignment_id=assignment["assignment_id"])
                assignment_result = await self._play_assignment(
                    api_key=api_key,
                    player_id=player_id,
                    run_name=str(server_config["run_name"]),
                    assignment=assignment,
                    session=session,
                )
                refreshed_setup = await self._run_setup(client, api_key=api_key)
                backend_status = self._assignment_status(refreshed_setup, assignment_id=assignment_result.assignment_id)
                if backend_status is not None:
                    assignment_result.status = backend_status
                result.assignments.append(assignment_result)
                if assignment_result.status != "completed":
                    return result

    async def _create_player(self, client: httpx.AsyncClient, *, registration_required: bool) -> dict[str, Any]:
        if not registration_required:
            return await self._request_json(client, "POST", "/api/player/anonymous")
        return await self._request_json(
            client,
            "POST",
            "/api/player/registration",
            json={
                "full_name": f"autoplay ({self.player.model_id})",
                "email": f"auto-play-{abs(hash(self.player.model_id))}@example.com",
                "phone_number": "555-0100",
            },
        )

    async def _run_setup(self, client: httpx.AsyncClient, *, api_key: str) -> dict[str, Any]:
        return await self._request_json(
            client,
            "GET",
            "/api/run/setup",
            headers=self._auth_headers(api_key),
        )

    async def _resolve_assignment(
        self,
        client: httpx.AsyncClient,
        *,
        setup: dict[str, Any],
        api_key: str,
    ) -> dict[str, Any] | None:
        current = setup.get("current_assignment")
        if isinstance(current, dict):
            return current

        next_assignment = setup.get("next_assignment")
        if not isinstance(next_assignment, dict):
            return None
        if next_assignment.get("mode") != "choice":
            return None

        options = setup.get("eligible_assignment_options") or next_assignment.get("options") or []
        if not options:
            return None
        option = dict(options[0])
        return await self._request_json(
            client,
            "POST",
            "/api/run/assignments/select",
            headers=self._auth_headers(api_key),
            json={
                "game_name": option["game_name"],
                "pc_hid": option["pc_hid"],
                "npc_hid": option["npc_hid"],
            },
        )

    async def _start_session(self, client: httpx.AsyncClient, *, api_key: str, assignment_id: str) -> dict[str, Any]:
        return await self._request_json(
            client,
            "POST",
            "/api/run/sessions",
            headers=self._auth_headers(api_key),
            json={"source": "autoplay", "assignment_id": assignment_id},
        )

    async def _play_assignment(
        self,
        *,
        api_key: str,
        player_id: str,
        run_name: str,
        assignment: dict[str, Any],
        session: dict[str, Any],
    ) -> AssignmentResult:
        assignment_id = str(assignment["assignment_id"])
        session_id = str(session["session_id"])
        history: list[PlayerTurn] = []
        last_error: str | None = None
        turns = 0
        logger.info(
            "autoplay assignment_started model=%s assignment_id=%s session_id=%s game=%s",
            self.player.model_id,
            assignment_id,
            session_id,
            assignment.get("game_name"),
        )
        self._emit(
            "assignment_started",
            assignment_id=assignment_id,
            session_id=session_id,
            game_name=str(assignment.get("game_name") or ""),
        )

        try:
            async with connect(self._ws_url(session_id), additional_headers=self._auth_headers(api_key)) as ws:
                session_meta = await self._recv_expected(ws, "session_meta")
                opening_events, turn_end = await self._recv_until_turn_end(ws)
                history.extend(self._turns_from_events(opening_events))
                turns = int(turn_end.get("turns") or 0)
                if turn_end.get("exited"):
                    return AssignmentResult(
                        assignment_id=assignment_id,
                        game_name=str(assignment["game_name"]),
                        session_id=session_id,
                        status="exited",
                        turns=turns,
                    )

                while turns < self.max_turns_per_assignment:
                    context = PlayerContext(
                        run_name=run_name,
                        player_id=player_id,
                        model_id=self.player.model_id,
                        assignment=dict(assignment),
                        session_id=session_id,
                        session_meta=dict(session_meta),
                        turns=turns,
                        history=tuple(history),
                        last_error=last_error,
                    )
                    player_input = await self.player.next_input(context)
                    history.append(PlayerTurn(role="player", content=player_input))
                    logger.info(
                        "autoplay turn_sent model=%s assignment_id=%s session_id=%s turns=%s input=%r",
                        self.player.model_id,
                        assignment_id,
                        session_id,
                        turns,
                        player_input,
                    )
                    self._emit(
                        "turn_sent",
                        assignment_id=assignment_id,
                        session_id=session_id,
                        turns=turns,
                        input=player_input,
                    )
                    await ws.send(WSAdvanceRequest(type="advance", text=player_input).model_dump_json())
                    events, turn_end = await self._recv_until_turn_end(ws)
                    history.extend(self._turns_from_events(events))
                    turns = int(turn_end.get("turns") or turns)
                    last_error = self._last_error(events)
                    if turn_end.get("exited"):
                        logger.info(
                            "autoplay assignment_exited model=%s assignment_id=%s session_id=%s turns=%s reason=%s",
                            self.player.model_id,
                            assignment_id,
                            session_id,
                            turns,
                            turn_end.get("exit_reason"),
                        )
                        self._emit(
                            "assignment_exited",
                            assignment_id=assignment_id,
                            session_id=session_id,
                            turns=turns,
                            reason=str(turn_end.get("exit_reason") or "exited"),
                        )
                        return AssignmentResult(
                            assignment_id=assignment_id,
                            game_name=str(assignment["game_name"]),
                            session_id=session_id,
                            status="exited",
                            turns=turns,
                        )

            return AssignmentResult(
                assignment_id=assignment_id,
                game_name=str(assignment["game_name"]),
                session_id=session_id,
                status="interrupted",
                turns=turns,
                error=f"max_turns_per_assignment reached: {self.max_turns_per_assignment}",
            )
        except Exception as exc:
            logger.error(
                "autoplay assignment_failed model=%s assignment_id=%s session_id=%s",
                self.player.model_id,
                assignment_id,
                session_id,
            )
            self._emit(
                "assignment_failed",
                assignment_id=assignment_id,
                session_id=session_id,
                turns=turns,
                error=str(exc),
            )
            return AssignmentResult(
                assignment_id=assignment_id,
                game_name=str(assignment["game_name"]),
                session_id=session_id,
                status="error",
                turns=turns,
                error=str(exc),
            )

    def _reject_pending_forms(self, setup: dict[str, Any]) -> None:
        pending = setup.get("pending_form_groups") or []
        if pending:
            names = [str(group.get("group_id") or group.get("trigger", {}).get("event")) for group in pending]
            raise RuntimeError(f"autoplay does not submit forms yet. Pending form groups: {names}")

    def _assignment_status(self, setup: dict[str, Any], *, assignment_id: str) -> str | None:
        for assignment in setup.get("assignments") or []:
            if isinstance(assignment, dict) and assignment.get("assignment_id") == assignment_id:
                status = assignment.get("status")
                return str(status) if status is not None else None
        return None

    async def _request_json(self, client: httpx.AsyncClient, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = await client.request(method, path, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"Expected object response from {path}")
        return payload

    def _auth_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def _emit(self, event: str, **payload: Any) -> None:
        if self._on_event is None:
            return
        self._on_event(event, {"model_id": self.player.model_id, **payload})

    def _ws_url(self, session_id: str) -> str:
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}/api/play/game/{session_id}/ws"

    async def _recv_json(self, ws: Any) -> dict[str, Any]:
        raw = await ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str):
            raise RuntimeError("Expected text websocket frame")
        frame = json.loads(raw)
        if not isinstance(frame, dict):
            raise RuntimeError("Expected JSON object websocket frame")
        if frame.get("type") == "error":
            raise RuntimeError(str(frame.get("detail") or "Unknown websocket error"))
        return frame

    async def _recv_expected(self, ws: Any, expected_type: str) -> dict[str, Any]:
        frame = await self._recv_json(ws)
        if frame.get("type") != expected_type:
            raise RuntimeError(f"Expected {expected_type!r} websocket frame, got {frame.get('type')!r}")
        return frame

    async def _recv_until_turn_end(self, ws: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while True:
            frame = await self._recv_json(ws)
            frame_type = frame.get("type")
            if frame_type == "event":
                events.append(frame)
                continue
            if frame_type == "replay_start":
                await self._drain_replay(ws)
                continue
            if frame_type == "turn_end":
                return events, frame
            if frame_type == "closed":
                return events, {"type": "turn_end", "session_id": frame.get("session_id"), "turns": 0, "exited": True}
            raise RuntimeError(f"Unexpected websocket frame type: {frame_type!r}")

    async def _drain_replay(self, ws: Any) -> None:
        while True:
            frame = await self._recv_json(ws)
            if frame.get("type") == "replay_end":
                return

    def _turns_from_events(self, events: list[dict[str, Any]]) -> list[PlayerTurn]:
        turns: list[PlayerTurn] = []
        for event in events:
            event_type = str(event.get("event_type") or "")
            role = "server"
            if event_type == "ai":
                role = "simulator"
            turns.append(
                PlayerTurn(
                    role=role,
                    event_type=event_type,
                    content=str(event.get("content") or ""),
                    failure_type=event.get("failure_type"),
                )
            )
        return turns

    def _last_error(self, events: list[dict[str, Any]]) -> str | None:
        for event in reversed(events):
            if event.get("event_type") == "error":
                return str(event.get("content") or "")
        return None
