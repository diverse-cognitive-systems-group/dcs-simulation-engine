"""Functional tests for the session transcript evaluation workflow."""

import json
from copy import deepcopy
from threading import Lock
from types import SimpleNamespace

import httpx
import pytest
from dcs_simulation_engine.cli.app import app
from dcs_simulation_engine.errors import APIRequestError
from dcs_simulation_engine.hitl import responses
from dcs_simulation_engine.hitl.create import build_scaffold
from dcs_simulation_engine.hitl.evaluation import load_evaluation_file
from typer.testing import CliRunner

pytestmark = pytest.mark.functional
RUNNER = CliRunner()
RATED = {"liked": True, "comment": "", "doesnt_make_sense": False, "out_of_character": False, "other": False}


def _pc(content, **extra):
    return {"type": "message", "source": "pc", "content": content, **extra}


def _branch(*entries, description="Test a branch"):
    return {"type": "branch", "session_id": None, "description": description, "transcript": list(entries)}


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _update(*options, input=""):
    return RUNNER.invoke(app, ["hitl", "update", "NA", "--api-key", "test-key", *options], input=input)


@pytest.fixture
def evaluation(tmp_path, monkeypatch):
    """Write a new evaluation scaffold to an isolated output directory."""
    monkeypatch.setattr("dcs_simulation_engine.hitl.create._SCENARIOS_DIR", tmp_path)
    monkeypatch.setenv("DCS_API_KEY", "")
    data = build_scaffold("NA", "Explore")
    path = tmp_path / "NA-evaluation.json"
    _write(path, data)
    return path, data


