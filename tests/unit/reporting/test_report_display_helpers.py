"""Tests for shared report display helpers."""

import json

import pandas as pd
import pytest
from dcs_simulation_engine.reporting.auto.rendering.chart_utils import short_player_id
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.auto.sections import player_engagement, runs_overview, system_performance
from dcs_simulation_engine.reporting.loader import load_all

pytestmark = pytest.mark.unit


def test_short_player_id_keeps_suffix() -> None:
    """Long player IDs should display with their distinguishing suffix."""
    assert short_player_id("player-prefix-abcdef123456") == "...ef123456"
    assert short_player_id("short-id") == "short-id"


def test_datatable_shortens_player_id_columns() -> None:
    """DataTables should shorten player ID columns before rendering."""
    player_id = "shared-prefix-player-000000000001"

    html = df_to_datatable(
        pd.DataFrame({"player_id": [player_id], "runs": [3]}),
        table_id="players",
        rename={"player_id": "Player"},
    )

    assert "...00000001" in html
    assert player_id not in html


def test_player_id_chart_axes_use_short_labels() -> None:
    """Player chart axes should use shortened player IDs."""
    player_id = "shared-prefix-player-000000000001"

    html = player_engagement._runs_per_player(pd.DataFrame({"player_id": [player_id], "runs": [3]}))

    assert "...00000001" in html
    assert player_id not in html


def test_session_timeline_uses_short_player_id_label() -> None:
    """Session timeline labels should use shortened player IDs."""
    player_id = "shared-prefix-player-000000000001"

    html = system_performance._session_timeline(
        pd.DataFrame(
            [
                {
                    "session_id": "session-1",
                    "player_id": player_id,
                    "game_name": "Infer Intent",
                    "session_started_at": pd.Timestamp("2026-05-04T12:00:00Z"),
                    "session_ended_at": pd.Timestamp("2026-05-04T12:05:00Z"),
                    "termination_reason": "game_completed",
                }
            ]
        )
    )

    assert "Infer Intent" in html
    assert "...00000001" in html
    assert player_id not in html


def test_participation_funnel_counts_completed_assignments(tmp_path) -> None:
    """Participation funnel should count assignment lifecycle stages."""
    (tmp_path / "assignments.json").write_text(
        json.dumps(
            [
                {"assignment_id": "a1", "player_id": "p1", "status": "completed"},
                {"assignment_id": "a2", "player_id": "p1", "status": "in_progress"},
                {"assignment_id": "a3", "player_id": "p2", "status": "assigned"},
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "sessions.json").write_text(
        json.dumps(
            [
                {"session_id": "s1", "assignment_id": "a1", "player_id": "p1", "termination_reason": "game_completed"},
                {"session_id": "s2", "assignment_id": "a2", "player_id": "p1", "termination_reason": "user_exit_command"},
            ]
        ),
        encoding="utf-8",
    )

    data = load_all(tmp_path)

    stages, values, title = runs_overview._participation_funnel_values(data)

    assert title == "Assignment Participation Funnel"
    assert stages == ["Assignments Created", "Assignments Started", "Assignments Completed"]
    assert values == [3, 2, 1]


def test_session_completion_status_recognizes_game_completed() -> None:
    """Session completion helper should recognize engine completion reasons."""
    assert runs_overview._is_completed_session_status("game_completed") is True
    assert runs_overview._is_completed_session_status("stopping_condition_met:_turns_>=50") is True
    assert runs_overview._is_completed_session_status("user_exit_command") is False
