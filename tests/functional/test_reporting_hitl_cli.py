"""Functional tests for the dcs CLI.

Runs every dcs command and asserts:
  - exit code 0
  - all HTML reports are parseable (contain <html>, no Python Traceback)
"""

import json
from html.parser import HTMLParser
from pathlib import Path

import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.hitl import Attempt, EvaluatorFeedback, Scenario, ScenarioFile, ScenarioGroup
from dcs_simulation_engine.hitl.generate import save_scenario_file
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
    """Dcs report coverage --db dev writes a valid HTML report."""
    monkeypatch.chdir(tmp_path)

    result = _RUNNER.invoke(app, ["report", "coverage", "--db", "dev"])

    assert result.exit_code == 0, result.output
    out_html = tmp_path / "results" / "character_coverage_dev.html"
    assert out_html.exists(), f"Expected report at {out_html}"
    _assert_valid_html(out_html)


@pytest.mark.functional
def test_report_coverage_prod(tmp_path, monkeypatch):
    """Dcs report coverage --db prod writes a valid HTML report."""
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
def test_hitl_create(tmp_path, monkeypatch):
    """Dcs admin hitl create NA --db dev creates a valid test cases scaffold file."""
    test_cases_file = tmp_path / "NA-test-cases.json"

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )

    result = _RUNNER.invoke(app, ["admin", "hitl", "create", "NA", "--db", "dev"])

    assert result.exit_code == 0, result.output
    assert test_cases_file.exists(), f"Expected test cases file at {test_cases_file}"
    assert "Scenario File Summary" in result.output
    assert "scenario group(s)" in result.output
    assert "attempt(s) without simulator responses" in result.output
    assert "attempt(s) without player feedback" in result.output
    assert "Next steps:" not in result.output

    data = json.loads(test_cases_file.read_text())
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
    """Dcs admin hitl update stores shared opening history, then branches per attempt."""

    class _FakeRun:
        def __init__(
            self,
            responses_by_message: dict[str, str],
            step_calls: list[tuple[str, str]],
            branch_name: str,
            session_id: str,
        ) -> None:
            self._responses_by_message = responses_by_message
            self._step_calls = step_calls
            self._branch_name = branch_name
            self.session_id = session_id
            self._simulator_output = ""
            self._events = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def step(self, user_input: str = ""):
            self._step_calls.append((self._branch_name, user_input))
            if user_input == "":
                self._simulator_output = "You enter a new space. In this space, a quiet machine waits."
            else:
                self._simulator_output = self._responses_by_message[user_input]
            self._events.append(
                type(
                    "Event",
                    (),
                    {"event_type": "ai", "content": self._simulator_output},
                )()
            )
            return self

        @property
        def simulator_output(self) -> str:
            return self._simulator_output

        @property
        def history(self):
            return list(self._events)

    class _FakeAPIClient:
        def __init__(self, *, url: str, api_key: str) -> None:
            _ = (url, api_key)
            self._branch_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def health(self):
            return {"status": "ok"}

        def start_game(self, body):
            assert body.game == "Explore"
            assert body.pc_choice == "NA"
            assert body.npc_choice == "NA"
            assert body.source == "hitl"
            return _FakeRun(_responses_by_message, _step_calls, "root", "root-session")

        def branch_session(self, session_id, *, api_key=None):
            assert session_id == "root-session"
            assert api_key == "test-key"
            self._branch_count += 1
            return _FakeRun(
                _responses_by_message,
                _step_calls,
                f"branch-{self._branch_count}",
                f"branch-session-{self._branch_count}",
            )

    test_cases_file = tmp_path / "NA-test-cases.json"
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
    save_scenario_file(test_cases_file, scenario_file)

    _responses_by_message = {
        "I look around": "The machine gives a low mechanical hum.",
        "I touch the wall": "A cold vibration travels through the wall.",
    }
    _step_calls: list[str] = []

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )
    monkeypatch.setattr("dcs_simulation_engine.api.client.APIClient", _FakeAPIClient)
    monkeypatch.setattr("dcs_simulation_engine.hitl.responses.APIClient", _FakeAPIClient)

    help_result = _RUNNER.invoke(app, ["admin", "hitl", "update", "--help"])
    assert help_result.exit_code == 0, help_result.output
    assert "--include-empty" not in help_result.output

    result = _RUNNER.invoke(app, ["admin", "hitl", "update", "NA", "--skip-player-feedback", "--api-key", "test-key"])

    assert result.exit_code == 0, result.output
    assert _step_calls == [
        ("root", ""),
        ("branch-1", "I look around"),
        ("branch-2", "I touch the wall"),
    ]

    data = json.loads(test_cases_file.read_text(encoding="utf-8"))
    scenario = data["scenario_groups"][0]["scenarios"][0]

    assert scenario["conversation_history"] == [
        {
            "role": "assistant",
            "content": "You enter a new space. In this space, a quiet machine waits.",
        },
    ]
    assert scenario["parent_session_id"] == "root-session"
    assert "Scenario File Summary" in result.output
    assert "0/2 attempt(s) without simulator responses" in result.output
    assert "2/2 attempt(s) without player feedback" in result.output
    assert scenario["attempts"][0]["simulator_response"] == "The machine gives a low mechanical hum."
    assert scenario["attempts"][1]["simulator_response"] == "A cold vibration travels through the wall."


