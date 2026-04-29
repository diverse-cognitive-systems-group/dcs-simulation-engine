"""Functional smoke tests for the supported API usage example scripts."""

import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
import uvicorn
from dcs_simulation_engine.api.app import create_app
from dcs_simulation_engine.core.run_config import RunConfig

pytestmark = pytest.mark.functional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXAMPLES_DIR = _REPO_ROOT / "examples" / "api_usage"
_IGNORED_EXAMPLE_STEMS = {"infer_intent_eval"}
_SCRIPT_CONFIG = {
    "explore": {"registration_required": False, "args": []},
    "infer_intent": {"registration_required": False, "args": []},
    "goal_horizon": {"registration_required": False, "args": []},
    "foresight": {"registration_required": False, "args": []},
    "register_auth_play_close": {"registration_required": True, "args": []},
}


def _run_config(*, registration_required: bool) -> RunConfig:
    """Return a compact run config for API usage smoke tests."""
    return RunConfig.model_validate(
        {
            "name": "api-usage-registration" if registration_required else "api-usage-anonymous",
            "description": "API usage example smoke test",
            "ui": {"registration_required": registration_required},
            "players": {"humans": {"all": True}},
            "games": [
                {"name": "Explore"},
                {"name": "Infer Intent"},
                {"name": "Foresight"},
                {"name": "Goal Horizon"},
                {"name": "Teamwork"},
            ],
            "next_game_strategy": {
                "strategy": {
                    "id": "full_character_access",
                    "allow_choice_if_multiple": True,
                    "require_completion": False,
                }
            },
            "forms": [],
        }
    )


def _find_open_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


@contextmanager
def _run_live_server(*, provider, run_config: RunConfig):
    """Run the FastAPI app under uvicorn on a temporary local port."""
    port = _find_open_port()
    app = create_app(
        provider=provider,
        run_config=run_config,
        session_ttl_seconds=3600,
        sweep_interval_seconds=3600,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        ws="websockets-sansio",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10.0
    try:
        while time.time() < deadline:
            try:
                response = httpx.get(f"{base_url}/healthz", timeout=0.25)
                if response.status_code == 200:
                    yield base_url
                    break
            except Exception:
                time.sleep(0.05)
        else:
            raise RuntimeError(f"Timed out waiting for example test server at {base_url}")
    finally:
        server.should_exit = True
        thread.join(timeout=10.0)


def test_api_usage_example_config_covers_all_supported_scripts() -> None:
    """Every kept example script should be explicitly covered by the smoke-test config."""
    discovered = {path.stem for path in _EXAMPLES_DIR.glob("*.py")}
    supported = discovered - _IGNORED_EXAMPLE_STEMS
    assert supported == set(_SCRIPT_CONFIG)


@pytest.mark.parametrize("stem", sorted(_SCRIPT_CONFIG))
def test_api_usage_example_runs(
    stem: str,
    async_mongo_provider,
    patch_llm_client,
) -> None:
    """Each supported example script should run cleanly against a live local server."""
    _ = patch_llm_client
    script = _EXAMPLES_DIR / f"{stem}.py"
    config = _SCRIPT_CONFIG[stem]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_REPO_ROOT)

    run_config = _run_config(registration_required=config["registration_required"])
    with _run_live_server(provider=async_mongo_provider, run_config=run_config) as base_url:
        result = subprocess.run(
            [sys.executable, str(script), "--base-url", base_url, *config["args"]],
            cwd=_REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60.0,
        )

    combined_output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, combined_output
    assert "Traceback (most recent call last)" not in combined_output
