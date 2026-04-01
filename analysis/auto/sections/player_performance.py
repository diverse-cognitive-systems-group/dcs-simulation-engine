"""Section 6 — Player Performance.

A summary DataTable (one row per player, aggregated stats) plus a
grouped bar chart comparing average turns and average duration per player.
"""

from __future__ import annotations

import pandas as pd

from dcs_utils.analysis.auto.rendering.chart_utils import plotly_to_html
from dcs_utils.analysis.auto.rendering.table_utils import df_to_datatable
from dcs_utils.analysis.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    df = data.runs_df

    if df.empty:
        return '<div class="alert alert-info">No run data found.</div>'

    agg: dict = {"session_id": "count"}
    if "turns_completed" in df.columns:
        agg["turns_completed"] = ["mean", "sum"]
    if "duration_minutes" in df.columns:
        agg["duration_minutes"] = ["mean", "sum"]

    perf = df.groupby("player_id").agg(agg)
    perf.columns = ["_".join(c).strip("_") for c in perf.columns]
    perf = perf.rename(columns={"session_id_count": "total_runs"}).round(2).reset_index()

    rename = {
        "player_id":                  "Player",
        "total_runs":                 "Total Runs",
        "turns_completed_mean":       "Avg Turns",
        "turns_completed_sum":        "Total Turns",
        "duration_minutes_mean":      "Avg Duration (min)",
        "duration_minutes_sum":       "Total Duration (min)",
    }

    table_html = df_to_datatable(
        perf,
        table_id="player-performance-table",
        rename={k: v for k, v in rename.items() if k in perf.columns},
    )

    chart_html = _perf_chart(perf)

    return f"{chart_html}\n{table_html}"


def _perf_chart(perf: pd.DataFrame) -> str:
    import plotly.graph_objects as go

    fig = go.Figure()
    if "turns_completed_mean" in perf.columns:
        fig.add_trace(go.Bar(
            x=perf["player_id"],
            y=perf["turns_completed_mean"],
            name="Avg Turns",
        ))
    if "duration_minutes_mean" in perf.columns:
        fig.add_trace(go.Bar(
            x=perf["player_id"],
            y=perf["duration_minutes_mean"],
            name="Avg Duration (min)",
        ))
    fig.update_layout(
        barmode="group",
        title="Player Performance Overview",
        xaxis_title="Player",
        height=350,
        margin=dict(l=20, r=20, t=40, b=60),
    )
    return f'<div class="chart-container">{plotly_to_html(fig)}</div>'
