"""Section 3 — System Performance.

Plotly charts covering run durations, pacing, exit reasons,
retry budget, PC/NPC pairings, and a session timeline (Gantt), followed by
system error details.
"""

from __future__ import annotations

from datetime import timezone

import pandas as pd

from analysis.auto.rendering.chart_utils import plotly_to_html
from analysis.auto.sections import system_errors
from analysis.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    df = data.runs_df
    parts: list[str] = []

    # Two-column grid rows
    def _row(*divs: str) -> str:
        cols = "".join(f'<div class="col-md-6 chart-container">{d}</div>' for d in divs)
        return f'<div class="row">{cols}</div>'

    def _full(*divs: str) -> str:
        cols = "".join(f'<div class="col-12 chart-container">{d}</div>' for d in divs)
        return f'<div class="row">{cols}</div>'

    if df.empty:
        parts.append('<div class="alert alert-info">No run data found.</div>')
    else:
        parts.append(_row(
            _exit_reasons(df),
            _duration_histogram(df),
        ))
        parts.append(_row(
            _duration_by_game(df),
            _turns_vs_runtime(df),
        ))
        parts.append(_row(
            _retry_budget(df),
        ))
        parts.append(_full(_session_timeline(df)))

    parts.append('<h3 class="h5 mt-4">System Errors</h3>')
    parts.append(system_errors.render(data))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Individual charts
# ---------------------------------------------------------------------------

def _pairing_heatmap(df: pd.DataFrame) -> str:
    import plotly.graph_objects as go

    games = df["game_name"].dropna().unique() if "game_name" in df.columns else []

    if len(games) <= 1 or "pc_hid" not in df.columns or "npc_hid" not in df.columns:
        return _single_heatmap(df, title="PC / NPC Pairing Heatmap")

    tab_nav = []
    tab_content = []
    for i, game in enumerate(sorted(games)):
        slug = game.replace(" ", "-").lower()
        active_nav = "active" if i == 0 else ""
        active_pane = "show active" if i == 0 else ""
        tab_nav.append(
            f'<li class="nav-item"><a class="nav-link {active_nav}" '
            f'data-bs-toggle="tab" href="#hm-{slug}">{game}</a></li>'
        )
        chart_html = _single_heatmap(df[df["game_name"] == game], title=game)
        tab_content.append(
            f'<div class="tab-pane fade {active_pane}" id="hm-{slug}">{chart_html}</div>'
        )

    return (
        '<p class="fw-semibold mb-1">PC / NPC Pairing Heatmap</p>'
        f'<ul class="nav nav-tabs mb-2">{"".join(tab_nav)}</ul>'
        f'<div class="tab-content">{"".join(tab_content)}</div>'
    )


def _single_heatmap(df: pd.DataFrame, title: str) -> str:
    import plotly.graph_objects as go

    if df.empty or "pc_hid" not in df.columns:
        return '<div class="alert alert-secondary">No pairing data.</div>'

    pivot = (
        df.groupby(["pc_hid", "npc_hid"])
        .size()
        .reset_index(name="runs")
        .pivot(index="pc_hid", columns="npc_hid", values="runs")
        .fillna(0)
    )
    fig = go.Figure(go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale="Blues",
        text=pivot.values.astype(int),
        texttemplate="%{text}",
        hovertemplate="PC: %{y}<br>NPC: %{x}<br>Runs: %{z}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="NPC",
        yaxis_title="PC",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return plotly_to_html(fig)


def _duration_histogram(df: pd.DataFrame) -> str:
    import plotly.express as px

    valid = df.dropna(subset=["duration_minutes"])
    if valid.empty:
        return '<div class="alert alert-secondary">No duration data.</div>'

    fig = px.histogram(
        valid,
        x="duration_minutes",
        nbins=20,
        title="Distribution of Run Durations",
        labels={"duration_minutes": "Duration (minutes)"},
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
    return plotly_to_html(fig)


def _duration_by_game(df: pd.DataFrame) -> str:
    import plotly.express as px

    valid = df.dropna(subset=["duration_minutes", "game_name"])
    if valid.empty:
        return '<div class="alert alert-secondary">No duration data.</div>'

    fig = px.box(
        valid,
        x="game_name",
        y="duration_minutes",
        title="Run Duration by Game",
        labels={"game_name": "Game", "duration_minutes": "Duration (minutes)"},
        points="all",
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
    return plotly_to_html(fig)


def _turns_vs_runtime(df: pd.DataFrame) -> str:
    import plotly.express as px

    needed = ["turns_completed", "duration_minutes"]
    valid = df.dropna(subset=needed)
    if valid.empty:
        return '<div class="alert alert-secondary">No turns/duration data.</div>'

    hover = [c for c in ["session_id", "pc_hid", "npc_hid"] if c in valid.columns]
    fig = px.scatter(
        valid,
        x="turns_completed",
        y="duration_minutes",
        color="game_name" if "game_name" in valid.columns else None,
        hover_data=hover,
        title="Run Pacing: Turns vs Runtime",
        labels={
            "turns_completed": "Turns Completed",
            "duration_minutes": "Duration (minutes)",
            "game_name": "Game",
        },
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
    return plotly_to_html(fig)


def _exit_reasons(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "termination_reason" not in df.columns:
        return '<div class="alert alert-secondary">No exit reason data.</div>'

    counts = df["termination_reason"].value_counts().reset_index()
    counts.columns = ["termination_reason", "count"]
    fig = px.bar(
        counts,
        x="termination_reason",
        y="count",
        title="Run Exit Reasons",
        labels={"termination_reason": "Exit Reason", "count": "Count"},
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
    return plotly_to_html(fig)


def _retry_budget(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "last_seq" not in df.columns:
        return '<div class="alert alert-secondary">No sequence data.</div>'

    counts = df["last_seq"].value_counts().sort_index().reset_index()
    counts.columns = ["last_seq", "count"]
    fig = px.bar(
        counts,
        x="count",
        y="last_seq",
        orientation="h",
        title="Runs by Event Count",
        labels={"last_seq": "Last Seq", "count": "Run Count"},
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=20))
    return plotly_to_html(fig)


def _session_timeline(df: pd.DataFrame) -> str:
    import plotly.express as px

    needed = ["session_started_at", "session_ended_at"]
    if not all(c in df.columns for c in needed):
        return '<div class="alert alert-secondary">No timeline data.</div>'

    gantt = df.dropna(subset=needed).copy()
    if gantt.empty:
        return '<div class="alert alert-secondary">No timeline data.</div>'

    now = pd.Timestamp.now(tz=timezone.utc)
    gantt["session_ended_at"] = gantt["session_ended_at"].fillna(now)
    gantt = gantt.sort_values("session_started_at")

    gantt["session_label"] = gantt.get("session_id", gantt.index).astype(str)
    if "game_name" in gantt.columns:
        gantt["session_label"] = gantt["game_name"].fillna("Run") + " • " + gantt["session_label"]

    fig = px.timeline(
        gantt,
        x_start="session_started_at",
        x_end="session_ended_at",
        y="session_label",
        color="termination_reason" if "termination_reason" in gantt.columns else None,
        title="Session Timeline",
        hover_data=[c for c in ["player_id", "pc_hid", "npc_hid"] if c in gantt.columns],
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(height=max(350, 24 * len(gantt)), margin=dict(l=20, r=20, t=40, b=20))
    return plotly_to_html(fig)
