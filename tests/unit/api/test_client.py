"""Unit tests for the APIClient websocket handshake handling."""

import json

import pytest
from dcs_simulation_engine.api import client as api_client

pytestmark = pytest.mark.unit


def _json_frame(payload: dict) -> str:
    return json.dumps(payload)


class _FakeWebSocket:
    """Context-manager websocket stub with queued inbound frames."""

    def __init__(self, frames: list[str]) -> None:
        self._frames = list(frames)
        self.sent: list[str] = []

    def __enter__(self) -> "_FakeWebSocket":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def recv(self) -> str:
        if not self._frames:
            raise AssertionError("No websocket frames remaining.")
        return self._frames.pop(0)

    def send(self, payload: str) -> None:
        self.sent.append(payload)


class _ConnectFactory:
    """Provide a fresh fake websocket per connect() call."""

    def __init__(self, *connections: _FakeWebSocket) -> None:
        self._connections = list(connections)

    def __call__(self, url: str, **kwargs):
        _ = (url, kwargs)
        if not self._connections:
            raise AssertionError("Unexpected websocket connection.")
        return self._connections.pop(0)


def test_simulation_run_step_consumes_session_meta_on_each_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """step() should consume leading session_meta before opening and advance turns."""
    first_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "sess-1",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-a",
                    "has_game_feedback": False,
                }
            ),
            _json_frame(
                {
                    "type": "event",
                    "session_id": "sess-1",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                }
            ),
            _json_frame({"type": "turn_end", "session_id": "sess-1", "turns": 1, "exited": False}),
        ]
    )
    second_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "sess-1",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-b",
                    "has_game_feedback": True,
                }
            ),
            _json_frame({"type": "replay_start", "session_id": "sess-1"}),
            _json_frame(
                {
                    "type": "replay_event",
                    "session_id": "sess-1",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                    "role": "ai",
                }
            ),
            _json_frame(
                {
                    "type": "replay_event",
                    "session_id": "sess-1",
                    "event_type": "info",
                    "content": "hello",
                    "event_id": None,
                    "role": "user",
                }
            ),
            _json_frame({"type": "replay_end", "session_id": "sess-1", "turns": 1}),
            _json_frame(
                {
                    "type": "event",
                    "session_id": "sess-1",
                    "event_type": "ai",
                    "content": "echo:hello",
                    "event_id": "evt-2",
                }
            ),
            _json_frame({"type": "turn_end", "session_id": "sess-1", "turns": 2, "exited": False}),
        ]
    )
    monkeypatch.setattr(api_client, "connect", _ConnectFactory(first_ws, second_ws))

    with api_client.APIClient(url="http://example.test", timeout=1.0) as api:
        run = api_client.SimulationRun(api, session_id="sess-1", game_name="Explore", api_key=None)
        run.step()
        assert run.session_meta is not None
        assert run.session_meta.npc_hid == "npc-a"
        assert run.simulator_output == "opening"
        assert run.turns == 1

        run.step("hello")
        assert run.session_meta is not None
        assert run.session_meta.npc_hid == "npc-b"
        assert run.session_meta.has_game_feedback is True
        assert run.simulator_output == "echo:hello"
        assert run.turns == 2
        assert [event.content for event in run.history] == ["opening", "echo:hello"]

    assert json.loads(second_ws.sent[0]) == {"type": "advance", "text": "hello"}


