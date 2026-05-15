"""Tests for whole-number report chart axes."""

import pandas as pd
import plotly.graph_objects as go
import pytest
from dcs_simulation_engine.reporting.auto.rendering.chart_utils import use_integer_ticks
from dcs_simulation_engine.reporting.auto.sections import system_performance

pytestmark = pytest.mark.unit


def test_use_integer_ticks_updates_requested_axes() -> None:
    """Integer tick helper should configure both requested Plotly axes."""
    fig = go.Figure(go.Bar(x=[1, 2], y=[3, 4]))

    use_integer_ticks(fig, x=True, y=True)

    assert fig.layout.xaxis.dtick == 1
    assert fig.layout.xaxis.tickformat == ",d"
    assert fig.layout.yaxis.dtick == 1
    assert fig.layout.yaxis.tickformat == ",d"


def test_game_duration_distribution_can_render_minutes_axis() -> None:
    """Game duration distribution should render minute units."""
    html = system_performance._lt_hist_kde(
        pd.Series([1.5, 2.0, 2.5]),
        "Game Duration Distribution (All Players)",
        "Duration (minutes)",
        annotation_unit="min",
        annotation_decimals=1,
    )

    assert "Duration (minutes)" in html
    assert "min" in html