@pytest.fixture
def backend(monkeypatch):
    """Exercise the real CLI against the same branch and reconstruction shapes as the API."""
    sessions = {}
    calls = []
    outputs = {}
    lock = Lock()

    class Run:
        def __init__(self, session_id):
            self.session_id = session_id
            self.history = []

        def step(self, text=""):
            with lock:
                calls.append((self.session_id, text))
                session = sessions[self.session_id]
                snapshot = session.setdefault(
                    "runtime_state",
                    {"schema_version": 1, "turn_count": 0, "game_state": {"filtered_transcript_buffer": []}},
                )
                turn_index = snapshot["turn_count"] + 1
                command = text == "/new-scene"
                if text:
                    events = outputs.get(text, [("ai", f"Reply to {text}.")])
                    session["events"].append(
                        {
                            "event_type": "command" if command else "message",
                            "event_source": "user",
                            "direction": "inbound",
                            "content": text,
                            "turn_index": turn_index,
                        }
                    )
                else:
                    events = [("info", "Setup info"), ("ai", "**Opening scene.**")]
                for kind, content in events:
                    session["events"].append(
                        {
                            "event_type": "command" if command else {"ai": "message", "warning": "info"}.get(kind, kind),
                            "event_source": "npc" if kind == "ai" and not command else "system",
                            "direction": "outbound",
                            "content": content,
                            "turn_index": turn_index,
                        }
                    )
                    self.history.append(SimpleNamespace(event_type=kind, content=content))
                if any(kind == "ai" for kind, _ in events):
                    snapshot["turn_count"] = turn_index
                    transcript = snapshot["game_state"]["filtered_transcript_buffer"]
                    reply = next(content for kind, content in events if kind == "ai")
                    if text and not command:
                        transcript.append(f"Player ({session['pc_hid']}): {text}")
                        transcript.append(f"Simulator: {reply}")
                    else:
                        transcript.append(f"Opening scene: {reply}")

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def health(self):
            return {"status": "ok"}

        def server_config(self):
            return SimpleNamespace(authentication_required=False)

        def start_game(self, body):
            assert body.source == "hitl"
            with lock:
                session_id = f"session-{len(sessions) + 1}"
                sessions[session_id] = {
                    "game_name": body.game,
                    "pc_hid": body.pc_choice,
                    "npc_hid": body.npc_choice,
                    "status": "paused",
                    "events": [],
                }
            return Run(session_id)

        def branch_session(self, session_id, **kwargs):
            with lock:
                assert sessions[session_id]["status"] in ("active", "paused")
                branch_id = f"session-{len(sessions) + 1}"
                sessions[branch_id] = deepcopy(sessions[session_id])
                sessions[branch_id]["branch_from_session_id"] = session_id
            return Run(branch_id)

    def reconstruct(url, **kwargs):
        session_id = url.split("/")[-2]
        if session_id not in sessions:
            return httpx.Response(404, request=httpx.Request("GET", url))
        session = sessions[session_id]
        return httpx.Response(
            200,
            json={"session": session, "events": session["events"]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("dcs_simulation_engine.api.client.APIClient", Client)
    monkeypatch.setattr(responses, "APIClient", Client)
    monkeypatch.setattr(responses, "SimulationRun", lambda *, session_id, **kwargs: Run(session_id))
    monkeypatch.setattr(responses.httpx, "get", reconstruct)
    return SimpleNamespace(sessions=sessions, calls=calls, outputs=outputs, client=Client)


def _branches(node):
    return [entry for entry in node["transcript"] if entry["type"] == "branch"]


def _inputs(node):
    return [entry["content"] for entry in node["events"] if entry["direction"] == "inbound"]


def test_generates_nested_forks_and_rates_every_response(evaluation, backend, monkeypatch):
    """Rate openings and every reply, including multiple outputs from a turn."""
    path, data = evaluation
    data["evaluator_id"] = "MW"
    data["results"] = {"summary": "Keep my summary."}
    data["sessions"][0]["transcript"] = [
        _pc("Context"),
        _branch(_pc("First", evaluator_note="Watch for continuity."), _branch(_pc("Nested"))),
        _branch(_pc("Sibling")),
        _pc("Continue the main session"),
    ]
    backend.outputs["First"] = [("ai", "First reply"), ("warning", "Warning"), ("error", "Error")]
    _write(path, data)

    result = _update("--skip-player-feedback")
    assert result.exit_code == 0, result.output
    saved = load_evaluation_file(path)
    root = saved["sessions"][0]
    first, sibling = _branches(root)
    (nested,) = _branches(first)
    root_id, first_id, sibling_id, nested_id = (node["session_id"] for node in (root, first, sibling, nested))
    assert len({root_id, first_id, sibling_id, nested_id}) == 4
    assert _inputs(backend.sessions[root_id]) == ["Context", "Continue the main session"]
    assert _inputs(backend.sessions[first_id]) == ["Context", "First"]
    assert _inputs(backend.sessions[sibling_id]) == ["Context", "Sibling"]
    assert _inputs(backend.sessions[nested_id]) == ["Context", "First", "Nested"]
    assert backend.sessions[nested_id]["branch_from_session_id"] == first_id
    assert first["transcript"][0]["evaluator_note"] == "Watch for continuity."
    assert saved["evaluator_id"] == "MW"
    assert saved["created_at"] == data["created_at"]
    assert saved["updated_at"] > data["updated_at"]
    assert saved["results"]["response_types"] == {"ai": 6, "info": 0, "warning": 1, "error": 1}
    assert saved["results"]["counts"]["turns"] == 5
    assert saved["results"]["counts"]["sessions"] == 1
    assert not saved["results"]["complete"]

    def unavailable(self):
        raise AssertionError("Feedback on recorded responses should work offline.")

    monkeypatch.setattr(backend.client, "health", unavailable)
    result = _update("--skip-simulator-responses", input="\n" + "u\n\n" * 7)
    assert result.exit_code == 0, result.output
    assert "Instructions: Thoroughly evaluate" in result.output
    for session_id in (root_id, first_id, sibling_id, nested_id):
        assert f"Session ID: {session_id}" in result.output
    history_lines = [" ".join(line.split()) for line in result.output.splitlines()]
    assert "System: Setup info" in history_lines
    assert "Simulator: Opening scene." in history_lines
    assert "PC: Context" in history_lines
    assert "Opening scene." in result.output and "**Opening scene.**" not in result.output
    assert "Evaluation summary complete: no" in result.output
    assert "Watch for continuity." in result.output
    assert load_evaluation_file(path)["results"]["counts"]["rated"] == 7
    assert not load_evaluation_file(path)["results"]["complete"]
    result = _update("--skip-simulator-responses", input="d\nos\nOpening feedback\n")
    assert result.exit_code == 0, result.output
    assert "Evaluation summary complete: yes" in result.output
    saved = load_evaluation_file(path)
    assert saved["sessions"][0]["transcript"][1]["evaluator_feedback"]["comment"] == "Opening feedback"
    assert saved["results"]["complete"]
    assert saved["results"]["counts"] == {
        "sessions": 1,
        "turns": 5,
        "rated": 8,
        "thumbs_up": 7,
        "thumbs_down": 1,
        "doesnt_make_sense": 1,
        "out_of_character": 1,
        "other": 0,
    }
    assert saved["results"]["summary"] == "Keep my summary."


@pytest.mark.parametrize("summary", [None, "", " \n\t "])
def test_complete_requires_a_written_summary(evaluation, summary):
    """A rated evaluation needs a nonblank written summary before it is complete."""
    path, data = evaluation
    if summary is not None:
        data["results"] = {"summary": summary}
    data["sessions"][0]["transcript"] = [
        {"type": "message", "source": "npc", "content": "Opening scene.", "evaluator_feedback": RATED},
    ]
    _write(path, data)
    result = _update("--skip-simulator-responses", "--skip-player-feedback")
    assert result.exit_code == 0, result.output
    assert "Evaluation summary complete: no" in result.output
    saved = load_evaluation_file(path)
    assert not saved["results"]["complete"]

    saved["results"]["summary"] = "The opening was consistent with the character."
    _write(path, saved)
    result = _update("--skip-simulator-responses", "--skip-player-feedback")
    assert result.exit_code == 0, result.output
    assert "Evaluation summary complete: yes" in result.output
    assert load_evaluation_file(path)["results"]["complete"]


def test_rerun_recovers_saved_reply_and_keeps_existing_branch(evaluation, backend):
    """Recover a committed server reply without advancing that turn again."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [_pc("Parent"), _branch(_pc("Branch"))]
    _write(path, data)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    current = load_evaluation_file(path)
    root = current["sessions"][0]
    (child,) = _branches(root)
    child_id = child["session_id"]
    child["transcript"].pop()
    root["transcript"].append(_pc("New main turn"))
    _write(path, current)
    previous_calls = list(backend.calls)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    root = load_evaluation_file(path)["sessions"][0]
    assert _branches(root)[0]["session_id"] == child_id
    assert _branches(root)[0]["transcript"][1]["content"] == "Reply to Branch."
    assert backend.calls == [*previous_calls, (root["session_id"], "New main turn")]
    before = path.read_bytes()
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    assert path.read_bytes() == before


def test_rerun_preserves_live_command_reply_type(evaluation, backend):
    """Match the transcript when the API persists an AI reply as a command event."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [_pc("/new-scene"), _branch(_pc("In the new scene"))]
    _write(path, data)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    before = path.read_bytes()
    calls = list(backend.calls)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    saved = load_evaluation_file(path)
    assert saved["sessions"][0]["transcript"][3]["type"] == "message"
    assert saved["results"]["response_types"]["ai"] == 3
    assert backend.calls == calls
    assert path.read_bytes() == before


def test_branch_continues_when_event_log_is_behind_its_snapshot(evaluation, backend, monkeypatch):
    """Use verified snapshot dialogue to continue a branch with missing event rows."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [_branch(_pc("First branch turn"))]
    _write(path, data)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    current = load_evaluation_file(path)
    root = current["sessions"][0]
    (child,) = _branches(root)
    child_id = child["session_id"]
    server_child = backend.sessions[child_id]
    server_child["events"] = deepcopy(backend.sessions[root["session_id"]]["events"])
    child["transcript"][-1]["evaluator_feedback"] = RATED
    child["transcript"].append(_pc("Next branch turn"))
    _write(path, current)
    monkeypatch.setattr(responses, "sleep", lambda _: None)

    calls = list(backend.calls)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    (after,) = _branches(load_evaluation_file(path)["sessions"][0])
    assert after["session_id"] == child_id
    assert after["transcript"][-1]["content"] == "Reply to Next branch turn."
    assert after["transcript"][1]["evaluator_feedback"] == RATED
    assert backend.calls == [*calls, (child_id, "Next branch turn")]

    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    assert backend.calls == [*calls, (child_id, "Next branch turn")]
    assert not list(path.parent.glob("*.backup-*.json"))


@pytest.mark.parametrize("bad_id", [None, "not-found", "wrong-parent"])
def test_invalid_branch_regenerates_only_after_confirmation(evaluation, backend, bad_id):
    """Regenerate one invalid branch and preserve its valid sibling."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [
        _pc("Context"),
        _branch(_pc("Change", evaluator_note="Keep my note.")),
        _branch(_pc("Keep")),
    ]
    _write(path, data)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    current = load_evaluation_file(path)
    old_root = current["sessions"][0]
    regenerate, keep = _branches(old_root)
    if bad_id == "wrong-parent":
        backend.sessions[regenerate["session_id"]]["branch_from_session_id"] = "different-parent"
    else:
        regenerate["session_id"] = bad_id
    keep["transcript"][-1]["evaluator_feedback"] = RATED
    regenerate["transcript"][-1]["evaluator_feedback"] = RATED
    _write(path, current)
    before = path.read_bytes()
    calls = list(backend.calls)

    result = _update("--skip-player-feedback")
    assert result.exit_code == 1
    assert "--replay-invalid-sessions" in result.output
    result = _update("--skip-player-feedback", "--replay-invalid-sessions", input="n\n")
    assert result.exit_code == 0, result.output
    assert path.read_bytes() == before
    assert backend.calls == calls
    assert not list(path.parent.glob("*.backup-*.json"))

    result = _update("--skip-player-feedback", "--replay-invalid-sessions", input="y\n")
    assert result.exit_code == 0, result.output
    (backup,) = path.parent.glob("*.backup-*.json")
    assert backup.read_bytes() == before
    root = load_evaluation_file(path)["sessions"][0]
    saved_regenerated, saved_keep = _branches(root)
    assert root["session_id"] == old_root["session_id"]
    assert saved_keep == keep
    assert saved_regenerated["session_id"] != regenerate["session_id"]
    assert saved_regenerated["transcript"][0]["evaluator_note"] == "Keep my note."
    assert saved_regenerated["transcript"][-1]["evaluator_feedback"] is None
    assert backend.calls == [*calls, (saved_regenerated["session_id"], "Change")]


def test_new_branch_at_past_turn_replays_using_existing_api(evaluation, backend):
    """Rebuild a parent when the API's current snapshot is past the fork."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [_pc("Before fork"), _pc("After fork")]
    _write(path, data)
    assert (result := _update("--skip-player-feedback")).exit_code == 0, result.output
    current = load_evaluation_file(path)
    old = current["sessions"][0]
    old["transcript"].insert(4, _branch(_pc("Different path")))
    _write(path, current)

    result = _update("--skip-player-feedback")
    assert result.exit_code == 1
    assert "past a branch" in result.output
    result = _update("--skip-player-feedback", "--replay-invalid-sessions", input="y\n")
    assert result.exit_code == 0, result.output
    root = load_evaluation_file(path)["sessions"][0]
    (branch,) = _branches(root)
    assert root["session_id"] != old["session_id"]
    assert _inputs(backend.sessions[root["session_id"]]) == ["Before fork", "After fork"]
    assert _inputs(backend.sessions[branch["session_id"]]) == ["Before fork", "Different path"]


def test_selection_and_only_history_keep_whole_file_results(evaluation, backend):
    """Limit generation to the selection and keep whole-file totals."""
    path, data = evaluation
    data["sessions"] *= 2
    data["sessions"] = [deepcopy(session) for session in data["sessions"]]
    data["sessions"][0]["transcript"] = [_pc("First root"), _branch(_pc("First branch"))]
    data["sessions"][1]["transcript"] = [_pc("Second root")]
    _write(path, data)
    result = _update("--only-history", "--session", "1")
    assert result.exit_code == 0, result.output
    saved = load_evaluation_file(path)
    assert saved["results"]["counts"]["sessions"] == 2
    assert saved["results"]["counts"]["turns"] == 3
    assert not saved["results"]["complete"]
    assert saved["sessions"][1] == data["sessions"][1]
    assert _branches(saved["sessions"][0])[0]["session_id"] is None
    assert len(backend.calls) == 2

    result = _update("--skip-player-feedback", "--exclude-session", "2")
    assert result.exit_code == 0, result.output
    assert len(backend.calls) == 3
    assert load_evaluation_file(path)["sessions"][1] == data["sessions"][1]


@pytest.mark.parametrize("options", [["--session", "0"], ["--exclude-session", "9"], ["--concurrency", "0"]])
def test_invalid_selection_fails_without_writes(evaluation, backend, options):
    """Reject invalid selectors before gameplay or file writes."""
    path, _ = evaluation
    before = path.read_bytes()
    assert _update(*options).exit_code != 0
    assert path.read_bytes() == before
    assert not backend.calls


def test_invalid_transcript_fails_without_writes(evaluation, backend):
    """Validate nested authored prompts before gameplay."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [_branch(_pc(" "))]
    _write(path, data)
    before = path.read_bytes()
    result = _update()
    assert result.exit_code == 1
    assert "nonblank string" in result.output
    assert path.read_bytes() == before
    assert not backend.calls


def test_backup_failure_stops_before_regeneration(evaluation, backend, monkeypatch):
    """Leave the file and server alone when the original cannot be backed up."""
    path, data = evaluation
    data["sessions"][0]["session_id"] = "missing"
    _write(path, data)
    before = path.read_bytes()

    def unavailable(_):
        raise OSError("Backup destination unavailable")

    monkeypatch.setattr(responses, "backup_evaluation_file", unavailable)
    result = _update("--replay-invalid-sessions", input="y\n")
    assert result.exit_code == 1
    assert "Backup destination unavailable" in result.output
    assert path.read_bytes() == before
    assert not backend.sessions


def test_update_reports_character_rejected_by_server(evaluation, backend, monkeypatch):
    """An unverified scaffold can be created and a rejected session reports the server reason."""
    existing_path, _ = evaluation
    hid = "unseeded-character"
    created = RUNNER.invoke(app, ["hitl", "create", hid])
    assert created.exit_code == 0, created.output
    path = existing_path.with_name(f"{hid}-evaluation.json")
    before = path.read_bytes()

    def reject_character(self, body):
        assert body.npc_choice == hid
        raise APIRequestError(f"Invalid npc_choice: {hid}")

    monkeypatch.setattr(backend.client, "start_game", reject_character)
    result = RUNNER.invoke(app, ["hitl", "update", hid, "--api-key", "test-key"])
    assert result.exit_code == 1
    assert f"Session 1: Could not start Explore with PC NA and NPC {hid}." in " ".join(result.output.split())
    assert f"Invalid npc_choice: {hid}" in result.output
    assert path.read_bytes() == before


def test_preserves_annotations_edited_during_generation(evaluation, backend, monkeypatch):
    """Merge changed descriptions, notes, and summaries when saving a reply."""
    path, data = evaluation
    data["sessions"][0]["transcript"] = [_pc("Question")]
    _write(path, data)
    start = backend.client.start_game

    def start_game(client, body):
        run = start(client, body)
        advance = run.step

        def step(text=""):
            advance(text)
            if text:
                current = load_evaluation_file(path)
                current["results"]["summary"] = "Updated summary."
                current["sessions"][0]["description"] = "Updated description."
                current["sessions"][0]["transcript"][-1]["evaluator_note"] = "Updated note."
                _write(path, current)

        run.step = step
        return run

    monkeypatch.setattr(backend.client, "start_game", start_game)
    result = _update("--skip-player-feedback")
    assert result.exit_code == 0, result.output
    saved = load_evaluation_file(path)
    session = saved["sessions"][0]
    assert saved["results"]["summary"] == "Updated summary."
    assert session["description"] == "Updated description."
    assert session["transcript"][-2]["evaluator_note"] == "Updated note."
    assert session["transcript"][-1]["content"] == "Reply to Question."
