"""Tests for the Player Performance report section."""

import json

import pytest
from dcs_simulation_engine.reporting.auto.sections import player_performance
from dcs_simulation_engine.reporting.loader import load_all

pytestmark = pytest.mark.unit


def test_player_performance_renders_score_summaries_by_player_and_game(tmp_path) -> None:
    """Runtime score state should render player/game performance summaries."""
    (tmp_path / "sessions.json").write_text(
        json.dumps(
            [
                {
                    "session_id": "s1",
                    "player_id": "p1",
                    "game_name": "Foresight",
                    "pc_hid": "PC1",
                    "npc_hid": "NPC1",
                    "turns_completed": 4,
                    "duration_minutes": 8,
                    "termination_reason": "game_completed",
                    "runtime_state": {
                        "game_state": {
                            "score": {
                                "tier": 2,
                                "score": 80,
                                "reasoning": "Strong prediction with clear evidence.",
                            }
                        }
                    },
                },
                {
                    "session_id": "s2",
                    "player_id": "p1",
                    "game_name": "Teamwork",
                    "pc_hid": "PC1",
                    "npc_hid": "NPC2",
                    "turns_completed": 5,
                    "duration_minutes": 10,
                    "termination_reason": "game_completed",
                    "runtime_state": {"game_state": {"score": {"tier": 1, "score": 40, "reasoning": "Partial answer."}}},
                },
                {
                    "session_id": "s3",
                    "player_id": "p2",
                    "game_name": "Foresight",
                    "pc_hid": "PC2",
                    "npc_hid": "NPC1",
                    "turns_completed": 6,
                    "duration_minutes": 12,
                    "termination_reason": "game_completed",
                    "runtime_state": {"game_state": {"score": {"tier": 3, "score": 100, "reasoning": "Exact answer."}}},
                },
            ]
        ),
        encoding="utf-8",
    )

    data = load_all(tmp_path)
    html = player_performance.render(data)

    assert "Scored Sessions" in html
    assert "Average Score by Game" in html
    assert "Average Score by Player" in html
    assert 'id="player-game-performance-table"' in html
    assert 'id="scored-sessions-table"' in html
    assert "Foresight" in html
    assert "Teamwork" in html
    assert "Strong prediction with clear evidence." in html


def test_player_performance_reports_missing_scores(tmp_path) -> None:
    """Player performance should show a clear empty state when no scores exist."""
    (tmp_path / "sessions.json").write_text(
        json.dumps([{"session_id": "s1", "player_id": "p1", "game_name": "Explore"}]),
        encoding="utf-8",
    )

    data = load_all(tmp_path)
    html = player_performance.render(data)

    assert "No scored gameplay sessions found." in html


def test_player_performance_uses_persisted_final_score_events(tmp_path) -> None:
    """Persisted final-score events should feed the performance report."""
    (tmp_path / "sessions.json").write_text(
        json.dumps(
            [
                {
                    "session_id": "s1",
                    "player_id": "p1",
                    "game_name": "Infer Intent",
                    "pc_hid": "PC1",
                    "npc_hid": "NPC1",
                    "turns_completed": 3,
                    "termination_reason": "game_completed",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "session_events.json").write_text(
        json.dumps(
            [
                {
                    "session_id": "s1",
                    "event_source": "system",
                    "event_type": "info",
                    "direction": "outbound",
                    "content": "## Final Score\n- Tier: 2\n- Score: 65\n\n### Reasoning\nPartial match.",
                    "event_ts": "2026-05-04T12:00:00+00:00",
                    "turn_index": 4,
                }
            ]
        ),
        encoding="utf-8",
    )

    data = load_all(tmp_path)
    html = player_performance.render(data)

    assert "No scored gameplay sessions found" not in html
    assert "Infer Intent" in html
    assert "65" in html
    assert "Partial match." in html
