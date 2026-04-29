"""API and websocket behavior tests for the FastAPI dcs-server."""

import asyncio
import tarfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.core.forms import (
    ExperimentForm,
    ExperimentFormQuestion,
)
from dcs_simulation_engine.core.run_config import RunConfig
from dcs_simulation_engine.dal.base import (
    PlayerRecord,
    SessionRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from fastapi.testclient import TestClient

ASSIGNMENT_DISPLAY_METADATA = {
    "game_description": "Game description",
    "player_character_name": "Player Character",
    "player_character_description": "Player character description",
    "simulator_character_description": "Details hidden",
    "simulator_character_details_visible": False,
}


def _run_config(
    *,
    name: str = "usability",
    registration_required: bool = True,
    allow_choice_if_multiple: bool = False,
    require_completion: bool = True,
    max_assignments_per_player: int = 3,
) -> RunConfig:
    """Return a compact run config for API tests."""
    return RunConfig.model_validate(
        {
            "name": name,
            "description": "Usability study",
            "ui": {"registration_required": registration_required},
            "games": [{"name": "Explore"}],
            "next_game_strategy": {
                "strategy": {
                    "id": "full_character_access",
                    "allow_choice_if_multiple": allow_choice_if_multiple,
                    "require_completion": require_completion,
                    "max_assignments_per_player": max_assignments_per_player,
                }
            },
            "forms": [
                {
                    "name": "intake",
                    "trigger": {"event": "before_all_assignments", "match": None},
                    "questions": [],
                }
            ],
        }
    )


class DummySessionManager:
    """Minimal async session manager used to test API + WS flows."""

    def __init__(self) -> None:
        """Initialize deterministic manager state for API tests."""
        self._turns = 0
        self._exited = False
        self._exit_reason = ""
        self.flush_calls = 0
        self.snapshot_calls = 0
        self.game_config = SimpleNamespace(name="Explore")
        self.game = SimpleNamespace(_pc=None, _npc=None)

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

    async def persist_runtime_snapshot_async(self) -> None:
        """Track explicit branch-source snapshot writes for live sessions."""
        self.snapshot_calls += 1


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
    provider.get_latest_experiment_assignment_for_player.return_value = None
    return provider


@pytest.fixture
def client(mock_provider: MagicMock) -> TestClient:
    """Build a TestClient over the API app with mocked provider wiring."""
    app = create_app(
        provider=mock_provider,
        run_config=_run_config(),
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anonymous_client(mock_provider: MagicMock) -> TestClient:
    """Build a TestClient configured for a run that allows anonymous players."""
    app = create_app(
        provider=mock_provider,
        run_config=_run_config(registration_required=False),
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anonymous_auth(anonymous_client: TestClient) -> dict[str, str]:
    """Create an anonymous player and return its issued auth payload."""
    response = anonymous_client.post("/api/player/anonymous")
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def remote_managed_client(mock_provider: MagicMock) -> TestClient:
    """Build a TestClient configured for remote-managed experiment hosting."""
    app = create_app(
        provider=mock_provider,
        run_config=_run_config(),
        mongo_uri="mongodb://example",
        remote_management_enabled=True,
        bootstrap_token="bootstrap-secret",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.unit
def test_app_lifespan_preloads_game_configs(mock_provider: MagicMock) -> None:
    """App startup should ensure the active run and preload game configs."""
    app = create_app(
        provider=mock_provider,
        run_config=_run_config(),
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )

    with (
        patch("dcs_simulation_engine.api.app.SessionManager.preload_game_configs") as preload_mock,
        patch("dcs_simulation_engine.api.app.EngineRunManager.ensure_run_async", new=AsyncMock()) as ensure_run_mock,
    ):
        with TestClient(app):
            pass

    preload_mock.assert_called_once_with()
    ensure_run_mock.assert_awaited_once()


@pytest.mark.unit
def test_app_lifespan_dumps_db_on_shutdown(async_mongo_provider, tmp_path) -> None:
    """App shutdown should write a Mongo dump when configured."""
    db = async_mongo_provider.get_db()
    db["widgets"].insert_one({"name": "shutdown-test"})

    app = create_app(
        provider=async_mongo_provider,
        shutdown_dump_dir=tmp_path,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )

    with TestClient(app):
        pass

    dump_dirs = [path for path in tmp_path.iterdir() if path.is_dir()]
    assert len(dump_dirs) == 1

    widgets_dump = dump_dirs[0] / "widgets.json"
    assert widgets_dump.exists()
    assert "shutdown-test" in widgets_dump.read_text(encoding="utf-8")


@pytest.mark.unit
def test_registration_returns_player_and_api_key(client: TestClient, mock_provider: MagicMock) -> None:
    """Registration creates player data and returns issued API key."""
    payload = {
        "full_name": "Ada Lovelace",
        "email": "ada@example.com",
        "phone_number": "+1 555 123 4567",
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
def test_server_config_reports_standard_mode(client: TestClient) -> None:
    """Server config should advertise standard-mode capabilities by default."""
    response = client.get("/api/server/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "standard",
        "authentication_required": True,
        "registration_enabled": True,
        "experiments_enabled": True,
        "default_experiment_name": "usability",
    }


@pytest.mark.unit
def test_server_config_reports_anonymous_run_capabilities(anonymous_client: TestClient) -> None:
    """Server config should advertise automatic anonymous-auth capabilities."""
    response = anonymous_client.get("/api/server/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "standard",
        "authentication_required": False,
        "registration_enabled": False,
        "experiments_enabled": True,
        "default_experiment_name": "usability",
    }


@pytest.mark.unit
def test_status_reports_started_at_and_uptime(client: TestClient) -> None:
    """Status endpoint should return liveness metadata with uptime and start time."""
    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["uptime"] >= 0

    started_at = datetime.fromisoformat(payload["started_at"].replace("Z", "+00:00"))
    assert started_at.tzinfo is not None
    assert started_at <= datetime.now(timezone.utc)


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
def test_branch_session_flushes_live_root_and_returns_paused_child(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Branching a live session should flush/snapshot the root and return child metadata."""
    manager = DummySessionManager()
    entry = client.app.state.registry.add(
        player_id="player-owner",
        game_name="Explore",
        manager=manager,
    )
    mock_provider.branch_session = AsyncMock(
        return_value=SessionRecord(
            session_id="child-1",
            player_id="player-owner",
            game_name="Explore",
            status="paused",
            created_at=datetime.now(timezone.utc),
            data={MongoColumns.BRANCH_FROM_SESSION_ID: entry.session_id},
        )
    )

    response = client.post(
        f"/api/sessions/{entry.session_id}/branch",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "child-1",
        "branch_from_session_id": entry.session_id,
        "game_name": "Explore",
        "status": "paused",
        "ws_path": "/api/play/game/child-1/ws",
    }
    assert manager.flush_calls == 1
    assert manager.snapshot_calls == 1

    kwargs = mock_provider.branch_session.await_args.kwargs
    assert kwargs["session_id"] == entry.session_id
    assert kwargs["player_id"] == "player-owner"


@pytest.mark.unit
def test_anonymous_setup_options_use_issued_access_key(
    anonymous_client: TestClient,
    anonymous_auth: dict[str, str],
) -> None:
    """Anonymous setup should use the access key issued by anonymous player creation."""
    setup_config = SimpleNamespace(
        name="Explore",
        get_valid_characters=lambda **_kwargs: ([("PC Alpha", "pc-1")], [("NPC Beta", "npc-2")]),
    )

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.get_game_config_cached",
        return_value=setup_config,
    ):
        response = anonymous_client.get(
            "/api/play/setup/explore",
            headers={"Authorization": f"Bearer {anonymous_auth['api_key']}"},
        )

    assert response.status_code == 200
    assert response.json()["can_start"] is True
    assert response.json()["pcs"] == [{"hid": "pc-1", "label": "PC Alpha"}]


@pytest.mark.unit
def test_anonymous_create_game_and_websocket_with_issued_access_key(
    anonymous_client: TestClient,
    anonymous_auth: dict[str, str],
) -> None:
    """Anonymous players should create sessions and play using their issued access key."""
    manager = DummySessionManager()
    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = anonymous_client.post(
            "/api/play/game",
            json={
                "api_key": anonymous_auth["api_key"],
                "game": "explore",
                "pc_choice": None,
                "npc_choice": None,
                "source": "api",
            },
        )

    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]

    with anonymous_client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
        ws.send_json({"type": "auth", "api_key": anonymous_auth["api_key"]})
        meta_frame = ws.receive_json()
        assert meta_frame["type"] == "session_meta"

        opening_event = ws.receive_json()
        opening_turn_end = ws.receive_json()

        assert opening_event["type"] == "event"
        assert opening_event["content"] == "opening"
        assert opening_turn_end["type"] == "turn_end"

        ws.send_json({"type": "advance", "text": "hello"})
        advance_event = ws.receive_json()
        advance_turn_end = ws.receive_json()

        assert advance_event["type"] == "event"
        assert advance_event["content"] == "echo:hello"
        assert advance_turn_end["turns"] == 2

        ws.send_json({"type": "close"})
        assert ws.receive_json() == {"type": "closed", "session_id": session_id}


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
        meta_frame = ws.receive_json()
        assert meta_frame["type"] == "session_meta"

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
def test_setup_options_handles_missing_valid_characters(client: TestClient) -> None:
    """Setup preflight reports when no valid PCs are available for the player."""
    setup_config = SimpleNamespace(
        name="Explore",
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
            "liked": False,
            "comment": "This response felt off.",
            "doesnt_make_sense": True,
            "out_of_character": False,
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
        json={
            "liked": False,
            "comment": "This response felt off.",
            "doesnt_make_sense": True,
            "out_of_character": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session_id
    assert payload["event_id"] == "evt-opening"
    assert payload["feedback"]["liked"] is False
    assert payload["feedback"]["comment"] == "This response felt off."
    assert payload["feedback"]["doesnt_make_sense"] is True
    assert payload["feedback"]["out_of_character"] is False
    assert manager.flush_calls == 1

    kwargs = mock_provider.set_session_event_feedback.await_args.kwargs
    assert kwargs["session_id"] == session_id
    assert kwargs["player_id"] == "player-owner"
    assert kwargs["event_id"] == "evt-opening"
    assert kwargs["feedback"]["liked"] is False
    assert kwargs["feedback"]["comment"] == "This response felt off."
    assert kwargs["feedback"]["doesnt_make_sense"] is True
    assert kwargs["feedback"]["out_of_character"] is False


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
        json={
            "liked": False,
            "comment": "That did not land.",
            "doesnt_make_sense": False,
            "out_of_character": True,
        },
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


@pytest.mark.unit
def test_anonymous_feedback_submit_flushes_live_session_and_persists(
    anonymous_client: TestClient,
    anonymous_auth: dict[str, str],
    mock_provider: MagicMock,
) -> None:
    """Anonymous sessions should still expose per-message feedback controls."""
    manager = DummySessionManager()
    mock_provider.set_session_event_feedback = AsyncMock(
        return_value={
            "liked": False,
            "comment": "This felt out of character.",
            "doesnt_make_sense": False,
            "out_of_character": True,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }
    )

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = anonymous_client.post(
            "/api/play/game",
            json={
                "api_key": anonymous_auth["api_key"],
                "game": "explore",
                "pc_choice": None,
                "npc_choice": None,
                "source": "api",
            },
        )

    session_id = create_resp.json()["session_id"]

    response = anonymous_client.post(
        f"/api/sessions/{session_id}/events/evt-opening/feedback",
        headers={"Authorization": f"Bearer {anonymous_auth['api_key']}"},
        json={
            "liked": False,
            "comment": "This felt out of character.",
            "doesnt_make_sense": False,
            "out_of_character": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["feedback"]["comment"] == "This felt out of character."
    assert response.json()["feedback"]["out_of_character"] is True
    assert manager.flush_calls == 1

    kwargs = mock_provider.set_session_event_feedback.await_args.kwargs
    assert kwargs["session_id"] == session_id
    assert kwargs["player_id"] == "player-owner"
    assert kwargs["event_id"] == "evt-opening"


@pytest.mark.unit
def test_session_event_feedback_submit_clears_issue_flags_for_likes(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Positive reactions should not retain negative issue flags even if sent accidentally."""
    manager = DummySessionManager()
    mock_provider.set_session_event_feedback = AsyncMock(
        return_value={
            "liked": True,
            "comment": "Helpful scene framing.",
            "doesnt_make_sense": False,
            "out_of_character": False,
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
        json={
            "liked": True,
            "comment": "Helpful scene framing.",
            "doesnt_make_sense": True,
            "out_of_character": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["feedback"]["liked"] is True
    assert payload["feedback"]["doesnt_make_sense"] is False
    assert payload["feedback"]["out_of_character"] is False


@pytest.mark.unit
def test_anonymous_feedback_clear_flushes_live_session_and_persists(
    anonymous_client: TestClient,
    anonymous_auth: dict[str, str],
    mock_provider: MagicMock,
) -> None:
    """Anonymous feedback clearing should work with the issued player auth key."""
    manager = DummySessionManager()
    mock_provider.clear_session_event_feedback = AsyncMock(return_value=True)

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = anonymous_client.post(
            "/api/play/game",
            json={
                "api_key": anonymous_auth["api_key"],
                "game": "explore",
                "pc_choice": None,
                "npc_choice": None,
                "source": "api",
            },
        )

    session_id = create_resp.json()["session_id"]

    response = anonymous_client.delete(
        f"/api/sessions/{session_id}/events/evt-opening/feedback",
        headers={"Authorization": f"Bearer {anonymous_auth['api_key']}"},
    )

    assert response.status_code == 200
    assert response.json()["cleared"] is True
    assert manager.flush_calls == 1

    kwargs = mock_provider.clear_session_event_feedback.await_args.kwargs
    assert kwargs["session_id"] == session_id
    assert kwargs["player_id"] == "player-owner"
    assert kwargs["event_id"] == "evt-opening"


@pytest.mark.unit
def test_experiment_setup_returns_metadata_and_assignment_state(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Experiment setup should return forms, progress, and the current assignment state."""
    form = ExperimentForm(
        name="intake",
        trigger={"event": "before_all_assignments", "match": None},
        questions=[
            ExperimentFormQuestion(
                key="full_name",
                prompt="Full Name",
                answer_type="string",
                required=True,
            )
        ],
    )
    assignment = SimpleNamespace(
        assignment_id="asg-1",
        game_name="Explore",
        pc_hid="pc-1",
        npc_hid="npc-1",
        status="assigned",
    )
    run_config = SimpleNamespace(
        name="usability",
        description="Usability study",
        forms=[form],
        assignment_strategy=SimpleNamespace(
            allow_choice_if_multiple=False,
            require_completion=True,
        ),
    )

    with (
        patch.object(client.app.state.engine_run_manager, "run_config", run_config),
        patch("dcs_simulation_engine.api.routers.runs.EngineRunManager.ensure_run_async", new=AsyncMock()),
        patch(
            "dcs_simulation_engine.api.routers.runs.EngineRunManager.compute_progress_async",
            new=AsyncMock(
                return_value={
                    "total": 20,
                    "completed": 4,
                    "is_complete": False,
                }
            ),
        ),
        patch(
            "dcs_simulation_engine.api.routers.runs.EngineRunManager.get_player_state_async",
            new=AsyncMock(
                return_value={
                    "active_assignment": assignment,
                    "pending_assignment_form_ids": [],
                    "has_finished_experiment": False,
                    "eligible_assignment_options": [],
                    "pending_form_groups": [],
                    "assignments": [assignment],
                }
            ),
        ),
        patch(
            "dcs_simulation_engine.api.routers.runs.EngineRunManager.assignment_display_metadata_async",
            new=AsyncMock(return_value=ASSIGNMENT_DISPLAY_METADATA),
        ),
    ):
        response = client.get(
            "/api/run/setup",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["experiment_name"] == "usability"
    assert payload["current_assignment"]["assignment_id"] == "asg-1"
    assert payload["progress"] == {"total": 20, "completed": 4, "is_complete": False}
    assert payload["allow_choice_if_multiple"] is False
    assert payload["require_completion"] is True
    assert payload["eligible_assignment_options"] == []
    assert payload["pending_form_groups"] == []
    assert "character_hid" not in payload["current_assignment"]
    assert payload["current_assignment"]["game_description"] == "Game description"
    assert payload["forms"][0]["name"] == "intake"


@pytest.mark.unit
def test_experiment_form_group_submission_returns_group(
    client: TestClient,
) -> None:
    """Experiment form submission should store one pending group."""
    group = {
        "group_id": "before_all_assignments",
        "trigger": {"event": "before_all_assignments", "match": None},
    }

    with patch(
        "dcs_simulation_engine.api.routers.runs.EngineRunManager.submit_form_group_async",
        new=AsyncMock(return_value=group),
    ) as submit_mock:
        response = client.post(
            "/api/run/forms/submit",
            headers={"Authorization": "Bearer valid-key"},
            json={"group_id": "before_all_assignments", "responses": {"intake": {"full_name": "Ada"}}},
        )

    assert response.status_code == 200
    assert response.json() == group | {"assignment_id": None}
    assert submit_mock.await_args.kwargs["group_id"] == "before_all_assignments"


@pytest.mark.unit
def test_experiment_setup_requires_auth(client: TestClient) -> None:
    """Experiment setup should not expose progress or state without authentication."""
    response = client.get("/api/run/setup")

    assert response.status_code == 401


@pytest.mark.unit
def test_experiment_session_creation_returns_ws_path(
    client: TestClient,
) -> None:
    """Experiment session creation should return the websocket path for the assigned session."""
    entry = SimpleNamespace(session_id="sess-exp-1")
    assignment = SimpleNamespace(assignment_id="asg-3")
    start_mock = AsyncMock(return_value=(entry, assignment))

    with patch(
        "dcs_simulation_engine.api.routers.runs.EngineRunManager.start_assignment_session_async",
        new=start_mock,
    ):
        response = client.post(
            "/api/run/sessions",
            headers={"Authorization": "Bearer valid-key"},
            json={"source": "experiment", "assignment_id": "asg-3"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "sess-exp-1",
        "status": "active",
        "ws_path": "/api/play/game/sess-exp-1/ws",
    }
    assert start_mock.await_args.kwargs["assignment_id"] == "asg-3"


@pytest.mark.unit
def test_generic_play_blocks_experiment_gated_players(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Generic play endpoints should reject players who are assigned through an experiment."""
    mock_provider.get_latest_experiment_assignment_for_player.return_value = SimpleNamespace(
        experiment_name="usability",
    )

    response = client.post(
        "/api/play/game",
        json={"api_key": "valid-key", "game": "explore", "source": "api"},
    )

    assert response.status_code == 403
    assert "experiment" in response.json()["detail"].lower()


@pytest.mark.unit
def test_experiment_websocket_close_updates_assignment_status(client: TestClient) -> None:
    """Closing an experiment session should sync the assignment terminal state."""
    manager = DummySessionManager()

    def _start_session(*, provider, registry, experiment_name, player, source, assignment_id=None):
        entry = registry.add(
            player_id=player.id,
            game_name="Explore",
            manager=manager,  # type: ignore[arg-type]
            experiment_name=experiment_name,
            assignment_id="asg-live-1",
        )
        return entry, SimpleNamespace(assignment_id="asg-live-1")

    with (
        patch(
            "dcs_simulation_engine.api.routers.runs.EngineRunManager.start_assignment_session_async",
            new=AsyncMock(side_effect=_start_session),
        ),
        patch(
            "dcs_simulation_engine.api.routers.play.EngineRunManager.handle_session_terminal_state_async",
            new=AsyncMock(),
        ) as handle_terminal_mock,
    ):
        create_resp = client.post(
            "/api/run/sessions",
            headers={"Authorization": "Bearer valid-key"},
            json={"source": "experiment"},
        )
        session_id = create_resp.json()["session_id"]

        with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
            ws.send_json({"type": "auth", "api_key": "valid-key"})
            ws.receive_json()
            ws.receive_json()
            ws.receive_json()
            ws.send_json({"type": "close"})
            assert ws.receive_json() == {"type": "closed", "session_id": session_id}

    handle_terminal_mock.assert_awaited_once()
    kwargs = handle_terminal_mock.await_args.kwargs
    assert kwargs["experiment_name"] == "usability"
    assert kwargs["assignment_id"] == "asg-live-1"


@pytest.mark.functional
def test_experiment_multiple_assignments_can_each_be_resumed(
    patch_llm_client,
    async_mongo_provider,
) -> None:
    """A player can pause and resume more than one experiment assignment independently."""

    def _receive_until(ws, frame_type: str) -> list[dict]:
        frames: list[dict] = []
        while True:
            frame = ws.receive_json()
            frames.append(frame)
            if frame.get("type") == frame_type:
                return frames

    _player, access_key = asyncio.run(
        async_mongo_provider.create_player(
            player_data={
                "full_name": {"answer": "Resume Tester"},
                "email": "resume@example.com",
                "consent_signature": {"answer": ["I confirm that the information I have provided is true..."]},
            },
            issue_access_key=True,
        )
    )
    assert access_key is not None

    app = create_app(
        provider=async_mongo_provider,
        run_config=_run_config(
            allow_choice_if_multiple=True,
            require_completion=False,
            max_assignments_per_player=2,
        ),
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )

    headers = {"Authorization": f"Bearer {access_key}"}
    entry_payload = {
        "group_id": "before_all_assignments",
        "responses": {
            "intake": {
                "professional_background": "Research engineer",
                "technical_savviness": "On the higher end",
                "technical_savviness_explanation": "I work with simulation tools daily.",
            }
        }
    }

    with TestClient(app) as client:
        form_submit = client.post(
            "/api/run/forms/submit",
            headers=headers,
            json=entry_payload,
        )
        assert form_submit.status_code == 200, form_submit.text

        setup = client.get("/api/run/setup", headers=headers)
        assert setup.status_code == 200, setup.text

        paused_session_ids: dict[str, str] = {}
        used_options: set[tuple[str, str, str]] = set()
        for _index in range(2):
            setup_payload = setup.json()
            options = setup_payload["eligible_assignment_options"]
            option = next(item for item in options if (item["game_name"], item["pc_hid"], item["npc_hid"]) not in used_options)
            used_options.add((option["game_name"], option["pc_hid"], option["npc_hid"]))
            select_resp = client.post(
                "/api/run/assignments/select",
                headers=headers,
                json={
                    "game_name": option["game_name"],
                    "pc_hid": option["pc_hid"],
                    "npc_hid": option["npc_hid"],
                },
            )
            assert select_resp.status_code == 200, select_resp.text
            assignment = select_resp.json()
            create_resp = client.post(
                "/api/run/sessions",
                headers=headers,
                json={
                    "source": "experiment",
                    "assignment_id": assignment["assignment_id"],
                },
            )
            assert create_resp.status_code == 200, create_resp.text
            session_id = create_resp.json()["session_id"]
            paused_session_ids[assignment["assignment_id"]] = session_id

            with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
                ws.send_json({"type": "auth", "api_key": access_key})
                assert ws.receive_json()["type"] == "session_meta"
                opening_frames = _receive_until(ws, "turn_end")
                assert any(frame.get("type") == "event" for frame in opening_frames)

            setup = client.get("/api/run/setup", headers=headers)
            assert setup.status_code == 200, setup.text

        paused_setup = client.get("/api/run/setup", headers=headers)
        assert paused_setup.status_code == 200, paused_setup.text
        paused_assignments = {assignment["assignment_id"]: assignment for assignment in paused_setup.json()["assignments"]}

        for assignment_id, session_id in paused_session_ids.items():
            assignment = paused_assignments[assignment_id]
            assert assignment["status"] == "in_progress"
            assert assignment["active_session_id"] == session_id

            resume_resp = client.post(
                "/api/run/sessions",
                headers=headers,
                json={
                    "source": "experiment",
                    "assignment_id": assignment_id,
                },
            )
            assert resume_resp.status_code == 200, resume_resp.text
            assert resume_resp.json()["session_id"] == session_id

            with client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
                ws.send_json({"type": "auth", "api_key": access_key})
                assert ws.receive_json()["type"] == "session_meta"
                replay_frames = _receive_until(ws, "replay_end")
                assert replay_frames[0]["type"] == "replay_start"
                assert replay_frames[-1]["type"] == "replay_end"
                assert replay_frames[-1]["turns"] >= 1


@pytest.mark.unit
def test_experiment_assignment_form_group_submission_persists_response(client: TestClient) -> None:
    """Experiment form submission should accept assignment-scoped groups."""
    group = {
        "group_id": "after_assignment:asg-complete-1",
        "trigger": {"event": "after_assignment", "match": None},
        "assignment_id": "asg-complete-1",
    }

    with patch(
        "dcs_simulation_engine.api.routers.runs.EngineRunManager.submit_form_group_async",
        new=AsyncMock(return_value=group),
    ):
        response = client.post(
            "/api/run/forms/submit",
            headers={"Authorization": "Bearer valid-key"},
            json={
                "group_id": "after_assignment:asg-complete-1",
                "responses": {"usability_feedback": {"usability_issues": "None"}},
            },
        )

    assert response.status_code == 200
    assert response.json() == group


@pytest.mark.unit
def test_experiment_status_returns_aggregate_counts(client: TestClient) -> None:
    """Experiment status should return only the aggregate status fields."""
    with (
        patch(
            "dcs_simulation_engine.api.routers.runs.EngineRunManager.ensure_run_async",
            new=AsyncMock(),
        ),
        patch(
            "dcs_simulation_engine.api.routers.runs.EngineRunManager.compute_status_async",
            new=AsyncMock(
                return_value={
                    "is_open": True,
                    "total": 20,
                    "completed": 4,
                    "per_game": {
                        "Explore": {"total": 5, "completed": 2, "in_progress": 1},
                        "Foresight": {"total": 5, "completed": 1, "in_progress": 0},
                    },
                }
            ),
        ),
    ):
        response = client.get(
            "/api/run/status",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "is_open": True,
        "total": 20,
        "completed": 4,
        "per_game": {
            "Explore": {"total": 5, "completed": 2, "in_progress": 1},
            "Foresight": {"total": 5, "completed": 1, "in_progress": 0},
        },
    }


@pytest.mark.unit
def test_experiment_status_requires_auth(client: TestClient) -> None:
    """Experiment status should not be exposed without authentication."""
    response = client.get("/api/run/status")

    assert response.status_code == 401


@pytest.mark.unit
def test_remote_managed_server_config_reports_default_experiment(remote_managed_client: TestClient) -> None:
    """Remote-managed deployments should expose their default experiment name."""
    response = remote_managed_client.get("/api/server/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "standard",
        "authentication_required": True,
        "registration_enabled": True,
        "experiments_enabled": True,
        "default_experiment_name": "usability",
    }


@pytest.mark.unit
def test_remote_bootstrap_seeds_and_returns_admin_key(
    remote_managed_client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Remote bootstrap should seed the selected profile and issue an admin key."""
    seed_admin = MagicMock()

    with patch(
        "dcs_simulation_engine.api.routers.remote.create_provider_admin",
        return_value=SimpleNamespace(seed_database=seed_admin),
    ):
        response = remote_managed_client.post(
            "/api/remote/bootstrap",
            headers={
                "X-DCS-Bootstrap-Token": "bootstrap-secret",
                "X-DCS-Mongo-Seed-Filename": "players.json",
                "Content-Type": "application/json",
            },
            content=b"[]",
        )

    assert response.status_code == 200
    assert response.json() == {
        "player_id": "player-owner",
        "admin_api_key": "valid-key",
        "experiment_name": "usability",
    }
    seed_admin.assert_called_once()
    kwargs = mock_provider.create_player.call_args.kwargs
    assert kwargs["issue_access_key"] is True
    assert kwargs["player_data"]["role"] == "remote_admin"


@pytest.mark.unit
def test_remote_bootstrap_uses_requested_admin_key(
    remote_managed_client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Remote bootstrap should accept a caller-supplied admin key during deployment."""
    seed_admin = MagicMock()
    requested_key = "dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU"

    with patch(
        "dcs_simulation_engine.api.routers.remote.create_provider_admin",
        return_value=SimpleNamespace(seed_database=seed_admin),
    ):
        response = remote_managed_client.post(
            "/api/remote/bootstrap",
            headers={
                "X-DCS-Bootstrap-Token": "bootstrap-secret",
                "X-DCS-Mongo-Seed-Filename": "players.json",
                "X-DCS-Admin-Key": requested_key,
                "Content-Type": "application/json",
            },
            content=b"[]",
        )

    assert response.status_code == 200
    kwargs = mock_provider.create_player.call_args.kwargs
    assert kwargs["issue_access_key"] is False
    assert kwargs["access_key"] == requested_key


@pytest.mark.unit
def test_remote_status_is_public_and_reports_experiment_progress(
    remote_managed_client: TestClient,
) -> None:
    """Remote status should expose experiment-oriented progress without authentication."""
    with (
        patch(
            "dcs_simulation_engine.api.routers.remote.EngineRunManager.ensure_experiment_async",
            new=AsyncMock(),
        ),
        patch(
            "dcs_simulation_engine.api.routers.remote.EngineRunManager.compute_progress_async",
            new=AsyncMock(return_value={"total": 4, "completed": 1, "is_complete": False}),
        ),
        patch(
            "dcs_simulation_engine.api.routers.remote.EngineRunManager.compute_status_async",
            new=AsyncMock(
                return_value={
                    "is_open": True,
                    "total": 4,
                    "completed": 1,
                    "per_game": {"Explore": {"total": 1, "completed": 1, "in_progress": 0}},
                }
            ),
        ),
    ):
        response = remote_managed_client.get("/api/remote/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "experiment"
    assert payload["experiment_name"] == "usability"
    assert payload["progress"] == {"total": 4, "completed": 1, "is_complete": False}
    assert payload["experiment_status"] == {
        "is_open": True,
        "total": 4,
        "completed": 1,
        "per_game": {"Explore": {"total": 1, "completed": 1, "in_progress": 0}},
    }


@pytest.mark.unit
def test_remote_export_requires_admin_role(async_mongo_provider) -> None:
    """Remote DB export should reject non-admin authenticated players."""
    _player_record, api_key = asyncio.run(
        async_mongo_provider.create_player(
            player_data={"name": "Regular Player"},
            issue_access_key=True,
        )
    )

    app = create_app(
        provider=async_mongo_provider,
        run_config=_run_config(),
        remote_management_enabled=True,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        response = client.get("/api/remote/db-export", headers={"Authorization": f"Bearer {api_key}"})

    assert response.status_code == 403
    assert "admin" in response.json()["detail"].lower()


@pytest.mark.unit
def test_remote_export_streams_tarball_for_admin(async_mongo_provider) -> None:
    """Remote DB export should stream a gzipped tarball to the remote admin."""
    _admin_record, admin_key = asyncio.run(
        async_mongo_provider.create_player(
            player_data={"name": "Remote Admin", "role": "remote_admin"},
            issue_access_key=True,
        )
    )
    async_mongo_provider.get_db()["widgets"].insert_one({"name": "export-test"})

    app = create_app(
        provider=async_mongo_provider,
        run_config=_run_config(),
        remote_management_enabled=True,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        response = client.get("/api/remote/db-export", headers={"Authorization": f"Bearer {admin_key}"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"

    with tarfile.open(fileobj=BytesIO(response.content), mode="r:gz") as archive:
        names = archive.getnames()

    assert any(name.endswith("/widgets.json") for name in names)
    assert any(name.endswith("/players.json") for name in names)
    assert any(name.endswith("/__manifest__.json") for name in names)
    assert any(name.endswith("/widgets.__indexes__.json") for name in names)


@pytest.mark.unit
def test_remote_export_streams_zip_for_admin(async_mongo_provider) -> None:
    """Remote DB export should also support zip archives for the remote admin."""
    _admin_record, admin_key = asyncio.run(
        async_mongo_provider.create_player(
            player_data={"name": "Remote Admin", "role": "remote_admin"},
            issue_access_key=True,
        )
    )
    async_mongo_provider.get_db()["widgets"].insert_one({"name": "export-test"})

    app = create_app(
        provider=async_mongo_provider,
        default_experiment_name="usability",
        remote_management_enabled=True,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        response = client.get("/api/remote/db-export?format=zip", headers={"Authorization": f"Bearer {admin_key}"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()

    assert any(name.endswith("/widgets.json") for name in names)
    assert any(name.endswith("/players.json") for name in names)
    assert any(name.endswith("/__manifest__.json") for name in names)
    assert any(name.endswith("/widgets.__indexes__.json") for name in names)


@pytest.mark.unit
def test_remote_managed_registration_assigns_first_user_as_admin(async_mongo_provider) -> None:
    """The first remotely registered user should receive the remote admin role."""
    app = create_app(
        provider=async_mongo_provider,
        run_config=_run_config(),
        remote_management_enabled=True,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/player/registration",
            json={
                "full_name": "First Remote Admin",
                "email": "first-admin@example.com",
                "phone_number": "+1 555 123 4567",
                "consent_to_followup": True,
                "consent_signature": "First Remote Admin",
            },
        )

    assert response.status_code == 200
    created = asyncio.run(async_mongo_provider.get_players(access_key=response.json()["api_key"]))
    assert created is not None
    assert created.data["role"] == "remote_admin"


@pytest.mark.unit
def test_remote_managed_deployment_disables_generic_play(remote_managed_client: TestClient) -> None:
    """Experiment-only remote deployments should reject generic play endpoints."""
    response = remote_managed_client.get("/api/play/setup/explore")

    assert response.status_code == 409
    assert "experiment-only" in response.json()["detail"].lower()
