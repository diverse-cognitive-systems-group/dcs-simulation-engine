"""Unit tests for local engine CLI commands."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import engine as engine_command
from dcs_simulation_engine.utils.assets import DCSAssets
from typer.testing import CliRunner


def _write(path: Path, text: str = "asset") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_package_assets(root: Path) -> DCSAssets:
    _write(root / "compose.yml", "services: {}\n")
    _write(root / "docker" / "db.dockerfile")
    _write(root / "docker" / "api.dockerfile")
    _write(root / "docker" / "ui.dockerfile")
    _write(root / "docker" / "Caddyfile")
    _write(root / "examples" / "run_configs" / "demo.yml", "name: demo\n")
    _write(root / "database_seeds" / "dev" / "characters.json", "[]\n")
    _write(root / "ui_dist" / "index.html", "<div></div>\n")
    return DCSAssets(
        mode="package",
        root=root.resolve(),
        compose_file=root / "compose.yml",
        docker_dir=root / "docker",
        run_configs_dir=root / "examples" / "run_configs",
        default_run_config=root / "examples" / "run_configs" / "demo.yml",
        database_seeds_dir=root / "database_seeds",
        ui_dist_dir=root / "ui_dist",
    )


@pytest.mark.unit
def test_engine_start_requires_openrouter_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine start should fail before Docker checks when the API key is missing."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    docker_ready = MagicMock()
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", docker_ready)

    result = CliRunner().invoke(app, ["engine", "start", "--config", "examples/run_configs/demo.yml"])

    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY is required" in result.stdout
    docker_ready.assert_not_called()


@pytest.mark.unit
def test_engine_start_starts_compose_stack_with_config_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Engine start should mount the selected config and start db, api, and ui services."""
    config_path = tmp_path / "custom-run.yml"
    config_path.write_text("name: custom\n", encoding="utf-8")
    commands: list[list[str]] = []
    compose_env: dict[str, str] = {}
    override_payload = {}

    def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "up" in command:
            compose_env.update(env or {})
            override_path = Path(command[command.index("-f", command.index("-f") + 1) + 1])
            override_payload.update(yaml.safe_load(override_path.read_text(encoding="utf-8")))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(engine_command, "_run_checked", run_checked)
    monkeypatch.setattr(engine_command, "_wait_for_db", MagicMock())
    monkeypatch.setattr(engine_command, "_wait_for_http", MagicMock())
    start_model_harness = MagicMock()
    monkeypatch.setattr(engine_command, "_start_model_harness", start_model_harness)

    result = CliRunner().invoke(
        app,
        [
            "engine",
            "start",
            "--config",
            str(config_path),
            "--api-port",
            "8001",
            "--ui-port",
            "5174",
            "--db-port",
            "27018",
        ],
    )

    assert result.exit_code == 0
    up_command = commands[-1]
    assert up_command[-3:] == ["mongo", "api", "ui"]
    assert "--build" in up_command
    assert compose_env["DCS_RUN_CONFIG"] == "/app/run_config.yml"
    assert compose_env["DCS_API_PORT"] == "8001"
    assert compose_env["DCS_UI_PORT"] == "5174"
    assert compose_env["DCS_DB_PORT"] == "27018"
    assert override_payload["services"]["api"]["volumes"][0]["source"] == str(config_path)
    assert "✓ Database ready" in result.stdout
    assert "→ Access the app ui at: http://localhost:5174" in result.stdout
    assert "Stop: dcs engine stop" in result.stdout
    start_model_harness.assert_not_called()