@pytest.mark.functional
def test_hitl_update_only_history_appends_missing_simulator_reply(tmp_path, monkeypatch):
    """Dcs admin hitl update --only-history repairs a trailing player turn without branching attempts."""

    class _FakeAPIClient:
        def __init__(self, *, url: str, api_key: str) -> None:
            _ = (url, api_key)
            self.branch_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def health(self):
            return {"status": "ok"}

        def _ws_status(self, *, session_id, api_key=None, include_opening=False, expect_replay=False):
            _ = (session_id, api_key, include_opening, expect_replay)
            session_meta = type("Meta", (), {"session_id": "existing-parent"})()
            status_frame = type(
                "Status",
                (),
                {"session_id": "existing-parent", "turns": 1, "exited": False},
            )()
            return session_meta, status_frame

        def _ws_open_and_advance(
            self,
            *,
            session_id,
            api_key=None,
            text=None,
            include_opening=False,
            expect_replay=False,
        ):
            _ = (session_id, api_key, include_opening, expect_replay)
            events = []
            if text == "I call out":
                events.append(type("Event", (), {"event_type": "ai", "content": "A distant voice answers back."})())
            turn_end = type("TurnEnd", (), {"session_id": "existing-parent", "turns": 2, "exited": False})()
            session_meta = type("Meta", (), {"session_id": "existing-parent"})()
            return session_meta, events, turn_end

        def branch_session(self, session_id, *, api_key=None):
            _ = (session_id, api_key)
            self.branch_calls += 1
            raise AssertionError("branch_session should not be called for --only-history")

    test_cases_file = tmp_path / "NA-test-cases.json"
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
                        parent_session_id="existing-parent",
                        conversation_history=[
                            {"role": "assistant", "content": "A machine waits in the room."},
                            {"role": "user", "content": "I call out"},
                        ],
                        attempts=[Attempt(player_message="I look around")],
                    )
                ],
            )
        ],
    )
    save_scenario_file(test_cases_file, scenario_file)

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )
    monkeypatch.setattr("dcs_simulation_engine.api.client.APIClient", _FakeAPIClient)
    monkeypatch.setattr("dcs_simulation_engine.hitl.responses.APIClient", _FakeAPIClient)

    result = _RUNNER.invoke(app, ["admin", "hitl", "update", "NA", "--only-history"])

    assert result.exit_code == 0, result.output
    assert "Scenario File Summary" in result.output
    assert "1/1 attempt(s) without simulator responses" in result.output
    assert "0/1 conversation history/histories missing a simulator reply" in result.output

    data = json.loads(test_cases_file.read_text(encoding="utf-8"))
    scenario = data["scenario_groups"][0]["scenarios"][0]
    assert scenario["conversation_history"][-1] == {
        "role": "assistant",
        "content": "A distant voice answers back.",
    }
    assert scenario["attempts"][0]["simulator_response"] is None


