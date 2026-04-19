"""Functional tests for the game setup API endpoint.

Tests GET /api/play/setup/{game_name} returns valid PC and NPC character
choices for each game. Uses the FastAPI TestClient in free-play mode so
no player authentication is required.
"""

import pytest
from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.core.session_manager import SessionManager
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.functional]

ALL_GAMES = ["explore", "Infer Intent", "Goal Horizon", "foresight", "teamwork"]


@pytest.fixture
def setup_client(_isolate_db_state, async_mongo_provider):
    """Build a TestClient in free-play mode wired to the seeded mongomock DB.

    Free-play mode skips player authentication, so no API key is needed.
    Character data comes from the auto-seeded mongomock DB (database_seeds/dev).
    """
    app = create_app(
        provider=async_mongo_provider,
        server_mode="free_play",
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("game", ALL_GAMES)
def test_setup_returns_valid_pc_and_npc_options(game, setup_client):
    """Setup endpoint returns non-empty PC and NPC lists for each game.

    GET /api/play/setup/{game} should return:
    - allowed: True
    - pcs: non-empty list with at least one entry having a non-empty hid
    - npcs: non-empty list with at least one entry having a non-empty hid
    """
    response = setup_client.get(f"/api/play/setup/{game}")

    assert response.status_code == 200, f"[{game}] Expected 200 from /api/play/setup, got {response.status_code}: {response.text}"

    data = response.json()
    assert data.get("allowed") is True, f"[{game}] Expected allowed=True, got: {data.get('allowed')}"

    pcs = data.get("pcs", [])
    npcs = data.get("npcs", [])

    assert len(pcs) > 0, f"[{game}] Expected non-empty pcs list; got: {pcs}"
    assert len(npcs) > 0, f"[{game}] Expected non-empty npcs list; got: {npcs}"


@pytest.mark.parametrize("game", ALL_GAMES)
def test_setup_pc_options_have_hid(game, setup_client):
    """Each PC and NPC choice must have a non-empty hid field.

    Confirms that character choices are populated with valid identifiers
    usable as pc_choice / npc_choice when creating a game session.
    """
    response = setup_client.get(f"/api/play/setup/{game}")
    assert response.status_code == 200

    data = response.json()
    for pc in data.get("pcs", []):
        assert pc.get("hid"), f"[{game}] PC entry missing non-empty hid: {pc}"

    for npc in data.get("npcs", []):
        assert npc.get("hid"), f"[{game}] NPC entry missing non-empty hid: {npc}"


@pytest.mark.anyio
async def test_session_manager_rejects_invalid_pc_choice(async_mongo_provider):
    """Session creation should reject PC choices outside the allowed returned set."""
    with pytest.raises(ValueError, match="Invalid pc_choice"):
        await SessionManager.create_async(
            game="explore",
            provider=async_mongo_provider,
            pc_choice="NOT_A_REAL_PC",
            npc_choice="FW",
        )


@pytest.mark.anyio
async def test_session_manager_rejects_invalid_npc_choice(async_mongo_provider):
    """Session creation should reject NPC choices outside the allowed returned set."""
    with pytest.raises(ValueError, match="Invalid npc_choice"):
        await SessionManager.create_async(
            game="explore",
            provider=async_mongo_provider,
            pc_choice="NA",
            npc_choice="NOT_A_REAL_NPC",
        )


def test_create_game_rejects_invalid_pc_choice(setup_client):
    """POST /api/play/game should fail fast for an invalid PC choice."""
    response = setup_client.post(
        "/api/play/game",
        json={"game": "explore", "pc_choice": "NOT_A_REAL_PC", "npc_choice": "FW", "source": "api"},
    )

    assert response.status_code == 400
    assert "Invalid pc_choice" in response.text


def test_create_game_rejects_invalid_npc_choice(setup_client):
    """POST /api/play/game should fail fast for an invalid NPC choice."""
    response = setup_client.post(
        "/api/play/game",
        json={"game": "explore", "pc_choice": "NA", "npc_choice": "NOT_A_REAL_NPC", "source": "api"},
    )

    assert response.status_code == 400
    assert "Invalid npc_choice" in response.text
