"""Tests for whole-number report chart axes."""

import pandas as pd
import pytest
from dcs_simulation_engine.reporting.auto.sections import player_feedback, runs_overview, system_performance

pytestmark = pytest.mark.unit


def test_turns_distribution_uses_integer_ticks_for_turns_and_sessions() -> None:
    html = runs_overview._turns_distribution(pd.DataFrame({"turns_completed": [1, 2, 2, 3]}))

    assert html.count('"dtick":1') >= 2
    assert html.count('"tickformat":",d"') >= 2


def test_flags_over_turns_uses_integer_ticks_for_turns_and_counts() -> None:
    html = player_feedback._flags_over_turns_chart(
        pd.DataFrame(
            {
                "turn_index": [1, 2, 2],
                "feedback.liked": [False, False, False],
                "feedback.out_of_character": [True, False, True],
                "feedback.doesnt_make_sense": [False, True, False],
            }
        )
    )

    assert html.count('"dtick":1') >= 2
    assert html.count('"tickformat":",d"') >= 2


def test_game_duration_distribution_can_render_minutes_axis() -> None:
    html = system_performance._lt_hist_kde(
        pd.Series([1.5, 2.0, 2.5]),
        "Game Duration Distribution (All Players)",
        "Duration (minutes)",
        annotation_unit="min",
        annotation_decimals=1,
    )

    assert "Duration (minutes)" in html
    assert "min" in html