@pytest.mark.functional
def test_hitl_update_regenerates_missing_parent_and_writes_new_field_name(tmp_path, monkeypatch):
    """Dcs admin hitl update can rebuild a missing parent session from saved history."""

    class _FakeRun:
        def __init__(
            self,
            responses_by_message: dict[str, str],
            step_calls: list[tuple[str, str]],
            branch_name: str,
            session_id: str,
        ) -> None:
            self._responses_by_message = responses_by_message
            self._step_calls = step_calls
            self._branch_name = branch_name
            self.session_id = session_id
            self._events = []

        def step(self, user_input: str = ""):
            self._step_calls.append((self._branch_name, user_input))
            content = self._responses_by_message[user_input]
            self._events.append(type("Event", (), {"event_type": "ai", "content": content})())
            return self

        @property
        def history(self):
            return list(self._events)

    class _FakeAPIClient:
        def __init__(self, *, url: str, api_key: str) -> None:
            _ = (url, api_key)
            self._branch_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def health(self):
            return {"status": "ok"}

        def _ws_status(self, *, session_id, api_key=None, include_opening=False, expect_replay=False):
            _ = (api_key, include_opening, expect_replay)
            if session_id == "missing-parent":
                raise RuntimeError("Session not found")
            session_meta = type("Meta", (), {"session_id": session_id})()
            status_frame = type("Status", (), {"session_id": session_id, "turns": 1, "exited": False})()
            return session_meta, status_frame

        def start_game(self, body):
            assert body.source == "hitl"
            return _FakeRun(_responses_by_message, _step_calls, "root", "rebuilt-parent")

        def branch_session(self, session_id, *, api_key=None):
            assert session_id == "rebuilt-parent"
            assert api_key == "test-key"
            self._branch_count += 1
            return _FakeRun(
                _responses_by_message,
                _step_calls,
                f"branch-{self._branch_count}",
                f"branch-session-{self._branch_count}",
            )

    test_cases_file = tmp_path / "NA-test-cases.json"
    test_cases_file.write_text(
        json.dumps(
            {
                "npc_hid": "NA",
                "generated_at": "2026-04-23T00:00:00+00:00",
                "scenario_groups": [
                    {
                        "group_id": "test-group",
                        "label": "Test Group",
                        "expected_failure_mode": "Test failure mode",
                        "pressure_category": "test-pressure",
                        "scenarios": [
                            {
                                "id": "NA-test-001",
                                "description": "Test scenario",
                                "game": "Explore",
                                "pc_hid": "NA",
                                "context_session_id": "missing-parent",
                                "conversation_history": [{"role": "assistant", "content": "A quiet machine waits."}],
                                "attempts": [
                                    {
                                        "player_message": "I inspect the machine",
                                        "simulator_response": None,
                                        "evaluator_feedback": None,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    _responses_by_message = {
        "": "A quiet machine waits.",
        "I inspect the machine": "The machine hums and turns toward you.",
    }
    _step_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )
    monkeypatch.setattr("dcs_simulation_engine.api.client.APIClient", _FakeAPIClient)
    monkeypatch.setattr("dcs_simulation_engine.hitl.responses.APIClient", _FakeAPIClient)

    result = _RUNNER.invoke(
        app,
        [
            "admin",
            "hitl",
            "update",
            "NA",
            "--skip-player-feedback",
            "--regenerate-parent-session",
            "--api-key",
            "test-key",
        ],
    )

    assert result.exit_code == 0, result.output
    assert _step_calls == [
        ("root", ""),
        ("branch-1", "I inspect the machine"),
    ]

    data = json.loads(test_cases_file.read_text(encoding="utf-8"))
    scenario = data["scenario_groups"][0]["scenarios"][0]
    assert "context_session_id" not in scenario
    assert scenario["parent_session_id"] == "rebuilt-parent"
    assert scenario["attempts"][0]["simulator_response"] == "The machine hums and turns toward you."


@pytest.mark.functional
def test_hitl_update_records_validation_error_as_simulator_response(tmp_path, monkeypatch):
    """Non-AI branch events are stored as simulator responses with metadata."""

    class _FakeRun:
        def __init__(self, step_calls: list[tuple[str, str]], branch_name: str, session_id: str) -> None:
            self._step_calls = step_calls
            self._branch_name = branch_name
            self.session_id = session_id
            self._events = []

        def step(self, user_input: str = ""):
            self._step_calls.append((self._branch_name, user_input))
            if user_input == "":
                payloads = [{"event_type": "ai", "content": "A quiet room waits around you."}]
            elif user_input == "Try blocked action":
                payloads = [
                    {"event_type": "error", "content": "Validation blocked that action."},
                    {"event_type": "info", "content": "Try a grounded physical action instead."},
                ]
            else:
                payloads = [{"event_type": "ai", "content": "The room remains still."}]
            for payload in payloads:
                self._events.append(type("Event", (), payload)())
            return self

        @property
        def history(self):
            return list(self._events)

        @property
        def turns(self):
            return 1

        @property
        def is_complete(self):
            return False

    class _FakeAPIClient:
        def __init__(self, *, url: str, api_key: str) -> None:
            _ = (url, api_key)
            self._branch_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def health(self):
            return {"status": "ok"}

        def start_game(self, body):
            _ = body
            return _FakeRun(_step_calls, "root", "root-session")

        def branch_session(self, session_id, *, api_key=None):
            assert session_id == "root-session"
            _ = api_key
            self._branch_count += 1
            return _FakeRun(_step_calls, f"branch-{self._branch_count}", f"branch-session-{self._branch_count}")

    test_cases_file = tmp_path / "NA-test-cases.json"
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
                        conversation_history=[],
                        attempts=[Attempt(player_message="Try blocked action")],
                    )
                ],
            )
        ],
    )
    save_scenario_file(test_cases_file, scenario_file)

    _step_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )
    monkeypatch.setattr("dcs_simulation_engine.api.client.APIClient", _FakeAPIClient)
    monkeypatch.setattr("dcs_simulation_engine.hitl.responses.APIClient", _FakeAPIClient)

    result = _RUNNER.invoke(app, ["admin", "hitl", "update", "NA", "--skip-player-feedback"])

    assert result.exit_code == 0, result.output
    assert "Scenario File Summary" in result.output
    assert "0/1 attempt(s) without simulator responses" in result.output

    data = json.loads(test_cases_file.read_text(encoding="utf-8"))
    attempt = data["scenario_groups"][0]["scenarios"][0]["attempts"][0]
    assert attempt["simulator_response"] == "Validation blocked that action."
    assert attempt["simulator_response_type"] == "error"
    assert attempt["simulator_extra_events"] == [{"event_type": "info", "content": "Try a grounded physical action instead."}]


@pytest.mark.functional
def test_hitl_status_summary_respects_selected_subset(tmp_path):
    """Shared HITL summary counts only the selected scenarios when filtered."""
    from dcs_simulation_engine.hitl.responses import compute_status_summary

    test_cases_file = tmp_path / "NA-test-cases.json"
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
                        description="Selected scenario",
                        game="Explore",
                        pc_hid="NA",
                        conversation_history=[],
                        attempts=[Attempt(player_message="One"), Attempt(player_message="Two")],
                    ),
                    Scenario(
                        id="NA-test-002",
                        description="Excluded scenario",
                        game="Explore",
                        pc_hid="NA",
                        conversation_history=[{"role": "assistant", "content": "Ready."}],
                        attempts=[
                            Attempt(
                                player_message="Done",
                                simulator_response="Complete",
                                simulator_response_type="ai",
                            )
                        ],
                    ),
                ],
            )
        ],
    )
    save_scenario_file(test_cases_file, scenario_file)

    summary = compute_status_summary(test_cases_file, only=["NA-test-001"])

    assert summary["scenario_groups_total"] == 1
    assert summary["scenarios_total"] == 1
    assert summary["attempts_total"] == 2
    assert summary["attempts_without_simulator_responses"] == 2
    assert summary["attempts_without_player_feedback"] == 0
    assert summary["empty_conversation_histories"] == 1
    assert summary["conversation_histories_missing_simulator_reply"] == 0