@pytest.mark.unit
def test_engine_start_headless_skips_ui_and_can_follow_logs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Headless mode should start only db/api services and pass those services to log following."""
    commands: list[list[str]] = []
    follow_logs = MagicMock()

    def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(engine_command, "_run_checked", run_checked)
    monkeypatch.setattr(engine_command, "_wait_for_db", MagicMock())
    monkeypatch.setattr(engine_command, "_wait_for_http", MagicMock())
    monkeypatch.setattr(engine_command, "_follow_logs", follow_logs)
    start_model_harness = MagicMock()
    monkeypatch.setattr(engine_command, "_start_model_harness", start_model_harness)

    result = CliRunner().invoke(
        app,
        [
            "engine",
            "start",
            "--config",
            "examples/run_configs/demo.yml",
            "--headless",
            "--no-build",
            "--follow-logs",
        ],
    )

    assert result.exit_code == 0
    assert commands[-1][-2:] == ["mongo", "api"]
    assert "--build" not in commands[-1]
    assert "ui" not in commands[-1]
    follow_logs.assert_called_once()
    assert follow_logs.call_args.kwargs["services"] == ["mongo", "api"]
    assert "Headless mode" in result.stdout
    start_model_harness.assert_not_called()


@pytest.mark.unit
def test_engine_start_accepts_repeatable_player_model_and_starts_harness(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Repeatable --player-model values should be validated and handed to the model harness."""
    custom_player = tmp_path / "player.py"
    custom_player.write_text("async def decide(context): return 'I look around.'\n", encoding="utf-8")
    commands: list[list[str]] = []
    start_model_harness = MagicMock()

    def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        _ = env
        commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(engine_command, "_run_checked", run_checked)
    monkeypatch.setattr(engine_command, "_wait_for_db", MagicMock())
    monkeypatch.setattr(engine_command, "_wait_for_http", MagicMock())
    monkeypatch.setattr(engine_command, "_start_model_harness", start_model_harness)

    result = CliRunner().invoke(
        app,
        [
            "engine",
            "start",
            "--config",
            "examples/run_configs/demo.yml",
            "--headless",
            "--no-build",
            "--api-port",
            "8123",
            "--player-model",
            "openrouter:openai/gpt-4o",
            "--player-model",
            f"python:{custom_player}",
        ],
    )

    assert result.exit_code == 0, result.output
    assert commands[-1][-2:] == ["mongo", "api"]
    assert "ui" not in commands[-1]
    start_model_harness.assert_called_once()
    assert start_model_harness.call_args.kwargs["api_url"] == "http://localhost:8123"
    assert start_model_harness.call_args.kwargs["player_models"] == [
        "openrouter:openai/gpt-4o",
        f"python:{custom_player}",
    ]


@pytest.mark.unit
def test_engine_start_rejects_invalid_player_model_before_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed --player-model values should fail without touching Docker."""
    docker_ready = MagicMock()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", docker_ready)

    result = CliRunner().invoke(
        app,
        [
            "engine",
            "start",
            "--config",
            "examples/run_configs/demo.yml",
            "--player-model",
            "openrouter:",
        ],
    )

    assert result.exit_code == 1
    assert "Invalid --player-model value" in result.stdout
    docker_ready.assert_not_called()


@pytest.mark.unit
def test_engine_start_rejects_missing_python_player_model_before_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    """Python model player specs should point at an existing .py file."""
    docker_ready = MagicMock()

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", docker_ready)

    result = CliRunner().invoke(
        app,
        [
            "engine",
            "start",
            "--config",
            "examples/run_configs/demo.yml",
            "--player-model",
            "python:/no/such/player.py",
        ],
    )

    assert result.exit_code == 1
    assert "Python player model not found" in result.stdout
    docker_ready.assert_not_called()


@pytest.mark.unit
def test_host_path_for_docker_translates_repo_paths_from_devcontainer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Repo-local config paths should map through DCS_RUNS_DIR when Docker runs on the host."""
    engine_root = Path("/app")
    monkeypatch.setenv("DCS_RUNS_DIR", str(tmp_path / "runs"))

    host_path = engine_command._host_path_for_docker(engine_root / "examples/run_configs/demo.yml", engine_root=engine_root)

    assert host_path == tmp_path / "examples/run_configs/demo.yml"


