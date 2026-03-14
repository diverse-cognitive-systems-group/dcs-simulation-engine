"""API and websocket behavior tests for the FastAPI dcs-server."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.dal.base import PlayerRecord
from fastapi.testclient import TestClient


class DummySessionManager:
    """Minimal async session manager used to test API + WS flows."""

    def __init__(self) -> None:
        """Initialize deterministic manager state for API tests."""
        self._turns = 0
        self._exited = False
        self._exit_reason = ""
        self.flush_calls = 0
        self.game_config = SimpleNamespace(name="Explore")

    @property
    def turns(self) -> int:
        """Total completed AI turns."""
        return self._turns

    @property
    def exited(self) -> bool:
        """Whether this session manager has exited."""
        return self._exited

    @property
    def exit_reason(self) -> str:
        """Current exit reason."""
        return self._exit_reason

    async def step_async(self, user_input: str | None = None) -> list[dict[str, str]]:
        """Return deterministic events for opening and advance turns."""
        if self._exited:
            return [{"type": "info", "content": "Session has ended."}]

        if user_input is None:
            self._turns += 1
            return [{"type": "ai", "content": "opening", "event_id": "evt-opening"}]

        self._turns += 1
        return [{"type": "ai", "content": f"echo:{user_input}", "event_id": f"evt-{self._turns}"}]

    def exit(self, reason: str) -> None:
        """Close the session manager."""
        self._exited = True
        self._exit_reason = reason

    async def exit_async(self, reason: str) -> None:
        """Async close shim used by websocket route tests."""
        self.exit(reason)

    async def start_persistence(self, *, session_id: str) -> None:
        """No-op persistence hook for API tests."""
        _ = session_id

    async def flush_persistence_async(self) -> None:
        """Track explicit feedback flushes for live sessions."""
        self.flush_calls += 1


def _player(player_id: str) -> PlayerRecord:
    """Create a lightweight player record for test provider responses."""
    return PlayerRecord(
        id=player_id,
        created_at=datetime.now(timezone.utc),
        access_key="raw-key",
        data={},
    )


@pytest.fixture
def mock_provider() -> MagicMock:
    """Provide a provider double with deterministic auth behavior."""
    provider = MagicMock()

    owner = _player("player-owner")
    other = _player("player-other")

    def _get_players(*, access_key: str | None = None):
        if access_key == "valid-key":
            return owner
        if access_key == "other-key":
            return other
        return None

    provider.get_players.side_effect = _get_players
    provider.create_player.return_value = (owner, "valid-key")
    return provider


@pytest.fixture
def client(mock_provider: MagicMock) -> TestClient:
    """Build a TestClient over the API app with mocked provider wiring."""
    app = create_app(
        provider=mock_provider,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.unit
def test_app_lifespan_preloads_game_configs(mock_provider: MagicMock) -> None:
    """App startup should preload game configs into SessionManager cache."""
    app = create_app(
        provider=mock_provider,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )

    with patch("dcs_simulation_engine.api.app.SessionManager.preload_game_configs") as preload_mock:
        with TestClient(app):
            pass

    preload_mock.assert_called_once_with()


@pytest.mark.unit
def test_registration_returns_player_and_api_key(client: TestClient, mock_provider: MagicMock) -> None:
    """Registration creates player data and returns issued API key."""
    payload = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone_number": "+1 555 123 4567",
        "prior_experience": "none",
        "additional_comments": "n/a",
        "consent_to_followup": True,
        "consent_signature": "Ada",
    }

    response = client.post("/api/player/registration", json=payload)

    assert response.status_code == 200
    assert response.json() == {"player_id": "player-owner", "api_key": "valid-key"}

    kwargs = mock_provider.create_player.call_args.kwargs
    assert kwargs["issue_access_key"] is True
    assert kwargs["player_data"]["consent_signature"]["answer"] == ["Ada"]


@pytest.mark.unit
def test_auth_success_and_failure(client: TestClient) -> None:
    """Auth endpoint accepts valid key and rejects invalid key."""
    ok = client.post("/api/player/auth", json={"api_key": "valid-key"})
    assert ok.status_code == 200
    assert ok.json()["player_id"] == "player-owner"
    assert ok.json()["authenticated"] is True

    bad = client.post("/api/player/auth", json={"api_key": "not-valid"})
    assert bad.status_code == 401


@pytest.mark.unit
def test_create_game_and_list_sessions(client: TestClient) -> None:
    """Play creation registers an in-memory session visible in list endpoint."""
    manager = DummySessionManager()
    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = client.post(
            "/api/play/game",
            json={
                "api_key": "valid-key",
                "game": "explore",
                "pc_choice": None,
                "npc_choice": None,
                "source": "api",
            },
        )

    assert create_resp.status_code == 200
    create_json = create_resp.json()
    session_id = create_json["session_id"]
    assert create_json["status"] == "active"
    assert create_json["ws_path"] == f"/api/play/game/{session_id}/ws"

    list_resp = client.get("/api/sessions/list", headers={"Authorization": "Bearer valid-key"})
    assert list_resp.status_code == 200
    sessions = list_resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == session_id
    assert sessions[0]["status"] == "active"


@pytest.mark.unit
def test_websocket_open_advance_status_close(client: TestClient) -> None:
    """WebSocket endpoint supports opening turn, advance, status, and close frames."""
    manager = DummySessionManager()
    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = client.post(
            "/api/play/game",
            json={"api_key": "valid-key", "game": "explore", "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
        ws.send_json({"type": "auth", "api_key": "valid-key"})
        opening_event = ws.receive_json()
        opening_turn_end = ws.receive_json()

        assert opening_event["type"] == "event"
        assert opening_event["event_type"] == "ai"
        assert opening_event["content"] == "opening"
        assert opening_event["event_id"] == "evt-opening"
        assert opening_turn_end["type"] == "turn_end"
        assert opening_turn_end["turns"] == 1

        ws.send_json({"type": "advance", "text": "hello"})
        advance_event = ws.receive_json()
        advance_turn_end = ws.receive_json()

        assert advance_event["type"] == "event"
        assert advance_event["content"] == "echo:hello"
        assert advance_event["event_id"] == "evt-2"
        assert advance_turn_end["type"] == "turn_end"
        assert advance_turn_end["turns"] == 2

        ws.send_json({"type": "status"})
        status_frame = ws.receive_json()
        assert status_frame["type"] == "status"
        assert status_frame["status"] == "active"
        assert status_frame["turns"] == 2

        ws.send_json({"type": "close"})
        closed_frame = ws.receive_json()
        assert closed_frame == {"type": "closed", "session_id": session_id}


@pytest.mark.unit
def test_websocket_rejects_wrong_owner(client: TestClient) -> None:
    """WebSocket connection is rejected when API key owner doesn't own session."""
    manager = DummySessionManager()
    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = client.post(
            "/api/play/game",
            json={"api_key": "valid-key", "game": "explore", "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
        ws.send_json({"type": "auth", "api_key": "other-key"})
        error_frame = ws.receive_json()
        assert error_frame["type"] == "error"
        assert "Unauthorized" in error_frame["detail"]


@pytest.mark.unit
def test_setup_options_returns_allowed_choices(client: TestClient) -> None:
    """Setup preflight returns valid player-scoped character choices."""
    setup_config = SimpleNamespace(
        name="Explore",
        is_player_allowed=lambda **_kwargs: True,
        get_valid_characters=lambda **_kwargs: ([("PC Alpha", "pc-1")], [("NPC Beta", "npc-2")]),
    )

    with (
        patch(
            "dcs_simulation_engine.api.routers.play.SessionManager.get_game_config_cached",
            return_value=setup_config,
        ),
    ):
        response = client.get(
            "/api/play/setup/explore",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "game": "Explore",
        "allowed": True,
        "can_start": True,
        "denial_reason": None,
        "message": None,
        "pcs": [{"hid": "pc-1", "label": "PC Alpha"}],
        "npcs": [{"hid": "npc-2", "label": "NPC Beta"}],
    }


@pytest.mark.unit
def test_setup_options_denies_unauthorized_player(client: TestClient) -> None:
    """Setup preflight blocks players that fail game access checks."""
    setup_config = SimpleNamespace(
        name="Foresight",
        is_player_allowed=lambda **_kwargs: False,
        get_valid_characters=lambda **_kwargs: ([], []),
    )

    with (
        patch(
            "dcs_simulation_engine.api.routers.play.SessionManager.get_game_config_cached",
            return_value=setup_config,
        ),
    ):
        response = client.get(
            "/api/play/setup/foresight",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["can_start"] is False
    assert response.json()["denial_reason"] == "not_allowed"
    assert "not authorized" in response.json()["message"]


@pytest.mark.unit
def test_setup_options_handles_missing_valid_characters(client: TestClient) -> None:
    """Setup preflight reports when no valid PCs are available for the player."""
    setup_config = SimpleNamespace(
        name="Explore",
        is_player_allowed=lambda **_kwargs: True,
        get_valid_characters=lambda **_kwargs: ([], [("NPC Beta", "npc-2")]),
    )

    with (
        patch(
            "dcs_simulation_engine.api.routers.play.SessionManager.get_game_config_cached",
            return_value=setup_config,
        ),
    ):
        response = client.get(
            "/api/play/setup/explore",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert response.status_code == 200
    assert response.json()["allowed"] is True
    assert response.json()["can_start"] is False
    assert response.json()["denial_reason"] == "no_valid_pc"
    assert response.json()["pcs"] == []
    assert response.json()["npcs"] == [{"hid": "npc-2", "label": "NPC Beta"}]


@pytest.mark.unit
def test_session_reconstruction_endpoint_returns_payload(client: TestClient, mock_provider: MagicMock) -> None:
    """Reconstruction endpoint returns session metadata and ordered events."""
    mock_provider.get_session_reconstruction.return_value = {
        "session": {"session_id": "s1", "player_id": "player-owner", "status": "closed"},
        "events": [{"session_id": "s1", "seq": 1, "content": "hello"}],
    }

    response = client.get(
        "/api/sessions/s1/reconstruction",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 200
    assert response.json()["session"]["session_id"] == "s1"
    assert response.json()["events"][0]["seq"] == 1


@pytest.mark.unit
def test_session_event_feedback_submit_flushes_live_session_and_persists(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Feedback submit uses the live registry session, flushes pending writes, and persists feedback."""
    manager = DummySessionManager()
    mock_provider.set_session_event_feedback = AsyncMock(
        return_value={
            "liked": True,
            "comment": "Helpful answer",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = client.post(
            "/api/play/game",
            json={"api_key": "valid-key", "game": "explore", "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/events/evt-opening/feedback",
        headers={"Authorization": "Bearer valid-key"},
        json={"liked": True, "comment": "Helpful answer"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["event_id"] == "evt-opening"
    assert payload["feedback"]["liked"] is True
    assert payload["feedback"]["comment"] == "Helpful answer"
    assert manager.flush_calls == 1

    kwargs = mock_provider.set_session_event_feedback.await_args.kwargs
    assert kwargs["session_id"] == session_id
    assert kwargs["player_id"] == "player-owner"
    assert kwargs["event_id"] == "evt-opening"
    assert kwargs["feedback"]["comment"] == "Helpful answer"


@pytest.mark.unit
def test_session_event_feedback_submit_returns_not_found_for_non_owner(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Feedback submit does not expose session ownership to other authenticated players."""
    manager = DummySessionManager()
    mock_provider.set_session_event_feedback = AsyncMock(return_value=None)

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = client.post(
            "/api/play/game",
            json={"api_key": "valid-key", "game": "explore", "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    response = client.post(
        f"/api/sessions/{session_id}/events/evt-opening/feedback",
        headers={"Authorization": "Bearer other-key"},
        json={"liked": False, "comment": "Wrong owner"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
def test_session_event_feedback_clear_flushes_live_session_and_persists(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Clearing feedback unsets it on the original assistant message row."""
    manager = DummySessionManager()
    mock_provider.clear_session_event_feedback = AsyncMock(return_value=True)

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = client.post(
            "/api/play/game",
            json={"api_key": "valid-key", "game": "explore", "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    response = client.delete(
        f"/api/sessions/{session_id}/events/evt-opening/feedback",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": session_id,
        "event_id": "evt-opening",
        "cleared": True,
    }
    assert manager.flush_calls == 1

    kwargs = mock_provider.clear_session_event_feedback.await_args.kwargs
    assert kwargs["session_id"] == session_id
    assert kwargs["player_id"] == "player-owner"
    assert kwargs["event_id"] == "evt-opening"
