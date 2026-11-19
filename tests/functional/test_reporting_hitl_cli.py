"""Functional tests for the dcs CLI.

Runs every dcs command and asserts:
  - exit code 0
  - all HTML reports are parseable (contain <html>, no Python Traceback)
"""

import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.hitl.create import build_scaffold
from typer.testing import CliRunner

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RUNNER = CliRunner()

_EXAMPLE_RESULTS = Path(__file__).parents[1] / "data" / "example_results"
_REPO_ROOT = Path(__file__).parents[2]
_DEV_CHARS = _REPO_ROOT / "database_seeds" / "dev" / "characters.json"

_VALID_SECTION_SLUGS = [
    "form-responses",
    "metadata",
    "npc-coverage",
    "pc-coverage",
    "player-feedback",
    "player-performance",
    "runs-overview",
    "sim-quality",
    "system-errors",
    "system-performance",
    "event-log",
]


class _HTMLValidator(HTMLParser):
    """Minimal parser that raises on malformed HTML."""

    def __init__(self):
        super().__init__()
        self.found_html_tag = False

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.found_html_tag = True


def _assert_valid_html(path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    validator = _HTMLValidator()
    validator.feed(content)
    assert validator.found_html_tag, f"No <html> tag found in {path}"
    assert "Traceback (most recent call last)" not in content, f"Python traceback found in {path}"
    # alert-danger divs are the render-failure template in run_analysis() / run_coverage_report()
    assert 'class="alert alert-danger"' not in content, (
        f"Section render error found in {path} — check for missing dependencies or data issues"
    )


# ---------------------------------------------------------------------------
# report coverage
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_report_coverage_dev(tmp_path, monkeypatch):
    """Dcs report coverage --db dev writes a valid HTML report."""
    monkeypatch.chdir(tmp_path)

    result = _RUNNER.invoke(app, ["report", "coverage", "--db", "dev"])

    assert result.exit_code == 0, result.output
    out_html = tmp_path / "reports" / "character_coverage_dev.html"
    assert out_html.exists(), f"Expected report at {out_html}"
    _assert_valid_html(out_html)


@pytest.mark.functional
def test_report_coverage_prod(tmp_path, monkeypatch):
    """Dcs report coverage --db prod writes a valid HTML report."""
    monkeypatch.chdir(tmp_path)

    result = _RUNNER.invoke(app, ["report", "coverage", "--db", "prod"])

    assert result.exit_code == 0, result.output
    out_html = tmp_path / "reports" / "character_coverage_prod.html"
    assert out_html.exists(), f"Expected report at {out_html}"
    _assert_valid_html(out_html)


# ---------------------------------------------------------------------------
# report results
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_report_results_default_sections(tmp_path):
    """Dcs report results with default sections produces a valid HTML report."""
    out = tmp_path / "report.html"

    result = _RUNNER.invoke(
        app,
        ["report", "results", str(_EXAMPLE_RESULTS), "--report-path", str(out)],
    )

    assert result.exit_code == 0, result.output
    assert out.exists(), f"Expected report at {out}"
    _assert_valid_html(out)


@pytest.mark.functional
def test_report_results_default_path_writes_to_reports_dir(tmp_path, monkeypatch):
    """Dcs report results without --report-path writes to ./reports."""
    monkeypatch.chdir(tmp_path)

    result = _RUNNER.invoke(app, ["report", "results", str(_EXAMPLE_RESULTS), "--only", "metadata"])

    assert result.exit_code == 0, result.output
    out = tmp_path / "reports" / "results_report.html"
    assert out.exists(), f"Expected report at {out}"
    _assert_valid_html(out)


@pytest.mark.functional
def test_report_results_sim_quality(tmp_path):
    """Dcs report results --only sim-quality produces a valid HTML report and per-character sub-reports."""
    out = tmp_path / "report.html"

    result = _RUNNER.invoke(
        app,
        [
            "report",
            "results",
            str(_EXAMPLE_RESULTS),
            "--only",
            "sim-quality",
            "--report-path",
            str(out),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out.exists(), f"Expected report at {out}"
    _assert_valid_html(out)

    per_char_dir = tmp_path / "per_character_quality"
    assert per_char_dir.exists(), "Expected per_character_quality/ directory to be created"


@pytest.mark.functional
@pytest.mark.parametrize("slug", _VALID_SECTION_SLUGS)
def test_report_results_each_section(tmp_path, slug):
    """Dcs report results --only <slug> runs without error for every section."""
    out = tmp_path / f"report_{slug}.html"

    result = _RUNNER.invoke(
        app,
        [
            "report",
            "results",
            str(_EXAMPLE_RESULTS),
            "--only",
            slug,
            "--report-path",
            str(out),
        ],
    )

    assert result.exit_code == 0, f"Section {slug!r} failed:\n{result.output}"
    assert out.exists(), f"Expected report at {out} for section {slug!r}"
    _assert_valid_html(out)


# ---------------------------------------------------------------------------
# hitl create
# ---------------------------------------------------------------------------


@pytest.mark.functional
@pytest.mark.parametrize("hid, game", [("NA", "Explore"), ("unseeded-character", "Custom Game")])
def test_hitl_create(tmp_path, monkeypatch, hid, game):
    """Create an evaluation with one session scaffold and an empty transcript."""
    evaluation_file = tmp_path / f"{hid}-evaluation.json"
    manual_test_cases_file = tmp_path / f"{hid}-evaluation-cases.json"
    manual_contents = '{"manually_edited": true}\n'
    manual_test_cases_file.write_text(manual_contents, encoding="utf-8")
    monkeypatch.setattr("dcs_simulation_engine.hitl.create._SCENARIOS_DIR", tmp_path)

    command = ["hitl", "create", hid]
    if game != "Explore":
        command.extend(["--game", game])
    started_at = datetime.now(timezone.utc)
    result = _RUNNER.invoke(app, command)

    assert result.exit_code == 0, result.output
    assert evaluation_file.is_file()
    assert "one evaluation session with an empty transcript" in " ".join(result.output.split())
    assert "evaluator_id" in result.output

    data = json.loads(evaluation_file.read_text(encoding="utf-8"))
    assert set(data) == {
        "character_hid", "evaluator_id", "created_at", "updated_at", "description",
        "evaluator_instructions", "results", "sessions",
    }
    assert data["character_hid"] == hid
    assert data["evaluator_id"] == ""
    assert started_at <= datetime.fromisoformat(data["created_at"]) <= datetime.now(timezone.utc)
    assert data["updated_at"] == data["created_at"]
    assert data["description"] == (
        "This human-in-the-loop character evaluation assesses the model’s fidelity and elucidates the bounds "
        "of its modeling capabilities across contexts so it can be used appropriately."
    )
    assert "common LLM failure modes" in data["evaluator_instructions"]
    assert data["results"] is None
    assert data["sessions"] == [
        {
            "game": game,
            "npc_hid": hid,
            "pc_hid": "NA",
            "session_id": None,
            "description": "",
            "transcript": [],
        }
    ]
    assert manual_test_cases_file.read_text(encoding="utf-8") == manual_contents

    # An evaluator's edits must survive an accidental second create command.
    data["sessions"][0]["description"] = "My handwritten setup."
    data["results"] = {"summary": "My handwritten results."}
    evaluation_file.write_text(json.dumps(data), encoding="utf-8")
    result = _RUNNER.invoke(app, command)
    assert result.exit_code == 1
    assert "already exists" in result.output
    assert json.loads(evaluation_file.read_text(encoding="utf-8")) == data
    assert manual_test_cases_file.read_text(encoding="utf-8") == manual_contents


@pytest.mark.functional
@pytest.mark.parametrize("hid", ["../outside", "nested\\character"])
def test_hitl_create_rejects_paths_as_hids(tmp_path, monkeypatch, hid):
    """An HID cannot select a different output path."""
    output_dir = tmp_path / "evaluations"
    monkeypatch.setattr("dcs_simulation_engine.hitl.create._SCENARIOS_DIR", output_dir)

    result = _RUNNER.invoke(app, ["hitl", "create", hid])
    assert result.exit_code == 1
    assert "character HID without path components" in result.output
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# hitl export
# ---------------------------------------------------------------------------


_RATING = {
    "liked": True,
    "comment": "Grounded.",
    "doesnt_make_sense": False,
    "out_of_character": False,
    "other": False,
}


@pytest.mark.functional
@pytest.mark.parametrize(
    "missing, diagnostic",
    [
        ("evaluator_id", "Missing evaluator_id"),
        ("response", "missing a simulator response"),
        ("feedback", "missing evaluator feedback"),
        ("summary", "Missing evaluator summary"),
    ],
)
def test_hitl_export_reports_incomplete_evaluations(tmp_path, monkeypatch, missing, diagnostic):
    """Export work in progress and show which conditions still prevent completion."""
    monkeypatch.setattr("dcs_simulation_engine.hitl.create._SCENARIOS_DIR", tmp_path)
    evaluation = build_scaffold("NA", "Explore")
    evaluation["evaluator_id"] = "MW"
    evaluation["results"] = {"summary": "The simulator stayed in character.", "complete": True}
    session = evaluation["sessions"][0]
    session["transcript"] = [{"type": "message", "source": "npc", "content": "Opening", "evaluator_feedback": _RATING}]
    if missing == "evaluator_id":
        del evaluation["evaluator_id"]
    elif missing == "response":
        session["transcript"].append({"type": "message", "source": "pc", "content": "What happened?"})
    elif missing == "feedback":
        session["transcript"][0]["evaluator_feedback"] = None
    else:
        evaluation["results"]["summary"] = " "

    source = tmp_path / "NA-evaluation.json"
    source.write_text(json.dumps(evaluation), encoding="utf-8")
    out_dir = tmp_path / "hitl_export"
    result = _RUNNER.invoke(app, ["hitl", "export", "NA", "--output-dir", str(out_dir)])

    assert result.exit_code == 0, result.output
    assert "Evaluation status: incomplete" in result.output
    manifest = json.loads((out_dir / "__manifest__.json").read_text(encoding="utf-8"))
    assert manifest["evaluation_status"]["complete"] is False
    assert any(diagnostic in issue for issue in manifest["evaluation_status"]["issues"])
    events = json.loads((out_dir / "session_events.json").read_text(encoding="utf-8"))
    assert events[0]["content"] == "Opening"
    if missing == "response":
        assert events[-1]["content"] == "What happened?"
    if missing == "feedback":
        assert "feedback" not in events[0]
    if missing in {"evaluator_id", "feedback", "summary"}:
        report_path = tmp_path / "incomplete.html"
        result = _RUNNER.invoke(
            app,
            ["report", "results", str(out_dir), "--only", "sim-quality", "--report-path", str(report_path)],
        )
        assert result.exit_code == 0, result.output
        character_report = tmp_path / "per_character_quality" / "NA_quality_report.html"
        for path in (report_path, character_report):
            report = path.read_text(encoding="utf-8")
            first_section = report.split('<section id="section-', 1)[1].split("</section>", 1)[0]
            assert first_section.startswith('evaluation-summary"')
            assert "<h2>Summary</h2>" in first_section
            assert "Evaluation status: <strong>Incomplete</strong>" in first_section
            assert diagnostic in first_section
            assert "Finish the evaluation before publishing." in first_section
            if missing == "summary":
                assert "No written summary provided." in first_section
        if missing == "evaluator_id":
            sessions = json.loads((out_dir / "sessions.json").read_text(encoding="utf-8"))
            assert sessions[0]["player_id"] is None
            players = json.loads((out_dir / "players.json").read_text(encoding="utf-8"))
            assert players == []
            report = character_report.read_text(encoding="utf-8")
            for table_id in ("event-feedback-table", "event-log-table"):
                table = report.split(f'id="{table_id}"', 1)[1].split("</table>", 1)[0]
                head, body = table.split("<tbody>", 1)
                player_column = re.findall(r"<th>(.*?)</th>", head).index("Player")
                cells = re.findall(r"<td>(.*?)</td>", body, re.DOTALL)
                assert cells[player_column] == "ID missing"
    assert json.loads(source.read_text(encoding="utf-8")) == evaluation


@pytest.mark.functional
def test_hitl_export_preserves_branch_transcripts_and_feedback(tmp_path, monkeypatch):
    """Export complete transcripts once each, with stable IDs and links to their forks."""
    monkeypatch.setattr("dcs_simulation_engine.hitl.create._SCENARIOS_DIR", tmp_path)
    evaluation = build_scaffold("NA", "Explore")
    evaluation["evaluator_id"] = "MW"
    evaluation["results"] = {"summary": "The simulator stayed in character.", "complete": False}
    root = evaluation["sessions"][0]
    root.update(
        session_id="root-id",
        description="Establish the opening context.",
        transcript=[
            {"type": "info", "source": "system", "content": "Setup info"},
            {"type": "message", "source": "npc", "content": "Opening", "evaluator_feedback": _RATING},
            {
                "type": "branch",
                "session_id": "first-branch",
                "description": "Probe the validator.",
                "transcript": [
                    {"type": "message", "source": "pc", "content": "Attempt an action", "evaluator_note": "Expect a block."},
                    {
                        "type": "error",
                        "source": "npc",
                        "content": "The action was blocked.",
                        "evaluator_feedback": {**_RATING, "liked": False, "other": True},
                    },
                    {
                        "type": "branch",
                        "session_id": None,
                        "description": "Retry a grounded action.",
                        "transcript": [
                            {"type": "message", "source": "pc", "content": "Choose a safer action"},
                            {"type": "message", "source": "npc", "content": "The action succeeds.", "evaluator_feedback": _RATING},
                        ],
                    },
                ],
            },
            {"type": "message", "source": "pc", "content": "Continue the main path"},
            {"type": "warning", "source": "npc", "content": "Proceed cautiously.", "evaluator_feedback": _RATING},
        ],
    )
    source = tmp_path / "NA-evaluation.json"
    source.write_text(json.dumps(evaluation), encoding="utf-8")
    out_dir = tmp_path / "hitl_export"
    result = _RUNNER.invoke(app, ["hitl", "export", "NA", "--output-dir", str(out_dir)])
    assert result.exit_code == 0, result.output
    assert "3 session(s) exported, including branches" in result.output
    assert "Evaluation status: complete" in result.output
    assert {path.name for path in out_dir.iterdir()} == {
        "__manifest__.json",
        "sessions.json",
        "session_events.json",
        "characters.json",
        "players.json",
        "runs.json",
        "assignments.json",
    }

    manifest = json.loads((out_dir / "__manifest__.json").read_text(encoding="utf-8"))
    sessions = json.loads((out_dir / "sessions.json").read_text(encoding="utf-8"))
    events = json.loads((out_dir / "session_events.json").read_text(encoding="utf-8"))
    assert manifest["evaluation_status"] == {"complete": True, "issues": []}
    assert (manifest["total_sessions"], manifest["total_turns"]) == (3, 3)
    assert [session["session_id"] for session in sessions[:2]] == ["root-id", "first-branch"]
    assert sessions[1]["branch_from_session_id"] == "root-id"
    assert sessions[1]["branch_from_seq"] == 2
    assert sessions[2]["branch_from_session_id"] == "first-branch"
    assert sessions[2]["branch_from_seq"] == 2
    assert sessions[2]["session_id"] not in ("root-id", "first-branch", None)
    assert [session["evaluator_description"] for session in sessions] == [
        "Establish the opening context.",
        "Probe the validator.",
        "Retry a grounded action.",
    ]
    assert manifest["evaluator_id"] == "MW"
    assert all(session["player_id"] == "MW" for session in sessions)
    for session in sessions:
        seqs = [event["seq"] for event in events if event["session_id"] == session["session_id"]]
        assert seqs == list(range(1, session["last_seq"] + 1))

    assert sum(event["content"] == "Opening" for event in events) == 1
    assert events[0]["event_source"] == "system"
    assert events[2]["direction"] == "inbound" and events[2]["event_source"] == "user"
    warning, error = [event for event in events if event["event_type"] in ("warning", "error")]
    assert warning["event_source"] == error["event_source"] == "npc"
    assert error["feedback"]["liked"] is False
    assert error["feedback"]["other"] is True
    assert error["feedback"]["submitted_at"] == evaluation["updated_at"]
    assert any(event.get("evaluator_note") == "Expect a block." for event in events)
    report = _RUNNER.invoke(app, ["report", "results", str(out_dir), "--only", "sim-quality", "--report-path", str(tmp_path / "report.html")])
    assert report.exit_code == 0, report.output
    html = (tmp_path / "per_character_quality" / "NA_quality_report.html").read_text()
    coverage = html.split('<section id="section-coverage"', 1)[1].split("</section>", 1)[0]
    assert coverage.index("Scene opening") < coverage.index("Branch 1.1") < coverage.index("Attempt an action")
    assert coverage.index("Branch 1.1.1") < coverage.index("Choose a safer action") < coverage.index("Continue the main path")
    assert coverage.count(">Liked</span>") == 3
    assert coverage.count(">Disliked</span>") == 1
    assert "Expect a block." in coverage and "The action was blocked." in coverage
    assert json.loads(source.read_text(encoding="utf-8")) == evaluation


# ---------------------------------------------------------------------------
# publish characters
# ---------------------------------------------------------------------------

_SIM_QUALITY_HTML = """\
<html><body>
<table id="sim-quality-per-npc-table">
  <thead><tr><th>HID</th><th>Turns</th><th>ICF</th><th>NCo</th></tr></thead>
  <tbody>
    <tr><td>NA</td><td>25</td><td>96.0%</td><td>4.0%</td></tr>
  </tbody>
</table>
</body></html>
"""


@pytest.mark.functional
def test_publish_characters(tmp_path, monkeypatch):
    """Dcs publish characters produces all three expected changes.

    Expected changes:
      [1] character_evaluations.json — one new evaluation entry appended for NA
      [2] prod/characters.json — unchanged (NA already present in prod)
      [3] release_manifest.json — recomputed via write_manifest
    """
    report_file = tmp_path / "sim_quality_report.html"
    report_file.write_text(_SIM_QUALITY_HTML, encoding="utf-8")

    saved_calls: list[tuple[Path, list | dict]] = []
    manifest_calls: list[tuple[Path, list, str]] = []

    def _mock_save_json_file(path: Path, data) -> None:
        saved_calls.append((path, data))

    def _mock_write_manifest(path: Path, approved, policy_version) -> None:
        manifest_calls.append((path, approved, policy_version))

    monkeypatch.setattr("dcs_simulation_engine.reporting.auto.publish.save_json_file", _mock_save_json_file)
    monkeypatch.setattr(
        "dcs_simulation_engine.utils.release_policy.write_manifest",
        _mock_write_manifest,
    )
    # compute_approved_characters has a stale import ('analysis' was renamed to 'dcs_simulation_engine')
    monkeypatch.setattr(
        "dcs_simulation_engine.utils.release_policy.compute_approved_characters",
        lambda policy, evals, chars_by_hid: [],
    )

    result = _RUNNER.invoke(
        app,
        [
            "publish",
            "characters",
            str(report_file),
            "--hids",
            "NA",
            "--evaluator-id",
            "test-evaluator",
            "--evaluator-expertise",
            "researcher",
        ],
        input="y\n",
    )

    assert result.exit_code == 0, result.output

    # --- Change [1]: evaluation entry appended to character_evaluations.json ---
    evals_saves = [(p, d) for p, d in saved_calls if "character_evaluations" in p.name]
    assert len(evals_saves) == 1, "Expected exactly one save to character_evaluations.json"
    evals_data = evals_saves[0][1]
    assert isinstance(evals_data, list)
    new_entry = next((e for e in evals_data if e.get("character_hid") == "NA"), None)
    assert new_entry is not None, "No evaluation entry for NA in saved evaluations"
    assert new_entry["evaluator_id"] == "test-evaluator"
    assert new_entry["expertise"] == "researcher"
    assert new_entry["scores"]["icf"] == pytest.approx(0.96, abs=1e-4)
    assert new_entry["scores"]["dms"] == pytest.approx(0.04, abs=1e-4)
    assert new_entry["scores"]["rf"] == 0.0
    assert "fingerprint" in new_entry

    # --- Change [2]: prod/characters.json — NA already present, so no save ---
    prod_chars_saves = [(p, d) for p, d in saved_calls if p.name == "characters.json"]
    assert len(prod_chars_saves) == 0, "prod/characters.json should not be written when character is already present"

    # --- Change [3]: release_manifest.json recomputed via write_manifest ---
    assert len(manifest_calls) == 1, "Expected write_manifest to be called exactly once"
    manifest_path, approved, policy_version = manifest_calls[0]
    assert "release_manifest" in manifest_path.name
