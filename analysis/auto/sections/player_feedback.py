"""Section 5 — Player Feedback.

Renders three sub-sections:
1. Flag distribution chart — how often each flag type fires per turn.
2. In-play feedback — inline thumbs/flags/comments on NPC messages, with transcript context.
3. Player feedback patterns — per-player segmentation by feedback behaviour.
4. Form responses — flattened assignment form answers (pre/post-game surveys).
"""

from __future__ import annotations

import pandas as pd

from analysis.auto.constants import chart_caption, section_intro
from analysis.auto.rendering.chart_utils import plotly_to_html
from analysis.auto.rendering.table_utils import df_to_datatable
from analysis.common.loader import AnalysisData

_FORM_COLUMNS = [
    "player_id",
    "game_name",
    "form_name",
    "before_or_after",
    "question_key",
    "question_prompt",
    "answer_type",
    "answer",
    "submitted_at",
]

_FORM_RENAME = {
    "player_id":       "Player",
    "game_name":       "Game",
    "form_name":       "Form",
    "before_or_after": "When",
    "question_key":    "Question Key",
    "question_prompt": "Question",
    "answer_type":     "Type",
    "answer":          "Answer",
    "submitted_at":    "Submitted At",
}

_EVENT_COLUMNS = [
    "session_id",
    "game_name",
    "player_id",
    "turn_index",
    "liked",
    "flags",
    "comment",
    "context",
    "submitted_at",
]

_EVENT_RENAME = {
    "session_id":   "Session",
    "game_name":    "Game",
    "player_id":    "Player",
    "turn_index":   "Turn",
    "liked":        "Liked",
    "flags":        "Flags",
    "comment":      "Comment",
    "context":      "Transcript Context",
    "submitted_at": "Submitted At",
}

_CONTEXT_TURNS = 3

# Flag columns in transcripts_df (dot-separated from json_normalize)
_FLAG_COLS = [
    ("feedback.out_of_character", "out of character"),
    ("feedback.doesnt_make_sense", "doesn't make sense"),
    ("feedback.other", "other"),
]


