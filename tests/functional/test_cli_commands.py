"""Workflow-level CLI coverage for supported command families."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import engine as engine_command
from dcs_simulation_engine.cli.commands import remote as remote_command
from dcs_simulation_engine.hitl.create import build_scaffold
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

    coverage_report = tmp_path / "reports" / "character_coverage_dev.html"
    assert coverage_result.exit_code == 0, coverage_result.output
    assert results_result.exit_code == 0, results_result.output
    assert "<html" in coverage_report.read_text(encoding="utf-8")
    assert "<html" in results_report.read_text(encoding="utf-8")


def test_cli_hitl_evaluation_cycle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Export a complete evaluation and include session descriptions in the character report."""
    monkeypatch.setattr("dcs_simulation_engine.hitl.create._SCENARIOS_DIR", tmp_path)
    source = tmp_path / "NA-evaluation.json"
    evaluation = build_scaffold("NA", "Explore")
    evaluation["evaluator_id"] = "reviewer & evaluator"
    evaluation["results"] = {"summary": "Consistent with the character.\nSeveral replies stayed grounded & clear."}
    rating = {"liked": True, "comment": "Grounded.", "doesnt_make_sense": False, "out_of_character": False, "other": False}
    evaluation["sessions"][0].update(
        session_id="root-id",
        description="Establish the scene & mood.",
        transcript=[
            {"type": "message", "source": "npc", "content": "You are in a quiet room.", "evaluator_feedback": rating},
            {
                "type": "branch",
                "session_id": "branch-id",
                "description": "Check the response to an ambiguous request.",
                "transcript": [
                    {"type": "message", "source": "pc", "content": "I inspect the table."},
                    {"type": "message", "source": "npc", "content": "The table is sturdy.", "evaluator_feedback": rating},
                ],
            },
        ],
    )
    source.write_text(json.dumps(evaluation), encoding="utf-8")

    export_dir = tmp_path / "hitl_results"
    report_path = tmp_path / "hitl_report.html"
    export_result = _RUNNER.invoke(app, ["hitl", "export", "NA", "--output-dir", str(export_dir)])
    assert export_result.exit_code == 0, export_result.output

    report_result = _RUNNER.invoke(
        app,
        ["report", "results", str(export_dir), "--only", "sim-quality", "--report-path", str(report_path)],
    )
    assert report_result.exit_code == 0, report_result.output
    assert (export_dir / "__manifest__.json").is_file()
    report_html = report_path.read_text(encoding="utf-8")
    assert "<html" in report_html
    character_report = (tmp_path / "per_character_quality" / "NA_quality_report.html").read_text(encoding="utf-8")
    for report in (report_html, character_report):
        first_section = report.split('<section id="section-', 1)[1].split("</section>", 1)[0]
        assert first_section.startswith('evaluation-summary"')
        assert "<h2>Summary</h2>" in first_section
        assert "Evaluation status: <strong>Complete</strong>" in first_section
        assert "Evaluator ID" in first_section and "reviewer &amp; evaluator" in first_section
        assert "Consistent with the character.\nSeveral replies stayed grounded &amp; clear." in first_section
        assert "Sessions (including branches)" in first_section and "PC turns" in first_section
    for fragment in (
        "Scenario Coverage",
        "Scores Summary",
        "In-Play Feedback",
        "Full Event Log",
        "Evaluator Description",
        "Establish the scene &amp; mood.",
        "Check the response to an ambiguous request.",
        "The table is sturdy.",
    ):
        assert fragment in character_report
    for table_id in ("event-feedback-table", "event-log-table"):
        table = character_report.split(f'id="{table_id}"', 1)[1].split("</table>", 1)[0]
        assert "<td>reviewer &amp; evaluator</td>" in table


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