@pytest.mark.unit
def test_engine_start_materializes_packaged_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Installed-package engine start should use a materialized Docker context."""
    package_assets = _make_package_assets(tmp_path / "package_assets")
    cache_base = tmp_path / "cache"
    commands: list[list[str]] = []
    compose_env: dict[str, str] = {}
    override_payload = {}

    def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "up" in command:
            compose_env.update(env or {})
            override_path = Path(command[command.index("-f", command.index("-f") + 1) + 1])
            override_payload.update(yaml.safe_load(override_path.read_text(encoding="utf-8")))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("DCS_RUNS_DIR", raising=False)
    monkeypatch.setenv("DCS_ENGINE_ASSETS_DIR", str(cache_base))
    monkeypatch.setattr(engine_command, "resolve_assets", MagicMock(return_value=package_assets))
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(engine_command, "_run_checked", run_checked)
    monkeypatch.setattr(engine_command, "_wait_for_db", MagicMock())
    monkeypatch.setattr(engine_command, "_wait_for_http", MagicMock())

    result = CliRunner().invoke(app, ["engine", "start", "--config", "demo.yml", "--no-build"])

    assert result.exit_code == 0
    engine_root = cache_base / engine_command._package_version()
    up_command = commands[-1]
    assert str(engine_root / "compose.yml") in up_command
    assert str(engine_root) in up_command
    assert "--build" not in up_command
    assert override_payload["services"]["api"]["volumes"][0]["source"] == str(engine_root / "examples" / "run_configs" / "demo.yml")
    assert compose_env["DCS_RUNS_DIR"] == str(Path.cwd() / "runs")
    assert (engine_root / "dcs_simulation_engine" / "cli" / "app.py").is_file()
    assert "uv sync" not in (engine_root / "docker" / "api.dockerfile").read_text(encoding="utf-8")
    assert "ui_dist/" in (engine_root / "docker" / "ui.dockerfile").read_text(encoding="utf-8")
    compose = yaml.safe_load((engine_root / "compose.yml").read_text(encoding="utf-8"))
    assert compose["services"]["ui"]["ports"] == ["${DCS_UI_PORT:-5173}:8080"]
    assert "reverse_proxy api:8000" in (engine_root / "docker" / "Caddyfile").read_text(encoding="utf-8")


@pytest.mark.unit
def test_engine_stop_runs_compose_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine stop should stop the compose project without requiring API keys."""
    commands: list[list[str]] = []
    compose_env: dict[str, str] = {}

    def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        compose_env.update(env or {})
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(engine_command, "_run_checked", run_checked)

    result = CliRunner().invoke(app, ["engine", "stop", "--clean"])

    assert result.exit_code == 0
    assert commands == [
        [
            "docker",
            "compose",
            "-f",
            str(Path.cwd() / "compose.yml"),
            "--project-directory",
            str(Path.cwd()),
            "-p",
            "dcs",
            "down",
            "--volumes",
        ]
    ]
    assert compose_env["OPENROUTER_API_KEY"] == "unused-for-engine-stop"
    assert "✓ Engine stopped" in result.stdout


@pytest.mark.unit
def test_engine_status_prints_service_health_and_run_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine status should combine Compose state, health checks, and run progress."""
    compose_services = [
        {"Service": "mongo", "State": "running", "Health": "healthy"},
        {"Service": "api", "State": "running", "Health": "healthy"},
        {"Service": "ui", "State": "running", "Health": ""},
    ]
    run_payload = {
        "run_name": "demo",
        "uptime": 754,
        "run_status": {
            "is_open": True,
            "total": 20,
            "completed": 3,
            "per_game": {
                "explore": {"total": 10, "completed": 2, "in_progress": 1},
                "goal_horizon": {"total": 10, "completed": 1, "in_progress": 0},
            },
        },
    }

    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(
        engine_command,
        "_run_capture",
        MagicMock(return_value=subprocess.CompletedProcess(["docker"], 0, stdout=json.dumps(compose_services), stderr="")),
    )
    monkeypatch.setattr(engine_command, "_db_is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(engine_command, "_http_is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(engine_command, "_fetch_json", MagicMock(return_value=run_payload))

    result = CliRunner().invoke(app, ["engine", "status"])

    assert result.exit_code == 0
    assert "Engine status: healthy" in result.stdout
    assert "✓ Database running and ready" in result.stdout
    assert "✓ Engine API at http://localhost:8000 ready" in result.stdout
    assert "✓ UI at http://localhost:5173 ready" in result.stdout
    assert "Run: demo" in result.stdout
    assert "Assignments: 3 / 20 completed" in result.stdout
    assert "explore: 2 / 10 completed, 1 in progress" in result.stdout


@pytest.mark.unit
def test_engine_status_json_exits_nonzero_when_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Engine status should produce machine-readable stopped status and a failing exit code."""
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(
        engine_command,
        "_run_capture",
        MagicMock(return_value=subprocess.CompletedProcess(["docker"], 0, stdout="[]", stderr="")),
    )

    result = CliRunner().invoke(app, ["engine", "status", "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "stopped"
    assert payload["project"] == "dcs"