@pytest.mark.functional
def test_hitl_update_reports_when_server_is_not_running(tmp_path, monkeypatch):
    """Dcs admin hitl update should fail fast with a clear server-running message."""

    class _UnavailableAPIClient:
        def __init__(self, *, url: str, api_key: str) -> None:
            _ = (url, api_key)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def health(self):
            raise RuntimeError("connection refused")

    test_cases_file = tmp_path / "NA-test-cases.json"
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
                        conversation_history=[],
                        attempts=[Attempt(player_message="I look around")],
                    )
                ],
            )
        ],
    )
    save_scenario_file(test_cases_file, scenario_file)

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )
    monkeypatch.setattr("dcs_simulation_engine.api.client.APIClient", _UnavailableAPIClient)

    called = {"generate": False}

    async def _fake_generate_responses(**kwargs):
        called["generate"] = True
        _ = kwargs

    monkeypatch.setattr("dcs_simulation_engine.hitl.responses.generate_responses", _fake_generate_responses)

    result = _RUNNER.invoke(app, ["admin", "hitl", "update", "NA", "--skip-player-feedback"])

    assert result.exit_code == 1
    assert "Could not connect to the DCS server" in result.output
    assert "needs to be running" in result.output
    assert called["generate"] is False


# ---------------------------------------------------------------------------
# hitl export
# ---------------------------------------------------------------------------


