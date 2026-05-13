"""Unit tests for the autoplay CLI."""

from autoplay import cli
from typer.testing import CliRunner


def test_openrouter_player_requires_api_key_before_api_work(monkeypatch, tmp_path) -> None:
    """OpenRouter players should fail preflight before contacting the engine API."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli.app, ["--model", "openrouter:openai/gpt-4.1-mini"])

    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY is required" in result.stdout
    assert "HTTP Request:" not in result.stdout


def test_openrouter_preflight_reads_dotenv(monkeypatch, tmp_path) -> None:
    """OpenRouter preflight should accept keys from the working directory .env file."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=dotenv-key\n", encoding="utf-8")

    async def run_players(**kwargs):
        _ = kwargs
        return []

    monkeypatch.setattr(cli, "_run_players", run_players)

    result = CliRunner().invoke(
        cli.app,
        [
            "--model",
            "openrouter:openai/gpt-4.1-mini",
            "--max-turns-per-assignment",
            "3",
            "--timeout",
            "2",
            "--log-dir",
            "runlogs",
        ],
    )

    assert result.exit_code == 0
    assert "OPENROUTER_API_KEY is required" not in result.stdout
    assert "Autoplay run" in result.stdout
    assert "Max turns per assignment: 3" in result.stdout
    assert "Timeout: 2s" in result.stdout
    assert "Model system prompt:" in result.stdout
    logs = list((tmp_path / "runlogs").glob("autoplay_*.log"))
    assert len(logs) == 1
    log_text = logs[0].read_text(encoding="utf-8")
    assert " autoplay INFO cli.py:" in log_text
    assert " | Autoplay run started" in log_text
    assert "Autoplay run started" in log_text
    assert "Models: openrouter:openai/gpt-4.1-mini" in log_text
    assert "info messages that explain the objective" in log_text


def test_character_summary_uses_hids_only() -> None:
    """Character summaries should not duplicate display names."""
    assert cli._character_summary(
        {
            "pc_hid": "NA",
            "npc_hid": "AS",
            "player_character_name": "NA",
            "simulator_character_name": "AS",
        }
    ) == "PC: NA, NPC: AS"


def test_event_printer_displays_and_logs_transcript_events(tmp_path, capsys) -> None:
    """CLI transcript events should be readable and persisted to the autoplay log."""
    cli._configure_logging(log_dir=tmp_path, quiet=False)
    printer = cli._event_printer(quiet=False)
    base_payload = {"model_id": "scripted"}

    printer(
        "assignment_started",
        {
            **base_payload,
            "game_name": "Explore",
            "pc_hid": "NA",
            "npc_hid": "AS",
            "session_id": "session-1",
            "assignment_id": "assignment-1",
        },
    )
    printer(
        "message_received",
        {
            **base_payload,
            "role": "server",
            "event_type": "info",
            "content": "Use /help to see available commands.",
        },
    )
    printer("turn_sent", {**base_payload, "turns": 1, "input": "I look around."})
    printer(
        "message_received",
        {
            **base_payload,
            "role": "simulator",
            "event_type": "ai",
            "content": "You see a quiet room.",
        },
    )
    printer(
        "message_received",
        {
            **base_payload,
            "role": "server",
            "event_type": "error",
            "content": "That action failed.",
        },
    )
    printer("assignment_exited", {**base_payload, "turns": 2, "reason": "done"})

    output = capsys.readouterr().out
    assert "Assignment 1: Explore" in output
    assert "Characters: PC: NA, NPC: AS" in output
    assert "Info: Use /help to see available commands." in output
    assert "Turn 1" in output
    assert "Player: I look around." in output
    assert "Simulator: You see a quiet room." in output
    assert "Error: That action failed." in output
    assert "Assignment 1 ended after 1 turn(s)" in output

    logs = list(tmp_path.glob("autoplay_*.log"))
    assert len(logs) == 1
    log_text = logs[0].read_text(encoding="utf-8")
    for expected in [
        "Assignment 1 started: Explore",
        "Info: Use /help to see available commands.",
        "Turn 1 player input: I look around.",
        "Simulator: You see a quiet room.",
        "Server error: That action failed.",
        "Assignment 1 exited after 1 turn(s): done",
    ]:
        assert expected in log_text
    assert "event {" not in log_text