def _build_context_column(edf: pd.DataFrame, transcripts_df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'context' column to edf with the preceding turns from transcripts."""
    edf = edf.copy()
    edf["context"] = ""

    if transcripts_df.empty:
        return edf

    has_role = "role" in transcripts_df.columns
    has_content = "content" in transcripts_df.columns
    has_turn = "turn_index" in transcripts_df.columns
    has_session = "session_id" in transcripts_df.columns

    if not (has_role and has_content and has_turn and has_session):
        return edf

    # Pre-index transcripts by session_id for efficiency
    by_session = {
        sid: grp.sort_values("turn_index")
        for sid, grp in transcripts_df.groupby("session_id")
    }

    contexts = []
    for _, row in edf.iterrows():
        sid = row.get("session_id")
        ti = row.get("turn_index")
        if sid is None or pd.isna(ti):
            contexts.append("")
            continue

        session_events = by_session.get(sid)
        if session_events is None or session_events.empty:
            contexts.append("")
            continue

        ti = int(ti)
        window = session_events[
            (session_events["turn_index"] >= ti - _CONTEXT_TURNS) &
            (session_events["turn_index"] <= ti)
        ]

        lines = []
        for _, evt in window.iterrows():
            role = str(evt.get("role") or "").strip() or "?"
            content = str(evt.get("content") or "").strip()
            t = int(evt["turn_index"]) if pd.notna(evt["turn_index"]) else "?"
            lines.append(f"[{role} T{t}]: {content}")

        contexts.append("\n".join(lines))

    edf["context"] = contexts
    return edf


def _flags_over_turns_chart(transcripts_df: pd.DataFrame) -> str:
    """Return a Plotly grouped bar chart of flag counts by turn, or '' if no data."""
    if transcripts_df.empty:
        return ""

    available = [(col, label) for col, label in _FLAG_COLS if col in transcripts_df.columns]
    if not available:
        return ""

    has_turn = "turn_index" in transcripts_df.columns
    if not has_turn:
        return ""

    # Only consider disliked (flagged) events
    mask = pd.Series([True] * len(transcripts_df), index=transcripts_df.index)
    if "feedback.liked" in transcripts_df.columns:
        mask = transcripts_df["feedback.liked"] == False  # noqa: E712

    flagged = transcripts_df[mask].copy()
    if flagged.empty:
        return ""

    # Check at least one flag is actually set
    any_flag = pd.concat(
        [flagged[col].fillna(False).astype(bool) for col, _ in available], axis=1
    ).any(axis=1)
    if not any_flag.any():
        return ""

    import plotly.graph_objects as go

    fig = go.Figure()
    colors = ["#e45f3c", "#3c8ee4", "#8e44ad"]

    for (col, label), color in zip(available, colors):
        counts = (
            flagged[flagged[col].fillna(False).astype(bool)]
            .groupby("turn_index")
            .size()
            .reset_index(name="count")
        )
        if counts.empty:
            continue
        fig.add_trace(go.Bar(
            x=counts["turn_index"],
            y=counts["count"],
            name=label,
            marker_color=color,
        ))

    fig.update_layout(
        barmode="group",
        xaxis_title="Turn",
        yaxis_title="Flag count",
        legend_title="Flag type",
        margin={"t": 30, "b": 40, "l": 50, "r": 20},
        height=320,
    )

    return plotly_to_html(fig, div_id="flags-over-turns")


def _player_segments_table(edf: pd.DataFrame) -> str:
    """Return a DataTable HTML of per-player feedback segments, or '' if no data."""
    if edf.empty or "player_id" not in edf.columns:
        return ""

    liked_col = edf["liked"] if "liked" in edf.columns else pd.Series(dtype=object)
    comment_col = edf["comment"].fillna("") if "comment" in edf.columns else pd.Series("", index=edf.index)
    flags_col = edf["flags"].fillna("") if "flags" in edf.columns else pd.Series("", index=edf.index)

    agg = edf.groupby("player_id").apply(lambda g: pd.Series({
        "total":       len(g),
        "positive":    int((g["liked"] == True).sum()) if "liked" in g.columns else 0,  # noqa: E712
        "negative":    int((g["liked"] == False).sum()) if "liked" in g.columns else 0,  # noqa: E712
        "commented":   int((g["comment"].fillna("").str.len() > 0).sum()) if "comment" in g.columns else 0,
        "flags_count": int((g["flags"].fillna("") != "").sum()) if "flags" in g.columns else 0,
    })).reset_index()

    if agg.empty:
        return ""

    high_thresh = agg["total"].quantile(0.75)
    low_thresh = agg["total"].quantile(0.25)

    def _segment(row):
        if row["negative"] == 0 and row["positive"] > 0:
            return "only positive"
        if row["positive"] == 0 and row["negative"] > 0:
            return "only negative"
        if row["total"] >= high_thresh:
            return "high feedback"
        if row["total"] <= low_thresh:
            return "low feedback"
        return "mixed"

    agg["segment"] = agg.apply(_segment, axis=1)
    agg = agg.sort_values("total", ascending=False).reset_index(drop=True)

    return df_to_datatable(
        agg,
        table_id="player-segments-table",
        columns=["player_id", "total", "positive", "negative", "commented", "flags_count", "segment"],
        rename={
            "player_id":    "Player",
            "total":        "Total",
            "positive":     "Positive",
            "negative":     "Negative",
            "commented":    "w/ Comment",
            "flags_count":  "Flagged",
            "segment":      "Segment",
        },
        scroll_y="",
        export_buttons=True,
    )


def render(data: AnalysisData) -> str:
    parts = [section_intro("player_feedback")]

    edf = data.event_feedback_df
    tdf = data.transcripts_df

    # --- Flag distribution over turns ---
    flags_chart = _flags_over_turns_chart(tdf)
    if flags_chart:
        parts.append("<h5>Flag Distribution Over Turns</h5>")
        parts.append(f'<div class="row"><div class="col-12 chart-container">{flags_chart}</div></div>')
        parts.append(chart_caption("player_feedback", "flags_over_turns"))

    # --- In-play (per-message) feedback ---
    if not edf.empty:
        edf = _build_context_column(edf, tdf)
        cols = [c for c in _EVENT_COLUMNS if c in edf.columns]
        rename = {k: v for k, v in _EVENT_RENAME.items() if k in cols}
        parts.append("<h5>In-Play Feedback</h5>")
        parts.append(df_to_datatable(
            edf,
            table_id="event-feedback-table",
            columns=cols,
            rename=rename,
            truncate_cols=["comment", "context"],
            truncate_at=300,
        ))
        parts.append(chart_caption("player_feedback", "inplay_feedback_table"))

    # --- Player feedback patterns ---
    if not edf.empty:
        segments_table = _player_segments_table(edf)
        if segments_table:
            parts.append("<h5>Player Feedback Patterns</h5>")
            parts.append(segments_table)
            parts.append(chart_caption("player_feedback", "player_segments_table"))

    # --- Form-based (survey) feedback ---
    fdf = data.feedback_df
    if not fdf.empty:
        cols = [c for c in _FORM_COLUMNS if c in fdf.columns]
        rename = {k: v for k, v in _FORM_RENAME.items() if k in cols}
        parts.append("<h5>Form Responses</h5>")
        parts.append(df_to_datatable(
            fdf,
            table_id="feedback-table",
            columns=cols,
            rename=rename,
            truncate_cols=["answer", "question_prompt"],
            truncate_at=300,
        ))
        parts.append(chart_caption("player_feedback", "form_responses_table"))

    if len(parts) <= 1:
        return '<div class="alert alert-info">No feedback responses found.</div>'

    return "\n".join(parts)
