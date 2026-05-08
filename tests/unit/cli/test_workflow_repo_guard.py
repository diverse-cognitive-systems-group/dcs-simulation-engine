"""Tests for repo-only workflow command guards."""

from pathlib import Path

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.cli.commands import workflow
from typer.testing import CliRunner


@pytest.mark.unit
def test_repo_only_guard_returns_repo_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The guard should return the detected repo root when available."""
    monkeypatch.setattr(workflow, "find_repo_root", lambda: tmp_path)

    assert workflow._require_repo_checkout("hitl create") == tmp_path


@pytest.mark.unit
@pytest.mark.parametrize(
    "command",
    [
        ["hitl", "create", "NA", "--db", "dev"],
        ["hitl", "update", "NA"],
        ["hitl", "export", "NA"],
        ["publish", "characters", "missing-report.html"],
    ],
)
def test_repo_only_commands_fail_clearly_outside_repo(monkeypatch: pytest.MonkeyPatch, command: list[str]) -> None:
    """Repo-only commands should fail before doing work outside a checkout."""
    monkeypatch.setattr(workflow, "find_repo_root", lambda: None)

    result = CliRunner().invoke(app, command)

    assert result.exit_code == 1
    normalized_stdout = " ".join(result.stdout.split())
    assert "currently available only from a repository checkout" in normalized_stdout


@pytest.mark.unit
def test_report_commands_are_not_repo_only_guarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Report commands should remain universal and not use the workflow repo guard."""
    monkeypatch.setattr(workflow, "find_repo_root", lambda: None)
    report_path = tmp_path / "coverage.html"

    result = CliRunner().invoke(
        app,
        [
            "report",
            "results",
            str(Path("tests/data/example_results").resolve()),
            "--only",
            "metadata",
            "--report-path",
            str(report_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert report_path.is_file()