@pytest.mark.functional
def test_hitl_export(tmp_path, monkeypatch):
    """Dcs admin hitl export NA writes a standard results directory."""
    from dcs_simulation_engine.hitl.generate import build_scaffold, load_character, save_scaffold

    # Build a scaffold directly so we have a test cases file to export from.
    character = load_character("NA", "dev")
    scaffold = build_scaffold(character, "Explore")
    test_cases_file = tmp_path / "NA-test-cases.json"
    save_scaffold(scaffold, test_cases_file)

    monkeypatch.setattr(
        "dcs_simulation_engine.hitl.generate.scenarios_path_for",
        lambda hid: tmp_path / f"{hid}-test-cases.json",
    )

    out_dir = tmp_path / "hitl_export"
    result = _RUNNER.invoke(
        app,
        ["admin", "hitl", "export", "NA", "--output-dir", str(out_dir)],
    )

    assert result.exit_code == 0, result.output
    assert "Scenario File Summary" in result.output
    assert "Export is proceeding with the current scenario file state." in result.output
    assert "Exported results" in result.output
    assert "0/" in result.output
    assert out_dir.exists(), f"Expected output directory at {out_dir}"
    assert (out_dir / "__manifest__.json").exists()
    assert (out_dir / "sessions.json").exists()
    assert (out_dir / "session_events.json").exists()

    manifest = json.loads((out_dir / "__manifest__.json").read_text(encoding="utf-8"))
    sessions = json.loads((out_dir / "sessions.json").read_text(encoding="utf-8"))
    assert manifest["total_scenarios"] == 0
    assert manifest["total_attempts"] == 0
    assert manifest["source_total_scenarios"] > 0
    assert manifest["source_total_attempts"] > 0
    assert manifest["skipped_scenarios"] == manifest["source_total_scenarios"]
    assert manifest["skipped_attempts"] == manifest["source_total_attempts"]
    assert sessions == []


