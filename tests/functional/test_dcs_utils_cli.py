"""Functional tests for the dcs-utils CLI.

Prerequisites:
    uv sync --extra dev --extra analysis

Runs every dcs-utils command and asserts:
  - exit code 0
  - all HTML reports are parseable (contain <html>, no Python Traceback)
"""

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from dcs_utils.cli.__main__ import app
from dcs_utils.hitl import Attempt, Scenario, ScenarioFile, ScenarioGroup
from dcs_utils.hitl.generate import save_scenario_file
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
    "transcripts",
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
    """dcs-utils report coverage --db dev writes a valid HTML report."""
    monkeypatch.chdir(tmp_path)

    result = _RUNNER.invoke(app, ["report", "coverage", "--db", "dev"])

    assert result.exit_code == 0, result.output
    out_html = tmp_path / "results" / "character_coverage_dev.html"
    assert out_html.exists(), f"Expected report at {out_html}"
    _assert_valid_html(out_html)


@pytest.mark.functional
def test_report_coverage_prod(tmp_path, monkeypatch):
    """dcs-utils report coverage --db prod writes a valid HTML report."""
    monkeypatch.chdir(tmp_path)

    result = _RUNNER.invoke(app, ["report", "coverage", "--db", "prod"])

    assert result.exit_code == 0, result.output
    out_html = tmp_path / "results" / "character_coverage_prod.html"
    assert out_html.exists(), f"Expected report at {out_html}"
    _assert_valid_html(out_html)


# ---------------------------------------------------------------------------
# report results
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_report_results_default_sections(tmp_path):
    """dcs-utils report results with default sections produces a valid HTML report."""
    out = tmp_path / "report.html"

    result = _RUNNER.invoke(
        app,
        ["report", "results", str(_EXAMPLE_RESULTS), "--report-path", str(out)],
    )

    assert result.exit_code == 0, result.output
    assert out.exists(), f"Expected report at {out}"
    _assert_valid_html(out)


@pytest.mark.functional
def test_report_results_sim_quality(tmp_path):
    """dcs-utils report results --only sim-quality produces a valid HTML report and per-character sub-reports."""
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
    """dcs-utils report results --only <slug> runs without error for every section."""
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
def test_hitl_create(tmp_path, monkeypatch):
    """dcs-utils hitl create NA --db dev creates a valid scenarios scaffold file."""
    scenarios_file = tmp_path / "NA-scenarios.json"

    monkeypatch.setattr(
        "dcs_utils.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-scenarios.json",
    )

    result = _RUNNER.invoke(app, ["hitl", "create", "NA", "--db", "dev"])

    assert result.exit_code == 0, result.output
    assert scenarios_file.exists(), f"Expected scenarios file at {scenarios_file}"

    data = json.loads(scenarios_file.read_text())
    assert data["npc_hid"] == "NA"
    assert len(data["scenario_groups"]) >= 12
    # All attempts start empty (no engine responses yet)
    for group in data["scenario_groups"]:
        for scenario in group["scenarios"]:
            for attempt in scenario["attempts"]:
                assert attempt["simulator_response"] is None


