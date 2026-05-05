"""Tests for loading persisted DB log dumps into reporting dataframes."""

import json

from dcs_simulation_engine.reporting.auto.sections import system_errors
from dcs_simulation_engine.reporting.loader import load_all


def test_load_all_reads_persisted_logs_json(tmp_path) -> None:
    """A dumped logs.json collection should populate logs_df and errors_df."""
    logs = [
        {
            "event_id": "log-1",
            "event_ts": "2026-05-04T12:00:00+00:00",
            "persisted_at": "2026-05-04T12:00:01+00:00",
            "source": "dcs-api",
            "level": "ERROR",
            "level_no": 40,
            "message": "Persisted DB log",
            "module": "example",
            "function": "run",
            "line": 12,
            "exception": {"type": "RuntimeError", "value": "boom"},
        }
    ]
    (tmp_path / "logs.json").write_text(json.dumps(logs), encoding="utf-8")

    data = load_all(tmp_path)

    assert len(data.logs_df) == 1
    assert data.logs_df.iloc[0]["message"] == "Persisted DB log"
    assert data.logs_df.iloc[0]["level"] == "ERROR"
    assert data.logs_df.iloc[0]["log_file"] == "logs.json"
    assert data.logs_source == "logs.json"
    assert len(data.errors_df) == 1


def test_system_errors_reports_empty_persisted_logs_as_clean_state(tmp_path) -> None:
    """An empty logs.json should read as no logged engine errors, not missing logs."""
    (tmp_path / "logs.json").write_text("[]", encoding="utf-8")

    data = load_all(tmp_path)
    html = system_errors.render(data)

    assert data.logs_source == "logs.json"
    assert data.logs_df.empty
    assert "logs.json was found, but no engine log entries were recorded for this run." in html
    assert "No log files found" not in html
    assert "No error log data available" not in html
