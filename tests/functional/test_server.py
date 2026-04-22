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
from dcs_simulation_engine.dal.base import (
    CharacterRecord,
    PlayerRecord,
    SessionEventRecord,
    SessionRecord,
)
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.games.ai_client import ScorerResult
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


def _player(player_id: str) -> PlayerRecord:
    """Create a lightweight player record for test provider responses."""
    return PlayerRecord(
        id=player_id,
        created_at=datetime.now(timezone.utc),
        access_key="raw-key",
        data={},
    )


def _session_record(
    *,
    session_id: str,
    player_id: str | None,
    game_name: str,
    termination_reason: str | None,
    npc_hid: str = "FW",
    turns_completed: int = 4,
) -> SessionRecord:
    return SessionRecord(
        session_id=session_id,
        player_id=player_id,
        game_name=game_name,
        status="closed" if termination_reason else "active",
        created_at=datetime.now(timezone.utc),
        data={
            MongoColumns.TERMINATION_REASON: termination_reason,
            MongoColumns.NPC_HID: npc_hid,
            MongoColumns.TURNS_COMPLETED: turns_completed,
        },
    )


def _session_event(
    *,
    seq: int,
    direction: str,
    event_type: str,
    event_source: str,
    content: str,
    data: dict | None = None,
) -> SessionEventRecord:
    return SessionEventRecord(
        session_id="s-infer-eval",
        seq=seq,
        event_id=f"evt-{seq}",
        event_ts=datetime.now(timezone.utc),
        direction=direction,
        event_type=event_type,
        event_source=event_source,
        content=content,
        data=data or {MongoColumns.VISIBLE_TO_USER: True},
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
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def free_play_client(mock_provider: MagicMock) -> TestClient:
    """Build a TestClient configured for anonymous free-play mode."""
    app = create_app(
        provider=mock_provider,
        server_mode="free_play",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def remote_managed_client(mock_provider: MagicMock) -> TestClient:
    """Build a TestClient configured for remote-managed experiment hosting."""
    app = create_app(
        provider=mock_provider,
        server_mode="standard",
        mongo_uri="mongodb://example",
        default_experiment_name="usability",
        remote_management_enabled=True,
        bootstrap_token="bootstrap-secret",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.unit
def test_remote_managed_free_play_status_reports_free_play_mode(mock_provider: MagicMock) -> None:
    """Remote-managed free-play deployments should report free-play mode without an experiment."""
    app = create_app(
        provider=mock_provider,
        server_mode="free_play",
        mongo_uri="mongodb://example",
        remote_management_enabled=True,
        bootstrap_token="bootstrap-secret",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        response = client.get("/api/remote/status")

    assert response.status_code == 200
    assert response.json()["mode"] == "free_play"
    assert response.json()["experiment_name"] is None


@pytest.mark.unit
def test_remote_bootstrap_in_free_play_returns_admin_without_experiment(mock_provider: MagicMock) -> None:
    """Remote bootstrap should still issue an admin key for free-play remote deployments."""
    seed_admin = MagicMock()

    app = create_app(
        provider=mock_provider,
        server_mode="free_play",
        mongo_uri="mongodb://example",
        remote_management_enabled=True,
        bootstrap_token="bootstrap-secret",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        with patch(
            "dcs_simulation_engine.api.routers.remote.create_provider_admin",
            return_value=SimpleNamespace(seed_database=seed_admin),
        ):
            response = client.post(
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
        "experiment_name": None,
    }


@pytest.mark.unit
def test_app_lifespan_preloads_game_configs(mock_provider: MagicMock) -> None:
    """App startup should preload game configs into SessionManager cache."""
    app = create_app(
        provider=mock_provider,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )

    with (
        patch("dcs_simulation_engine.api.app.SessionManager.preload_game_configs") as preload_mock,
        patch("dcs_simulation_engine.api.app.ExperimentManager.preload_experiment_configs") as preload_experiments_mock,
    ):
        with TestClient(app):
            pass

    preload_mock.assert_called_once_with()
    preload_experiments_mock.assert_called_once_with()


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
        "default_experiment_name": None,
    }


@pytest.mark.unit
def test_server_config_reports_free_play_mode(free_play_client: TestClient) -> None:
    """Server config should advertise anonymous capabilities in free-play mode."""
    response = free_play_client.get("/api/server/config")

    assert response.status_code == 200
    assert response.json() == {
        "mode": "free_play",
        "authentication_required": False,
        "registration_enabled": False,
        "experiments_enabled": False,
        "default_experiment_name": None,
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
def test_free_play_setup_options_allow_anonymous_access(free_play_client: TestClient) -> None:
    """Free-play setup should not require an Authorization header."""
    setup_config = SimpleNamespace(
        name="Explore",
        get_valid_characters=lambda **_kwargs: ([("PC Alpha", "pc-1")], [("NPC Beta", "npc-2")]),
    )

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.get_game_config_cached",
        return_value=setup_config,
    ):
        response = free_play_client.get("/api/play/setup/explore")

    assert response.status_code == 200
    assert response.json()["can_start"] is True
    assert response.json()["pcs"] == [{"hid": "pc-1", "label": "PC Alpha"}]


@pytest.mark.unit
def test_free_play_create_game_and_websocket_without_auth(free_play_client: TestClient) -> None:
    """Free-play should support anonymous session creation and websocket play."""
    manager = DummySessionManager()
    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = free_play_client.post(
            "/api/play/game",
            json={
                "game": "explore",
                "pc_choice": None,
                "npc_choice": None,
                "source": "api",
            },
        )

    assert create_resp.status_code == 200
    session_id = create_resp.json()["session_id"]

    with free_play_client.websocket_connect(f"/api/play/game/{session_id}/ws") as ws:
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
def test_free_play_disables_player_experiment_and_session_prefixes(
    free_play_client: TestClient,
) -> None:
    """Free-play should reject registration, experiments, and session APIs with 409s."""
    registration = free_play_client.post(
        "/api/player/registration",
        json={
            "full_name": "Ada Lovelace",
            "email": "ada@example.com",
            "phone_number": "+1 555 123 4567",
            "consent_to_followup": True,
            "consent_signature": "Ada",
        },
    )
    experiment = free_play_client.get("/api/experiments/usability/setup")
    sessions = free_play_client.get("/api/sessions/list")

    assert registration.status_code == 409
    assert "free play mode" in registration.json()["detail"].lower()
    assert experiment.status_code == 409
    assert sessions.status_code == 409


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
def test_infer_intent_evaluation_endpoint_generates_then_returns_cached_result(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """First evaluation request persists a hidden event; second request reuses it."""
    session_id = "s-infer-eval"
    persisted_events = [
        _session_event(
            seq=1,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="A pale creature retreats into the shadow.",
        ),
        _session_event(
            seq=2,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="I place a crumb nearby.",
        ),
        _session_event(
            seq=3,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="It glides toward the crumb and settles over it.",
        ),
        _session_event(
            seq=4,
            direction="inbound",
            event_type="command",
            event_source="user",
            content="/finish",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "finish"},
        ),
        _session_event(
            seq=5,
            direction="outbound",
            event_type="command",
            event_source="system",
            content="What do you think the NPC's goal or intention was?",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "finish"},
        ),
        _session_event(
            seq=6,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="It is trying to find food while staying protected.",
        ),
        _session_event(
            seq=7,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="No additional feedback.",
        ),
    ]
    mock_provider.get_session = AsyncMock(
        return_value=_session_record(
            session_id=session_id,
            player_id="player-owner",
            game_name="Infer Intent",
            termination_reason="game_completed",
        )
    )
    mock_provider.list_session_events = AsyncMock(side_effect=lambda **_kwargs: list(persisted_events))
    mock_provider.get_character = AsyncMock(
        return_value=CharacterRecord(
            hid="FW",
            name="Flatworm",
            short_description="A flatworm.",
            data={"long_description": "A cautious feeder.", "abilities": "Can move and feed."},
        )
    )

    async def _append_session_event(**kwargs):
        event = SessionEventRecord(
            session_id=kwargs["session_id"],
            seq=8,
            event_id="evt-llm-eval",
            event_ts=datetime.now(timezone.utc),
            direction=kwargs["direction"],
            event_type=kwargs["event_type"],
            event_source=kwargs["event_source"],
            content=kwargs["content"],
            data={
                MongoColumns.CONTENT_FORMAT: kwargs["content_format"],
                MongoColumns.TURN_INDEX: kwargs["turn_index"],
                MongoColumns.VISIBLE_TO_USER: kwargs["visible_to_user"],
            },
        )
        persisted_events.append(event)
        return event

    mock_provider.append_session_event = AsyncMock(side_effect=_append_session_event)
    scorer_mock = AsyncMock(
        return_value=ScorerResult(
            evaluation={"tier": 3, "score": 95, "reasoning": "Strong match."},
            raw_json='{"tier": 3, "score": 95, "reasoning": "Strong match."}',
        )
    )

    with patch(
        "dcs_simulation_engine.api.infer_intent_evaluation.ScorerClient.score",
        new=scorer_mock,
    ):
        first = client.post(
            f"/api/sessions/{session_id}/infer-intent/evaluation",
            headers={"Authorization": "Bearer valid-key"},
        )
        second = client.post(
            f"/api/sessions/{session_id}/infer-intent/evaluation",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert first.status_code == 200
    assert first.json() == {
        "session_id": session_id,
        "event_id": "evt-llm-eval",
        "cached": False,
        "evaluation": {
            "tier": 3,
            "score": 95,
            "reasoning": "Strong match.",
        },
    }

    assert second.status_code == 200
    assert second.json() == {
        "session_id": session_id,
        "event_id": "evt-llm-eval",
        "cached": True,
        "evaluation": {
            "tier": 3,
            "score": 95,
            "reasoning": "Strong match.",
        },
    }
    assert scorer_mock.await_count == 1
    assert mock_provider.append_session_event.await_count == 1


@pytest.mark.unit
def test_infer_intent_evaluation_endpoint_supports_free_play_sessions(
    free_play_client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Free-play should allow Infer Intent evaluation for anonymous sessions by session id."""
    app = free_play_client.app
    registry = app.state.registry
    entry = registry.add(player_id=None, game_name="Infer Intent", manager=DummySessionManager())
    registry.close(entry.session_id)

    session_id = entry.session_id
    persisted_events = [
        _session_event(
            seq=1,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="A pale creature retreats into the shadow.",
        ),
        _session_event(
            seq=2,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="I place a crumb nearby.",
        ),
        _session_event(
            seq=3,
            direction="outbound",
            event_type="message",
            event_source="npc",
            content="It glides toward the crumb and settles over it.",
        ),
        _session_event(
            seq=4,
            direction="inbound",
            event_type="command",
            event_source="user",
            content="/finish",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "finish"},
        ),
        _session_event(
            seq=5,
            direction="outbound",
            event_type="command",
            event_source="system",
            content="What do you think the NPC's goal or intention was?",
            data={MongoColumns.VISIBLE_TO_USER: True, MongoColumns.COMMAND_NAME: "finish"},
        ),
        _session_event(
            seq=6,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="It is trying to find food while staying protected.",
        ),
        _session_event(
            seq=7,
            direction="inbound",
            event_type="message",
            event_source="user",
            content="No additional feedback.",
        ),
    ]
    mock_provider.get_session = AsyncMock(
        return_value=_session_record(
            session_id=session_id,
            player_id=None,
            game_name="Infer Intent",
            termination_reason="game_completed",
        )
    )
    mock_provider.list_session_events = AsyncMock(side_effect=lambda **_kwargs: list(persisted_events))
    mock_provider.get_character = AsyncMock(
        return_value=CharacterRecord(
            hid="FW",
            name="Flatworm",
            short_description="A flatworm.",
            data={"long_description": "A cautious feeder.", "abilities": "Can move and feed."},
        )
    )

    async def _append_session_event(**kwargs):
        event = SessionEventRecord(
            session_id=kwargs["session_id"],
            seq=8,
            event_id="evt-freeplay-llm-eval",
            event_ts=datetime.now(timezone.utc),
            direction=kwargs["direction"],
            event_type=kwargs["event_type"],
            event_source=kwargs["event_source"],
            content=kwargs["content"],
            data={
                MongoColumns.CONTENT_FORMAT: kwargs["content_format"],
                MongoColumns.TURN_INDEX: kwargs["turn_index"],
                MongoColumns.VISIBLE_TO_USER: kwargs["visible_to_user"],
            },
        )
        persisted_events.append(event)
        return event

    mock_provider.append_session_event = AsyncMock(side_effect=_append_session_event)
    scorer_mock = AsyncMock(
        return_value=ScorerResult(
            evaluation={"tier": 3, "score": 95, "reasoning": "Strong match."},
            raw_json='{"tier": 3, "score": 95, "reasoning": "Strong match."}',
        )
    )

    with patch(
        "dcs_simulation_engine.api.infer_intent_evaluation.ScorerClient.score",
        new=scorer_mock,
    ):
        first = free_play_client.post(f"/api/sessions/{session_id}/infer-intent/evaluation")
        second = free_play_client.post(f"/api/sessions/{session_id}/infer-intent/evaluation")

    assert first.status_code == 200
    assert first.json() == {
        "session_id": session_id,
        "event_id": "evt-freeplay-llm-eval",
        "cached": False,
        "evaluation": {
            "tier": 3,
            "score": 95,
            "reasoning": "Strong match.",
        },
    }

    assert second.status_code == 200
    assert second.json() == {
        "session_id": session_id,
        "event_id": "evt-freeplay-llm-eval",
        "cached": True,
        "evaluation": {
            "tier": 3,
            "score": 95,
            "reasoning": "Strong match.",
        },
    }
    assert scorer_mock.await_count == 1
    assert mock_provider.append_session_event.await_count == 1


def test_infer_intent_evaluation_endpoint_rejects_incomplete_session(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Evaluation is unavailable until the Infer Intent session is completed."""
    mock_provider.get_session = AsyncMock(
        return_value=_session_record(
            session_id="s-incomplete",
            player_id="player-owner",
            game_name="Infer Intent",
            termination_reason="user_exit_command",
        )
    )

    response = client.post(
        "/api/sessions/s-incomplete/infer-intent/evaluation",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 409
    assert "not available until the game is completed" in response.json()["detail"]


@pytest.mark.unit
def test_infer_intent_evaluation_endpoint_returns_not_found_for_non_owner(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """The evaluation endpoint does not reveal sessions the caller does not own."""
    mock_provider.get_session = AsyncMock(return_value=None)

    response = client.post(
        "/api/sessions/s-missing/infer-intent/evaluation",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.unit
def test_infer_intent_evaluation_endpoint_rejects_other_games(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Infer Intent evaluation is only available for Infer Intent sessions."""
    mock_provider.get_session = AsyncMock(
        return_value=_session_record(
            session_id="s-explore",
            player_id="player-owner",
            game_name="Explore",
            termination_reason="game_completed",
        )
    )

    response = client.post(
        "/api/sessions/s-explore/infer-intent/evaluation",
        headers={"Authorization": "Bearer valid-key"},
    )

    assert response.status_code == 409
    assert "only available for completed infer intent sessions" in response.json()["detail"].lower()


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
def test_free_play_feedback_submit_flushes_live_session_and_persists(
    free_play_client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Free-play sessions should still expose per-message feedback controls."""
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
        create_resp = free_play_client.post(
            "/api/play/game",
            json={"game": "explore", "pc_choice": None, "npc_choice": None, "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    response = free_play_client.post(
        f"/api/sessions/{session_id}/events/evt-opening/feedback",
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
    assert kwargs["player_id"] is None
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
def test_free_play_feedback_clear_flushes_live_session_and_persists(
    free_play_client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Free-play feedback clearing should work without a player auth key."""
    manager = DummySessionManager()
    mock_provider.clear_session_event_feedback = AsyncMock(return_value=True)

    with patch(
        "dcs_simulation_engine.api.routers.play.SessionManager.create_async",
        new=AsyncMock(return_value=manager),
    ):
        create_resp = free_play_client.post(
            "/api/play/game",
            json={"game": "explore", "pc_choice": None, "npc_choice": None, "source": "api"},
        )

    session_id = create_resp.json()["session_id"]

    response = free_play_client.delete(f"/api/sessions/{session_id}/events/evt-opening/feedback")

    assert response.status_code == 200
    assert response.json()["cleared"] is True
    assert manager.flush_calls == 1

    kwargs = mock_provider.clear_session_event_feedback.await_args.kwargs
    assert kwargs["session_id"] == session_id
    assert kwargs["player_id"] is None
    assert kwargs["event_id"] == "evt-opening"


@pytest.mark.unit
def test_experiment_setup_returns_metadata_and_assignment_state(
    client: TestClient,
    mock_provider: MagicMock,
) -> None:
    """Experiment setup should return forms, progress, and the current assignment state."""
    form = ExperimentForm(
        name="intake",
        before_or_after="before",
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
        character_hid="pc-1",
        status="assigned",
    )

    with (
        patch(
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.get_experiment_config_cached",
            return_value=SimpleNamespace(
                name="usability",
                description="Usability study",
                forms=[form],
                assignment_strategy=SimpleNamespace(assignment_mode="random_unique"),
            ),
        ),
        patch(
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.ensure_experiment_async",
            new=AsyncMock(),
        ),
        patch(
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.compute_progress_async",
            new=AsyncMock(
                return_value={
                    "total": 20,
                    "completed": 4,
                    "is_complete": False,
                }
            ),
        ),
        patch(
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.get_player_state_async",
            new=AsyncMock(
                return_value={
                    "active_assignment": assignment,
                    "pending_post_play": None,
                    "has_finished_experiment": False,
                    "has_submitted_before_forms": True,
                    "assignments": [assignment],
                }
            ),
        ),
    ):
        response = client.get(
            "/api/experiments/usability/setup",
            headers={"Authorization": "Bearer valid-key"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["experiment_name"] == "usability"
    assert payload["current_assignment"]["assignment_id"] == "asg-1"
    assert payload["progress"] == {"total": 20, "completed": 4, "is_complete": False}
    assert payload["pending_post_play"] is False
    assert payload["forms"][0]["name"] == "intake"


@pytest.mark.unit
def test_experiment_before_play_submission_returns_assignment(
    client: TestClient,
) -> None:
    """Experiment before-play submission should return the current assignment for the signed-in player."""
    assignment = SimpleNamespace(
        assignment_id="asg-2",
        game_name="Foresight",
        character_hid="pc-2",
        status="assigned",
    )

    with patch(
        "dcs_simulation_engine.api.routers.experiments.ExperimentManager.submit_before_play_async",
        new=AsyncMock(return_value=assignment),
    ):
        response = client.post(
            "/api/experiments/usability/players",
            headers={"Authorization": "Bearer valid-key"},
            json={"responses": {"intake": {"full_name": "Ada"}}},
        )

    assert response.status_code == 200
    assert response.json() == {
        "assignment": {
            "assignment_id": "asg-2",
            "game_name": "Foresight",
            "character_hid": "pc-2",
            "status": "assigned",
        },
    }


@pytest.mark.unit
def test_experiment_setup_requires_auth(client: TestClient) -> None:
    """Experiment setup should not expose progress or state without authentication."""
    response = client.get("/api/experiments/usability/setup")

    assert response.status_code == 401


@pytest.mark.unit
def test_experiment_session_creation_returns_ws_path(
    client: TestClient,
) -> None:
    """Experiment session creation should return the websocket path for the assigned session."""
    entry = SimpleNamespace(session_id="sess-exp-1")
    assignment = SimpleNamespace(assignment_id="asg-3")

    with patch(
        "dcs_simulation_engine.api.routers.experiments.ExperimentManager.start_assignment_session_async",
        new=AsyncMock(return_value=(entry, assignment)),
    ):
        response = client.post(
            "/api/experiments/usability/sessions",
            headers={"Authorization": "Bearer valid-key"},
            json={"source": "experiment"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "sess-exp-1",
        "status": "active",
        "ws_path": "/api/play/game/sess-exp-1/ws",
    }


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

    def _start_session(*, provider, registry, experiment_name, player, source):
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
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.start_assignment_session_async",
            new=AsyncMock(side_effect=_start_session),
        ),
        patch(
            "dcs_simulation_engine.api.routers.play.ExperimentManager.handle_session_terminal_state_async",
            new=AsyncMock(),
        ) as handle_terminal_mock,
    ):
        create_resp = client.post(
            "/api/experiments/usability/sessions",
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


@pytest.mark.unit
def test_experiment_post_play_submission_persists_response(client: TestClient) -> None:
    """Experiment post-play submission should target the latest completed assignment."""
    assignment = SimpleNamespace(
        assignment_id="asg-complete-1",
        game_name="Explore",
        character_hid="pc-1",
        status="completed",
    )

    with patch(
        "dcs_simulation_engine.api.routers.experiments.ExperimentManager.store_post_play_async",
        new=AsyncMock(return_value=assignment),
    ):
        response = client.post(
            "/api/experiments/usability/post-play",
            headers={"Authorization": "Bearer valid-key"},
            json={"responses": {"usability_feedback": {"usability_issues": "None"}}},
        )

    assert response.status_code == 200
    assert response.json() == {
        "assignment_id": "asg-complete-1",
        "game_name": "Explore",
        "character_hid": "pc-1",
        "status": "completed",
    }


@pytest.mark.unit
def test_experiment_status_returns_aggregate_counts(client: TestClient) -> None:
    """Experiment status should return only the aggregate status fields."""
    with (
        patch(
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.ensure_experiment_async",
            new=AsyncMock(),
        ),
        patch(
            "dcs_simulation_engine.api.routers.experiments.ExperimentManager.compute_status_async",
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
            "/api/experiments/usability/status",
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
    response = client.get("/api/experiments/usability/status")

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
            "dcs_simulation_engine.api.routers.remote.ExperimentManager.ensure_experiment_async",
            new=AsyncMock(),
        ),
        patch(
            "dcs_simulation_engine.api.routers.remote.ExperimentManager.compute_progress_async",
            new=AsyncMock(return_value={"total": 4, "completed": 1, "is_complete": False}),
        ),
        patch(
            "dcs_simulation_engine.api.routers.remote.ExperimentManager.compute_status_async",
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
        server_mode="standard",
        default_experiment_name="usability",
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
        server_mode="standard",
        default_experiment_name="usability",
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
        server_mode="standard",
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
        server_mode="standard",
        default_experiment_name="usability",
        remote_management_enabled=True,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/player/registration",
            json={
                "full_name": "Ada Lovelace",
                "email": "ada@example.com",
                "phone_number": "+1 555 123 4567",
                "consent_to_followup": True,
                "consent_signature": "Ada",
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
