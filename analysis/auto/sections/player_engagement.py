"""Section 4 — Player Engagement.

Three Plotly charts:
  - Runs per player (bar)
  - Engagement by consent_to_followup (grouped bar)
  - Engagement by prior_experience if available (grouped bar)
"""



import pandas as pd

from analysis.auto.constants import chart_caption, section_intro
from analysis.auto.rendering.chart_utils import plotly_to_html
from analysis.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    if data.runs_df.empty:
        return '<div class="alert alert-info">No run data found.</div>'

    # Build per-player run counts joined with player attributes
    run_counts = (
        data.runs_df.groupby("player_id")
        .size()
        .reset_index(name="runs")
    )

    parts: list[str] = [section_intro("player_engagement")]

    def _row(*divs: str) -> str:
        cols = "".join(f'<div class="col-md-6 chart-container">{d}</div>' for d in divs)
        return f'<div class="row">{cols}</div>'

    # Chart 1: runs per player
    parts.append(_row(
        _runs_per_player(run_counts) + chart_caption("player_engagement", "runs_per_player"),
        _engagement_by(run_counts, data.players_df, "consent_to_followup") + chart_caption("player_engagement", "engagement_by_consent"),
    ))

    # Chart 3: prior_experience (only if the column exists)
    if not data.players_df.empty and "prior_experience" in data.players_df.columns:
        parts.append(_row(
            _engagement_by(run_counts, data.players_df, "prior_experience") + chart_caption("player_engagement", "engagement_by_experience"),
        ))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Individual charts
# ---------------------------------------------------------------------------

def _runs_per_player(run_counts: pd.DataFrame) -> str:
    import plotly.express as px

    df = run_counts.sort_values("runs", ascending=False)
    fig = px.bar(
        df,
        x="player_id",
        y="runs",
        title="Runs per Player",
        labels={"player_id": "Player ID", "runs": "Run Count"},
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=60))
    return plotly_to_html(fig)


def _engagement_by(
    run_counts: pd.DataFrame,
    players_df: pd.DataFrame,
    column: str,
) -> str:
    import plotly.express as px

    if players_df.empty or column not in players_df.columns:
        return (
            f'<div class="alert alert-secondary">'
            f'Column <code>{column}</code> not available in player data.</div>'
        )
    if "access_key" not in players_df.columns:
        return '<div class="alert alert-secondary">Player access_key not available.</div>'

    merged = run_counts.merge(
        players_df[["access_key", column]].rename(columns={"access_key": "player_id"}),
        on="player_id",
        how="left",
    )

    # Normalise the grouping column: lists → pipe-joined string, NaN → "Missing"
    def _normalise(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "Missing"
        if isinstance(v, list):
            return "; ".join(str(x) for x in v)
        s = str(v).strip()
        return s if s else "Blank"

    merged[column] = merged[column].apply(_normalise)

    grouped = (
        merged.groupby(column)["runs"]
        .sum()
        .reset_index()
        .sort_values("runs", ascending=False)
    )

    title = "Engagement by " + column.replace("_", " ").title()
    fig = px.bar(
        grouped,
        x=column,
        y="runs",
        title=title,
        labels={column: column.replace("_", " ").title(), "runs": "Run Count"},
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=80))
    return plotly_to_html(fig)