# ---------------------------------------------------------------------------
# hitl update
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_hitl_update_generates_opening_scene_before_attempts(tmp_path, monkeypatch):
    """dcs-utils hitl update seeds opening history, then fills attempt responses."""

    class _FakeRun:
        def __init__(self, responses_by_message: dict[str, str], step_calls: list[str]) -> None:
            self._responses_by_message = responses_by_message
            self._step_calls = step_calls
            self._simulator_output = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def step(self, user_input: str = ""):
            self._step_calls.append(user_input)
            if user_input == "":
                self._simulator_output = "You enter a new space. In this space, a quiet machine waits."
            else:
                self._simulator_output = self._responses_by_message[user_input]
            return self

        @property
        def simulator_output(self) -> str:
            return self._simulator_output

    class _FakeAPIClient:
        def __init__(self, *, url: str, api_key: str) -> None:
            _ = (url, api_key)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def start_game(self, body):
            assert body.game == "Explore"
            assert body.pc_choice == "NA"
            assert body.npc_choice == "NA"
            return _FakeRun(_responses_by_message, _step_calls)

    scenarios_file = tmp_path / "NA-scenarios.json"
    scenario_file = ScenarioFile(
        npc_hid="NA",
        generated_at="2026-04-22T00:00:00+00:00",
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
                        conversation_history=[],
                        attempts=[
                            Attempt(player_message="I look around"),
                            Attempt(player_message="I touch the wall"),
                        ],
                    )
                ],
            )
        ],
    )
    save_scenario_file(scenarios_file, scenario_file)

    _responses_by_message = {
        "I look around": "The machine gives a low mechanical hum.",
        "I touch the wall": "A cold vibration travels through the wall.",
    }
    _step_calls: list[str] = []

    monkeypatch.setattr(
        "dcs_utils.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-scenarios.json",
    )
    monkeypatch.setattr("dcs_utils.hitl.responses.APIClient", _FakeAPIClient)

    help_result = _RUNNER.invoke(app, ["hitl", "update", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "--include-empty" not in help_result.output

    result = _RUNNER.invoke(app, ["hitl", "update", "NA", "--skip-feedback"])

    assert result.exit_code == 0, result.output
    assert _step_calls == ["", "I look around", "I touch the wall"]

    data = json.loads(scenarios_file.read_text(encoding="utf-8"))
    scenario = data["scenario_groups"][0]["scenarios"][0]

    assert scenario["conversation_history"] == [
        {
            "role": "assistant",
            "content": "You enter a new space. In this space, a quiet machine waits.",
        },
        {"role": "user", "content": "I look around"},
        {
            "role": "assistant",
            "content": "The machine gives a low mechanical hum.",
        },
        {"role": "user", "content": "I touch the wall"},
        {
            "role": "assistant",
            "content": "A cold vibration travels through the wall.",
        },
    ]
    assert scenario["attempts"][0]["simulator_response"] == "The machine gives a low mechanical hum."
    assert scenario["attempts"][1]["simulator_response"] == "A cold vibration travels through the wall."


# ---------------------------------------------------------------------------
# hitl export
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_hitl_export(tmp_path, monkeypatch):
    """dcs-utils hitl export NA writes a standard results directory."""
    from dcs_utils.hitl.generate import build_scaffold, load_character, save_scaffold

    # Build a scaffold directly so we have a scenarios file to export from.
    character = load_character("NA", "dev")
    scaffold = build_scaffold(character, "Explore")
    scenarios_file = tmp_path / "NA-scenarios.json"
    save_scaffold(scaffold, scenarios_file)

    monkeypatch.setattr(
        "dcs_utils.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-scenarios.json",
    )

    out_dir = tmp_path / "hitl_export"
    result = _RUNNER.invoke(
        app,
        ["hitl", "export", "NA", "--output-dir", str(out_dir)],
    )

    assert result.exit_code == 0, result.output
    assert out_dir.exists(), f"Expected output directory at {out_dir}"
    assert (out_dir / "__manifest__.json").exists()
    assert (out_dir / "sessions.json").exists()
    assert (out_dir / "session_events.json").exists()


# ---------------------------------------------------------------------------
# admin publish characters
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
def test_admin_publish_characters(tmp_path, monkeypatch):
    """dcs-utils admin publish characters produces all three expected changes.

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

    monkeypatch.setattr("dcs_utils.auto.publish.save_json_file", _mock_save_json_file)
    monkeypatch.setattr(
        "dcs_simulation_engine.utils.release_policy.write_manifest",
        _mock_write_manifest,
    )
    # compute_approved_characters has a stale import ('analysis' was renamed to 'dcs_utils')
    monkeypatch.setattr(
        "dcs_simulation_engine.utils.release_policy.compute_approved_characters",
        lambda policy, evals, chars_by_hid: [],
    )

    result = _RUNNER.invoke(
        app,
        [
            "admin",
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
    assert len(prod_chars_saves) == 0, (
        "prod/characters.json should not be written when character is already present"
    )

    # --- Change [3]: release_manifest.json recomputed via write_manifest ---
    assert len(manifest_calls) == 1, "Expected write_manifest to be called exactly once"
    manifest_path, approved, policy_version = manifest_calls[0]
    assert "release_manifest" in manifest_path.name
