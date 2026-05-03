"""Section 2 — Runs Overview Table.

Renders a DataTables interactive table with one row per session (run),
showing player, game, characters, turn count, duration, exit reason, etc.
"""

import pandas as pd
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.auto.sections.system_performance import _pairing_heatmap
from dcs_simulation_engine.reporting.loader import AnalysisData

# Source-column → display-name mapping (in display order)
_COLUMNS = [
    "session_id",
    "player_id",
    "game_name",
    "pc_hid",
    "npc_hid",
    "turns_completed",
    "duration_human",
    "termination_reason",
    "last_seq",
    "status",
    "session_started_at",
    "session_ended_at",
]

_RENAME = {
    "session_id": "Run ID",
    "player_id": "Player",
    "game_name": "Game",
    "pc_hid": "PC",
    "npc_hid": "NPC",
    "turns_completed": "Turns",
    "duration_human": "Duration",
    "termination_reason": "Exit Reason",
    "last_seq": "Last Seq",
    "status": "Status",
    "session_started_at": "Started",
    "session_ended_at": "Ended",
}


def render(data: AnalysisData) -> str:
    df = data.runs_df

    if df.empty:
        return '<div class="alert alert-info">No run data found.</div>'

    # Only include columns that actually exist in the DataFrame
    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    table_html = df_to_datatable(
        df,
        table_id="runs-overview-table",
        columns=cols,
        rename=rename,
        scroll_x=True,
        export_buttons=True,
    )

    def _row(*divs: str) -> str:
        cols_html = "".join(f'<div class="col-md-6 chart-container">{d}</div>' for d in divs)
        return f'<div class="row">{cols_html}</div>'

    return "\n".join(
        [
            section_intro("runs_overview"),
            _summary_stats_table(df),
            # Pairing heatmap (full width, top)
            '<div class="chart-container mb-4">' + _pairing_heatmap(df) + "</div>",
            chart_caption("runs_overview", "pairing_heatmap"),
            # Row 1: sessions over time + exit reasons
            _row(
                _sessions_over_time(df) + chart_caption("runs_overview", "sessions_over_time"),
                _exit_reasons(df) + chart_caption("runs_overview", "exit_reasons"),
            ),
            # Row 2: turns distribution + duration distribution
            _row(
                _turns_distribution(df) + chart_caption("runs_overview", "turns_distribution"),
                _duration_distribution(df) + chart_caption("runs_overview", "duration_distribution"),
            ),
            # Row 3: runs per game + completion by game
            _row(
                _runs_per_game(df) + chart_caption("runs_overview", "runs_per_game"),
                _completion_by_game(df) + chart_caption("runs_overview", "completion_by_game"),
            ),
            # Row 4: participation funnel + sessions per player
            _row(
                _participation_funnel(data) + chart_caption("runs_overview", "participation_funnel"),
                _sessions_per_player(df) + chart_caption("runs_overview", "sessions_per_player"),
            ),
            '<h3 class="h5 mt-4 mb-2">Gameplay Sessions</h3>',
            table_html,
            chart_caption("runs_overview", "sessions_table"),
        ]
    )


def _sessions_over_time(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "session_started_at" not in df.columns:
        return '<div class="alert alert-secondary">session_started_at not available.</div>'

    dates = pd.to_datetime(df["session_started_at"], utc=True, errors="coerce").dropna().dt.date
    daily = dates.value_counts().sort_index().rename_axis("date").reset_index(name="sessions")
    if daily.empty:
        return '<div class="alert alert-secondary">No timestamp data.</div>'

    fig = px.bar(daily, x="date", y="sessions", title="Sessions Over Time", labels={"date": "Date", "sessions": "Sessions Started"})
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=40))
    return _plotly(fig)


def _exit_reasons(df: pd.DataFrame) -> str:
    import plotly.express as px

    col = next((c for c in ("termination_reason", "exit_reason") if c in df.columns), None)
    if col is None:
        return '<div class="alert alert-secondary">Exit reason column not available.</div>'

    counts = df[col].fillna("unknown").value_counts().reset_index(name="count")
    counts.columns = ["reason", "count"]
    fig = px.bar(
        counts, x="count", y="reason", orientation="h", title="Exit Reasons", labels={"reason": "Exit Reason", "count": "Sessions"}
    )
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=40), yaxis={"categoryorder": "total ascending"})
    return _plotly(fig)


def _turns_distribution(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "turns_completed" not in df.columns:
        return '<div class="alert alert-secondary">turns_completed not available.</div>'

    valid = df["turns_completed"].dropna()
    if valid.empty:
        return '<div class="alert alert-secondary">No turn data.</div>'

    fig = px.histogram(valid, nbins=20, title="Turns Completed per Session", labels={"value": "Turns", "count": "Sessions"})
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=40), showlegend=False)
    return _plotly(fig)


def _duration_distribution(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "duration_minutes" not in df.columns:
        return '<div class="alert alert-secondary">duration_minutes not available.</div>'

    valid = df["duration_minutes"].dropna()
    if valid.empty:
        return '<div class="alert alert-secondary">No duration data.</div>'

    fig = px.histogram(valid, nbins=20, title="Session Duration Distribution", labels={"value": "Duration (min)", "count": "Sessions"})
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=40), showlegend=False)
    return _plotly(fig)


