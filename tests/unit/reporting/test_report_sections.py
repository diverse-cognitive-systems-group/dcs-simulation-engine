"""Tests for report section labels and descriptive copy."""

import json

import pytest
from dcs_simulation_engine.reporting.auto import resolve_sections, run_analysis
from dcs_simulation_engine.reporting.loader import load_all

pytestmark = pytest.mark.unit


def test_event_log_section_replaces_transcripts_label_and_explains_filters(tmp_path) -> None:
    (tmp_path / "session_events.json").write_text(
        json.dumps(
            [
                {
                    "session_id": "session-1",
                    "event_source": "user",
                    "event_type": "message",
                    "content": "Hello",
                    "turn_index": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    data = load_all(tmp_path)
    html = run_analysis(data, sections=resolve_sections(only=["event-log"], include=None, exclude=None))

    assert "<h2>Full Event Log</h2>" in html
    assert "filter Type to message and Source to user or npc" in html
    assert 'id="event-log-table"' in html
    assert "<h2>Transcripts</h2>" not in html
