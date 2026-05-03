"""Helpers for API-level functional tests against real example run configs."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.core.engine_run_manager import EngineRunManager
from dcs_simulation_engine.core.run_config import RunConfig
from dcs_simulation_engine.core.session_manager import SessionManager
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUN_CONFIG_DIR = REPO_ROOT / "examples" / "run_configs"
RUN_CONFIG_FILES = sorted(RUN_CONFIG_DIR.glob("*.yml"))

REGISTRATION_PAYLOAD = {
    "full_name": "Example Config Tester",
    "email": "example-config-tester@example.com",
    "phone_number": "555-0100",
    "consent_to_followup": False,
    "consent_signature": "Example Config Tester",
}


def load_run_config(stem: str) -> RunConfig:
    """Load one example run config by filename stem."""
    return RunConfig.load(RUN_CONFIG_DIR / f"{stem}.yml")


def run_config_ids(path: Path) -> str:
    """Return stable parametrization ID for one run config path."""
    return path.stem


@contextmanager
def example_client(provider: Any, config: RunConfig) -> Iterator[TestClient]:
    """Create a TestClient for a real example run config."""
    original_engine_run_config = EngineRunManager._run_config
    original_session_run_config = SessionManager._run_config
    original_game_config_cache = dict(SessionManager._game_config_cache)
    app = create_app(
        provider=provider,
        run_config=config,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        EngineRunManager._run_config = original_engine_run_config
        SessionManager._run_config = original_session_run_config
        SessionManager._game_config_cache = original_game_config_cache


def register_player(client: TestClient) -> dict[str, str]:
    """Register a standard test participant and return auth payload."""
    response = client.post("/api/player/registration", json=REGISTRATION_PAYLOAD)
    assert response.status_code == 200, response.text
    return response.json()


def create_anonymous_player(client: TestClient) -> dict[str, str]:
    """Create an anonymous test participant and return auth payload."""
    response = client.post("/api/player/anonymous")
    assert response.status_code == 200, response.text
    return response.json()


def auth_headers(auth_payload: dict[str, str]) -> dict[str, str]:
    """Return Authorization header for a registration response."""
    return {"Authorization": f"Bearer {auth_payload['api_key']}"}


def run_setup(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    """Fetch run setup for the authenticated participant."""
    response = client.get("/api/run/setup", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def assert_authenticates(client: TestClient, auth_payload: dict[str, str]) -> None:
    """Assert the issued participant key is usable."""
    response = client.post("/api/player/auth", json={"api_key": auth_payload["api_key"]})
    assert response.status_code == 200, response.text
    assert response.json()["authenticated"] is True


def submit_pending_group(
    client: TestClient,
    headers: dict[str, str],
    setup_payload: dict[str, Any],
    *,
    event: str,
) -> dict[str, Any]:
    """Submit generated valid answers for one pending form group event."""
    group = pending_group(setup_payload, event=event)
    response = client.post(
        "/api/run/forms/submit",
        headers=headers,
        json={
            "group_id": group["group_id"],
            "responses": responses_for_group(group),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def pending_group(setup_payload: dict[str, Any], *, event: str) -> dict[str, Any]:
    """Return one pending form group by trigger event."""
    for group in setup_payload["pending_form_groups"]:
        if group["trigger"]["event"] == event:
            return group
    raise AssertionError(f"No pending form group for event {event}: {setup_payload['pending_form_groups']}")


def responses_for_group(group: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Generate valid responses from the API form schemas in one group."""
    return {
        form["name"]: {
            question["key"]: answer_for_question(question)
            for question in form.get("questions", [])
            if question.get("key") and question.get("answer_type")
        }
        for form in group.get("forms", [])
    }


def answer_for_question(question: dict[str, Any]) -> Any:
    """Generate one valid answer for a form question schema."""
    answer_type = question.get("answer_type")
    options = list(question.get("options") or [])

    if answer_type == "single_choice":
        assert options, f"single_choice question has no options: {question}"
        return options[0]
    if answer_type == "multi_choice":
        assert options, f"multi_choice question has no options: {question}"
        return [options[0]]
    if answer_type == "number":
        return 34
    if answer_type == "bool":
        return True
    if answer_type == "email":
        return "example-config-tester@example.com"
    if answer_type == "phone":
        return "555-0100"
    if answer_type == "string":
        return "Functional test response."

    raise AssertionError(f"Unsupported form answer type: {answer_type}")


def choose_or_locked_assignment(
    client: TestClient,
    headers: dict[str, str],
    setup_payload: dict[str, Any],
) -> dict[str, Any]:
    """Return a current assignment, selecting the first eligible option if required."""
    next_assignment = setup_payload["next_assignment"]
    if next_assignment["mode"] == "locked":
        assert setup_payload["current_assignment"] is not None
        return setup_payload["current_assignment"]

    assert next_assignment["mode"] == "choice", next_assignment
    option = setup_payload["eligible_assignment_options"][0]
    response = client.post(
        "/api/run/assignments/select",
        headers=headers,
        json={
            "game_name": option["game_name"],
            "pc_hid": option["pc_hid"],
            "npc_hid": option["npc_hid"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_run_session(
    client: TestClient,
    headers: dict[str, str],
    *,
    assignment_id: str | None = None,
) -> dict[str, Any]:
    """Create or resume a run assignment session."""
    response = client.post(
        "/api/run/sessions",
        headers=headers,
        json={"source": "run", "assignment_id": assignment_id},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "active"
    assert payload["ws_path"] == f"/api/play/game/{payload['session_id']}/ws"
    return payload
