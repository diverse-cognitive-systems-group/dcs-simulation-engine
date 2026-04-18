"""Functional tests for the game setup API endpoint.

Tests GET /api/play/setup/{game_name} returns valid PC and NPC character
choices for each game. Uses the FastAPI TestClient in free-play mode so
no player authentication is required.
"""

import pytest
from dcs_simulation_engine.api.app import create_app
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


@pytest.mark.skip(reason="pending fix of dropdown sorting")
@pytest.mark.parametrize("game", ALL_GAMES)
def test_setup_dropdown_sorted_alphabetically(game, setup_client):
    """PC and NPC choices should be sorted alphabetically by display label."""
    ...


@pytest.mark.skip(reason="pending implementation of configurable dropdown selector")
@pytest.mark.parametrize("game", ALL_GAMES)
def test_setup_configurable_selector_per_run_config(game, setup_client):
    """Setup dropdown should reflect the selector configured by the run config."""
    ...