def _runs_per_game(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "game_name" not in df.columns:
        return '<div class="alert alert-secondary">game_name not available.</div>'

    counts = df["game_name"].fillna("unknown").value_counts().rename_axis("game").reset_index(name="sessions")
    fig = px.bar(counts, x="sessions", y="game", orientation="h", title="Runs per Game", labels={"game": "Game", "sessions": "Sessions"})
    fig.update_layout(
        height=max(250, 60 + len(counts) * 30), margin=dict(l=20, r=20, t=40, b=40), yaxis={"categoryorder": "total ascending"}
    )
    return _plotly(fig)


def _completion_by_game(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "game_name" not in df.columns:
        return '<div class="alert alert-secondary">game_name not available.</div>'

    status_col = next((c for c in ("termination_reason", "status") if c in df.columns), None)
    if status_col is None:
        return '<div class="alert alert-secondary">Status column not available.</div>'

    tmp = df[["game_name", status_col]].copy()
    tmp["game_name"] = tmp["game_name"].fillna("unknown")
    tmp["completed"] = tmp[status_col].fillna("").str.lower().eq("completed")
    tmp["outcome"] = tmp["completed"].map({True: "Completed", False: "Not Completed"})

    grouped = tmp.groupby(["game_name", "outcome"]).size().reset_index(name="count")
    fig = px.bar(
        grouped,
        x="count",
        y="game_name",
        color="outcome",
        orientation="h",
        barmode="stack",
        title="Completion by Game",
        labels={"game_name": "Game", "count": "Sessions", "outcome": "Outcome"},
        color_discrete_map={"Completed": "#2ecc71", "Not Completed": "#e74c3c"},
    )
    fig.update_layout(
        height=max(250, 60 + df["game_name"].nunique() * 30),
        margin=dict(l=20, r=20, t=40, b=40),
        yaxis={"categoryorder": "total ascending"},
    )
    return _plotly(fig)


def _participation_funnel(data: "AnalysisData") -> str:
    import plotly.graph_objects as go

    df = data.runs_df
    assigned = len(data.assignments_df) if not data.assignments_df.empty else None
    started = df["player_id"].nunique() if "player_id" in df.columns else 0

    status_col = next((c for c in ("termination_reason", "status") if c in df.columns), None)
    if status_col is not None:
        completed_ids = df.loc[df[status_col].fillna("").str.lower().eq("completed"), "player_id"].nunique()
    else:
        completed_ids = None

    stages, values = [], []
    if assigned:
        stages.append("Assigned")
        values.append(assigned)
    stages.append("Started (≥1 session)")
    values.append(started)
    if completed_ids is not None:
        stages.append("Completed (≥1 session)")
        values.append(completed_ids)

    fig = go.Figure(go.Funnel(y=stages, x=values, textinfo="value+percent initial"))
    fig.update_layout(title="Player Participation Funnel", height=300, margin=dict(l=20, r=20, t=40, b=40))
    return _plotly(fig)


def _sessions_per_player(df: pd.DataFrame) -> str:
    import plotly.express as px

    if "player_id" not in df.columns:
        return '<div class="alert alert-secondary">player_id not available.</div>'

    counts = df.groupby("player_id").size()
    fig = px.histogram(
        counts, nbins=max(1, counts.nunique()), title="Sessions per Player", labels={"value": "Sessions Completed", "count": "Players"}
    )
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=40), showlegend=False)
    return _plotly(fig)


def _plotly(fig) -> str:
    from dcs_simulation_engine.reporting.auto.rendering.chart_utils import plotly_to_html

    return plotly_to_html(fig)


def _fmt_range_avg(series: pd.Series, unit: str = "", decimals: int = 1) -> str:
    """Return 'X – Y (avg Z unit)' for a numeric series, or '—' if empty."""
    valid = series.dropna()
    if valid.empty:
        return "—"
    fmt = f".{decimals}f"
    u = f" {unit}" if unit else ""
    return f"{valid.min():{fmt}} – {valid.max():{fmt}}{u} (avg {valid.mean():{fmt}}{u})"


def _summary_stats_table(df: pd.DataFrame) -> str:
    """Render a summary card styled like the Metadata section."""
    n_pcs = str(int(df["pc_hid"].nunique())) if "pc_hid" in df.columns else "—"
    n_npcs = str(int(df["npc_hid"].nunique())) if "npc_hid" in df.columns else "—"

    turns_str = _fmt_range_avg(df["turns_completed"]) if "turns_completed" in df.columns else "—"
    dur_str = _fmt_range_avg(df["duration_minutes"], unit="min") if "duration_minutes" in df.columns else "—"
    spp_str = _fmt_range_avg(df.groupby("player_id").size()) if "player_id" in df.columns else "—"

    rows = [
        ("PC Characters Used", n_pcs),
        ("NPC Characters Used", n_npcs),
        ("Turns / Session", turns_str),
        ("Duration / Session", dur_str),
        ("Sessions / Player", spp_str),
    ]

    dl_items = "".join(f"<dt class='col-sm-4'>{label}</dt><dd class='col-sm-8'>{value}</dd>" for label, value in rows)
    return (
        '<h3 class="h5 mb-2">Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{dl_items}</dl>'
        "</div></div>"
    )