def test_simulation_run_get_state_consumes_session_meta_before_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_state() should drain session_meta and opening turn before requesting status."""
    first_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "sess-2",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-status",
                    "has_game_feedback": False,
                }
            ),
            _json_frame(
                {
                    "type": "event",
                    "session_id": "sess-2",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                }
            ),
            _json_frame({"type": "turn_end", "session_id": "sess-2", "turns": 1, "exited": False}),
        ]
    )
    second_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "sess-2",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-status",
                    "has_game_feedback": False,
                }
            ),
            _json_frame({"type": "replay_start", "session_id": "sess-2"}),
            _json_frame(
                {
                    "type": "replay_event",
                    "session_id": "sess-2",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                    "role": "ai",
                }
            ),
            _json_frame({"type": "replay_end", "session_id": "sess-2", "turns": 1}),
            _json_frame({"type": "status", "session_id": "sess-2", "status": "active", "turns": 4, "exited": False}),
        ]
    )
    monkeypatch.setattr(api_client, "connect", _ConnectFactory(first_ws, second_ws))

    with api_client.APIClient(url="http://example.test", timeout=1.0) as api:
        run = api_client.SimulationRun(api, session_id="sess-2", game_name="Explore", api_key=None)
        run.step()
        run.get_state()
        assert run.session_meta is not None
        assert run.session_meta.npc_hid == "npc-status"
        assert run.turns == 4
        assert run.is_complete is False

    assert json.loads(second_ws.sent[0]) == {"type": "status"}


def test_simulation_run_close_consumes_session_meta_before_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """close() should drain session_meta and the opening turn before sending close."""
    first_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "sess-3",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-close",
                    "has_game_feedback": False,
                }
            ),
            _json_frame(
                {
                    "type": "event",
                    "session_id": "sess-3",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                }
            ),
            _json_frame({"type": "turn_end", "session_id": "sess-3", "turns": 1, "exited": False}),
        ]
    )
    second_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "sess-3",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-close",
                    "has_game_feedback": False,
                }
            ),
            _json_frame({"type": "replay_start", "session_id": "sess-3"}),
            _json_frame(
                {
                    "type": "replay_event",
                    "session_id": "sess-3",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                    "role": "ai",
                }
            ),
            _json_frame({"type": "replay_end", "session_id": "sess-3", "turns": 1}),
            _json_frame({"type": "closed", "session_id": "sess-3"}),
        ]
    )
    monkeypatch.setattr(api_client, "connect", _ConnectFactory(first_ws, second_ws))

    with api_client.APIClient(url="http://example.test", timeout=1.0) as api:
        run = api_client.SimulationRun(api, session_id="sess-3", game_name="Explore", api_key=None)
        run.step()
        run.close()
        assert run.session_meta is not None
        assert run.session_meta.npc_hid == "npc-close"

    assert json.loads(second_ws.sent[0]) == {"type": "close"}


def test_branch_session_returns_resumed_run_and_drains_replay(monkeypatch: pytest.MonkeyPatch) -> None:
    """branch_session should return a resumed-style run that drains replay before advance."""
    branch_ws = _FakeWebSocket(
        [
            _json_frame(
                {
                    "type": "session_meta",
                    "session_id": "child-1",
                    "pc_hid": "pc-a",
                    "npc_hid": "npc-a",
                    "has_game_feedback": False,
                }
            ),
            _json_frame({"type": "replay_start", "session_id": "child-1"}),
            _json_frame(
                {
                    "type": "replay_event",
                    "session_id": "child-1",
                    "event_type": "ai",
                    "content": "opening",
                    "event_id": "evt-opening",
                    "role": "ai",
                }
            ),
            _json_frame({"type": "replay_end", "session_id": "child-1", "turns": 1}),
            _json_frame(
                {
                    "type": "event",
                    "session_id": "child-1",
                    "event_type": "ai",
                    "content": "branch reply",
                    "event_id": "evt-branch",
                }
            ),
            _json_frame({"type": "turn_end", "session_id": "child-1", "turns": 2, "exited": False}),
        ]
    )
    monkeypatch.setattr(api_client, "connect", _ConnectFactory(branch_ws))

    with api_client.APIClient(url="http://example.test", timeout=1.0) as api:
        monkeypatch.setattr(
            api,
            "_request",
            lambda method, path, body, response_model, **kwargs: type(
                "BranchResponse",
                (),
                {"session_id": "child-1", "game_name": "Explore"},
            )(),
        )
        run = api.branch_session("root-1")
        run.step("look around")

        assert run.session_id == "child-1"
        assert run.simulator_output == "branch reply"
        assert run.turns == 2
        assert [event.content for event in run.history] == ["branch reply"]

    assert json.loads(branch_ws.sent[0]) == {"type": "advance", "text": "look around"}