@pytest.mark.functional
def test_hitl_export_preserves_non_ai_attempt_response_types(tmp_path):
    """Validation/system attempt responses export with their original event types."""
    from dcs_simulation_engine.hitl.export import export_results

    test_cases_file = tmp_path / "NA-test-cases.json"
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
                        attempts=[
                            Attempt(
                                player_message="Try blocked action",
                                simulator_response="Validation blocked that action.",
                                simulator_response_type="error",
                                simulator_extra_events=[{"event_type": "info", "content": "Try a grounded physical action instead."}],
                                evaluator_feedback=EvaluatorFeedback(
                                    liked=False,
                                    comment="Validator caught it correctly.",
                                    doesnt_make_sense=False,
                                    out_of_character=False,
                                    other=True,
                                    submitted_at="2026-04-23T00:05:00+00:00",
                                ),
                            )
                        ],
                    )
                ],
            )
        ],
    )
    save_scenario_file(test_cases_file, scenario_file)

    out_dir = export_results(test_cases_file, output_dir=tmp_path / "hitl_export")
    session_events = json.loads((out_dir / "session_events.json").read_text(encoding="utf-8"))

    outbound = [event for event in session_events if event["direction"] == "outbound"]
    assert len(outbound) == 2
    assert outbound[0]["event_type"] == "error"
    assert outbound[0]["event_source"] == "system"
    assert outbound[0]["content"] == "Validation blocked that action."
    assert outbound[0]["feedback"]["liked"] is False
    assert outbound[1]["event_type"] == "info"
    assert outbound[1]["event_source"] == "system"
    assert outbound[1]["content"] == "Try a grounded physical action instead."


@pytest.mark.functional
def test_hitl_export_skips_incomplete_attempts_and_zero_complete_scenarios(tmp_path):
    """Only attempts with both response and feedback are exported."""
    from dcs_simulation_engine.hitl.export import export_results

    test_cases_file = tmp_path / "NA-test-cases.json"
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
                        id="NA-mixed-001",
                        description="Mixed completion scenario",
                        game="Explore",
                        pc_hid="NA",
                        attempts=[
                            Attempt(player_message="Missing response"),
                            Attempt(
                                player_message="Missing feedback",
                                simulator_response="She looks up briefly.",
                                simulator_response_type="ai",
                            ),
                            Attempt(
                                player_message="Completed attempt",
                                simulator_response="She nods and says hello.",
                                simulator_response_type="ai",
                                evaluator_feedback=EvaluatorFeedback(
                                    liked=True,
                                    comment="Works.",
                                    submitted_at="2026-04-23T00:10:00+00:00",
                                ),
                            ),
                        ],
                    ),
                    Scenario(
                        id="NA-incomplete-001",
                        description="No completed attempts",
                        game="Explore",
                        pc_hid="NA",
                        attempts=[
                            Attempt(player_message="No response"),
                            Attempt(
                                player_message="Response only",
                                simulator_response="Blocked.",
                                simulator_response_type="error",
                            ),
                        ],
                    ),
                ],
            )
        ],
    )
    save_scenario_file(test_cases_file, scenario_file)

    out_dir = export_results(test_cases_file, output_dir=tmp_path / "hitl_export")
    manifest = json.loads((out_dir / "__manifest__.json").read_text(encoding="utf-8"))
    sessions = json.loads((out_dir / "sessions.json").read_text(encoding="utf-8"))
    session_events = json.loads((out_dir / "session_events.json").read_text(encoding="utf-8"))

    assert manifest["total_scenarios"] == 1
    assert manifest["total_attempts"] == 1
    assert manifest["source_total_scenarios"] == 2
    assert manifest["source_total_attempts"] == 5
    assert manifest["skipped_scenarios"] == 1
    assert manifest["skipped_attempts"] == 4

    assert len(sessions) == 1
    assert sessions[0]["name"] == "hitl-NA-NA-mixed-001"
    assert sessions[0]["turns_completed"] == 1
    assert sessions[0]["last_seq"] == 2

    assert len(session_events) == 2
    assert session_events[0]["direction"] == "inbound"
    assert session_events[0]["content"] == "Completed attempt"
    assert session_events[1]["direction"] == "outbound"
    assert session_events[1]["content"] == "She nods and says hello."
    assert session_events[1]["feedback"]["liked"] is True


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
    """Dcs admin publish characters produces all three expected changes.

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
    assert len(prod_chars_saves) == 0, "prod/characters.json should not be written when character is already present"

    # --- Change [3]: release_manifest.json recomputed via write_manifest ---
    assert len(manifest_calls) == 1, "Expected write_manifest to be called exactly once"
    manifest_path, approved, policy_version = manifest_calls[0]
    assert "release_manifest" in manifest_path.name
