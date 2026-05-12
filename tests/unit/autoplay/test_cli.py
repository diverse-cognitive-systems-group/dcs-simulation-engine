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
    logs = list((tmp_path / "runlogs").glob("autoplay-*.log"))
    assert len(logs) == 1
    log_text = logs[0].read_text(encoding="utf-8")
    assert "run_config" in log_text
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
