"""Workflow-level CLI coverage for supported command families."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import engine as engine_command
from dcs_simulation_engine.cli.commands import remote as remote_command
from dcs_simulation_engine.hitl import Attempt, EvaluatorFeedback, Scenario, ScenarioFile, ScenarioGroup
from dcs_simulation_engine.hitl.generate import save_scenario_file
from dcs_simulation_engine.infra.remote import RemoteDeploymentResult, RemoteStatusResult
from typer.testing import CliRunner

pytestmark = pytest.mark.functional

_RUNNER = CliRunner()
_EXAMPLE_RESULTS = Path(__file__).parents[1] / "data" / "example_results"


def test_cli_local_engine_run_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start, inspect, and stop the local engine through the public CLI."""
    checked_commands: list[list[str]] = []
    run_payload = {
        "run_name": "demo",
        "uptime": 12,
        "run_status": {
            "is_open": True,
            "total": 2,
            "completed": 1,
            "per_game": {"explore": {"total": 2, "completed": 1, "in_progress": 1}},
        },
    }
    compose_services = [
        {"Service": "mongo", "State": "running", "Health": "healthy"},
        {"Service": "api", "State": "running", "Health": "healthy"},
        {"Service": "ui", "State": "running", "Health": ""},
    ]

    def run_checked(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        _ = env
        checked_commands.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(engine_command, "_ensure_docker_ready", MagicMock())
    monkeypatch.setattr(engine_command, "_run_checked", run_checked)
    monkeypatch.setattr(engine_command, "_wait_for_db", MagicMock())
    monkeypatch.setattr(engine_command, "_wait_for_http", MagicMock())
    monkeypatch.setattr(
        engine_command,
        "_run_capture",
        MagicMock(return_value=subprocess.CompletedProcess(["docker"], 0, stdout=json.dumps(compose_services), stderr="")),
    )
    monkeypatch.setattr(engine_command, "_db_is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(engine_command, "_http_is_ready", MagicMock(return_value=True))
    monkeypatch.setattr(engine_command, "_fetch_json", MagicMock(return_value=run_payload))

    start_result = _RUNNER.invoke(app, ["engine", "start", "--config", "examples/run_configs/demo.yml", "--no-build"])
    status_result = _RUNNER.invoke(app, ["engine", "status"])
    stop_result = _RUNNER.invoke(app, ["engine", "stop"])

    assert start_result.exit_code == 0, start_result.output
    assert status_result.exit_code == 0, status_result.output
    assert stop_result.exit_code == 0, stop_result.output
    assert any("up" in command for command in checked_commands)
    assert any("down" in command for command in checked_commands)
    assert "✓ Compose up: db, api, ui" in start_result.stdout
    assert "Engine status: healthy" in status_result.stdout
    assert "✓ Engine stopped" in stop_result.stdout


def test_cli_reporting_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Generate coverage and results report artifacts from the public CLI."""
    monkeypatch.chdir(tmp_path)
    results_report = tmp_path / "run_report.html"

    coverage_result = _RUNNER.invoke(app, ["report", "coverage", "--db", "dev"])
    results_result = _RUNNER.invoke(
        app,
        [
            "report",
            "results",
            str(_EXAMPLE_RESULTS),
            "--only",
            "metadata",
            "--report-path",
            str(results_report),
        ],
    )

    coverage_report = tmp_path / "results" / "character_coverage_dev.html"
    assert coverage_result.exit_code == 0, coverage_result.output
    assert results_result.exit_code == 0, results_result.output
    assert "<html" in coverage_report.read_text(encoding="utf-8")
    assert "<html" in results_report.read_text(encoding="utf-8")


def test_cli_hitl_evaluation_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Export a completed HITL scenario and generate a report from the exported results."""
    scenarios_path = tmp_path / "NA-test-cases.json"
    scenario_file = ScenarioFile(
        npc_hid="NA",
        generated_at="2026-04-23T00:00:00+00:00",
        scenario_groups=[
            ScenarioGroup(
                group_id="test-group",
                label="Test Group",
                expected_failure_mode="Test failure mode",
                pressure_category="test-pressure",
                scenarios=[
                    Scenario(
                        id="NA-test-001",
                        description="Test scenario",
                        game="Explore",
                        pc_hid="NA",
                        conversation_history=[{"role": "assistant", "content": "You are in a quiet room."}],
                        attempts=[
                            Attempt(
                                player_message="I inspect the table.",
                                simulator_response="The table is plain and sturdy.",
                                simulator_response_type="ai",
                                evaluator_feedback=EvaluatorFeedback(
                                    liked=True,
                                    comment="Grounded.",
                                    submitted_at="2026-04-23T00:05:00+00:00",
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )
    save_scenario_file(scenarios_path, scenario_file)
    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )

    export_dir = tmp_path / "hitl_results"
    report_path = tmp_path / "hitl_report.html"
    export_result = _RUNNER.invoke(app, ["hitl", "export", "NA", "--output-dir", str(export_dir)])
    report_result = _RUNNER.invoke(
        app,
        ["report", "results", str(export_dir), "--only", "metadata", "--report-path", str(report_path)],
    )

    assert export_result.exit_code == 0, export_result.output
    assert report_result.exit_code == 0, report_result.output
    assert (export_dir / "__manifest__.json").is_file()
    assert "<html" in report_path.read_text(encoding="utf-8")


def test_cli_remote_lifecycle_cycle(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Deploy, inspect, save, and stop a remote run through the public CLI with Fly test doubles."""
    config_path = tmp_path / "run.yaml"
    seed_path = tmp_path / "seed.json"
    save_path = tmp_path / "export.tar.gz"
    config_path.write_text(
        "name: usability-ca\nassignment_strategy:\n  strategy: random_unique_game\n  games: [explore]\n  quota_per_game: 1\n",
        encoding="utf-8",
    )
    seed_path.write_text("[]", encoding="utf-8")
    deploy = MagicMock(
        return_value=RemoteDeploymentResult(
            run_name="usability-ca",
            deployed_apps=["db", "api", "ui"],
            api_app="dcs-usability-ca-api",
            ui_app="dcs-usability-ca-ui",
            db_app="dcs-usability-ca-db",
            api_url="https://dcs-usability-ca-api.fly.dev",
            ui_url="https://dcs-usability-ca-ui.fly.dev",
            admin_api_key="admin-key",
            status_command="dcs remote status --uri https://dcs-usability-ca-api.fly.dev --admin-key <saved-admin-key>",
            save_command="dcs remote save ...",
            stop_command="dcs remote stop ...",
        )
    )
    fetch_status = MagicMock(
        return_value=RemoteStatusResult(
            api_url="https://dcs-usability-ca-api.fly.dev",
            run_name="usability-ca",
            run_status={"is_open": True, "total": 4, "completed": 1, "per_game": {}},
        )
    )
    save = MagicMock(return_value=save_path)
    stop = MagicMock(return_value=save_path)
    monkeypatch.setattr(remote_command, "deploy_remote_run", deploy)
    monkeypatch.setattr(remote_command, "fetch_remote_status", fetch_status)
    monkeypatch.setattr(remote_command, "save_remote_database", save)
    monkeypatch.setattr(remote_command, "stop_remote_run", stop)

    deploy_result = _RUNNER.invoke(
        app,
        [
            "remote",
            "deploy",
            "--config",
            str(config_path),
            "--openrouter-key",
            "or-key",
            "--mongo-seed-path",
            str(seed_path),
        ],
    )
    status_result = _RUNNER.invoke(
        app,
        ["remote", "status", "--uri", "https://dcs-usability-ca-api.fly.dev", "--admin-key", "admin-key"],
    )
    save_result = _RUNNER.invoke(
        app,
        [
            "remote",
            "save",
            "--uri",
            "https://dcs-usability-ca-api.fly.dev",
            "--admin-key",
            "admin-key",
            "--save-db-path",
            str(save_path),
        ],
    )
    stop_result = _RUNNER.invoke(
        app,
        [
            "remote",
            "stop",
            "--uri",
            "https://dcs-usability-ca-api.fly.dev",
            "--admin-key",
            "admin-key",
            "--save-db-path",
            str(save_path),
            "--api-app",
            "dcs-usability-ca-api",
            "--ui-app",
            "dcs-usability-ca-ui",
            "--db-app",
            "dcs-usability-ca-db",
        ],
    )

    assert deploy_result.exit_code == 0, deploy_result.output
    assert status_result.exit_code == 0, status_result.output
    assert save_result.exit_code == 0, save_result.output
    assert stop_result.exit_code == 0, stop_result.output
    assert "Deployment ready: usability-ca" in deploy_result.stdout
    assert '"completed": 1' in status_result.stdout
    assert "Database export written to:" in save_result.stdout
    assert "Remote deployment destroyed." in stop_result.stdout
