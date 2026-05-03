"""Section — Player Feedback.

Renders:
1. Flag distribution chart — how often each flag type fires per turn.
2. In-play feedback — inline thumbs/flags/comments on NPC messages, with transcript context.
3. Player feedback patterns — per-player segmentation by feedback behaviour.
"""

import pandas as pd
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.chart_utils import plotly_to_html
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

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
    "session_id": "Session",
    "game_name": "Game",
    "player_id": "Player",
    "turn_index": "Turn",
    "liked": "Liked",
    "flags": "Flags",
    "comment": "Comment",
    "context": "Transcript Context",
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

    has_content = "content" in transcripts_df.columns
    has_turn = "turn_index" in transcripts_df.columns
    has_session = "session_id" in transcripts_df.columns

    if not (has_content and has_turn and has_session):
        return edf

    # Pre-index transcripts by session_id for efficiency
    by_session = {sid: grp.sort_values("turn_index") for sid, grp in transcripts_df.groupby("session_id")}

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
        window = session_events[(session_events["turn_index"] >= ti - _CONTEXT_TURNS) & (session_events["turn_index"] <= ti)]

        lines = []
        for _, evt in window.iterrows():
            # Use event_source if available (e.g. "user"/"npc"), else event_type, else "?"
            source = str(evt.get("event_source") or "").strip() or str(evt.get("event_type") or "").strip() or "?"
            content = str(evt.get("content") or "").strip()
            t = int(evt["turn_index"]) if pd.notna(evt["turn_index"]) else "?"
            lines.append(f"[{source} T{t}]: {content}")

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
    any_flag = pd.concat([flagged[col].fillna(False).astype(bool) for col, _ in available], axis=1).any(axis=1)
    if not any_flag.any():
        return ""

    import plotly.graph_objects as go

    fig = go.Figure()
    colors = ["#e45f3c", "#3c8ee4", "#8e44ad"]

    for (col, label), color in zip(available, colors):
        counts = flagged[flagged[col].fillna(False).astype(bool)].groupby("turn_index").size().reset_index(name="count")
        if counts.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=counts["turn_index"],
                y=counts["count"],
                name=label,
                marker_color=color,
            )
        )

    fig.update_layout(
        barmode="group",
        xaxis_title="Turn",
        yaxis_title="Flag count",
        legend_title="Flag type",
        margin={"t": 30, "b": 40, "l": 50, "r": 20},
        height=320,
    )

    return plotly_to_html(fig, div_id="flags-over-turns")


_FLAG_LABELS = [label for _, label in _FLAG_COLS]
_FLAG_COLORS = ["#e45f3c", "#3c8ee4", "#8e44ad"]


def _parse_flag_cols(edf: pd.DataFrame) -> pd.DataFrame:
    """Add a boolean column per flag type by parsing the comma-separated flags string."""
    edf = edf.copy()
    for label in _FLAG_LABELS:
        edf[label] = edf["flags"].fillna("").str.contains(label, regex=False)
    return edf


def _flags_over_turns_by_game(edf: pd.DataFrame) -> str:
    """Return a Plotly faceted bar chart of flag counts by turn, split by game."""
    if edf.empty or "game_name" not in edf.columns or "flags" not in edf.columns:
        return ""

    flagged = edf[edf["flags"].fillna("") != ""].copy()
    if flagged.empty or "turn_index" not in flagged.columns:
        return ""

    flagged = _parse_flag_cols(flagged)

    games = sorted(flagged["game_name"].dropna().unique())
    if not games:
        return ""

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    n = len(games)
    fig = make_subplots(
        rows=1,
        cols=n,
        shared_yaxes=True,
        subplot_titles=[str(g) for g in games],
    )

    for col_idx, game in enumerate(games, start=1):
        subset = flagged[flagged["game_name"] == game]
        for trace_idx, (label, color) in enumerate(zip(_FLAG_LABELS, _FLAG_COLORS)):
            counts = subset[subset[label]].groupby("turn_index").size().reset_index(name="count")
            fig.add_trace(
                go.Bar(
                    x=counts["turn_index"],
                    y=counts["count"],
                    name=label,
                    marker_color=color,
                    legendgroup=label,
                    showlegend=(col_idx == 1),
                ),
                row=1,
                col=col_idx,
            )

    fig.update_layout(
        barmode="group",
        legend_title="Flag type",
        margin={"t": 50, "b": 40, "l": 50, "r": 20},
        height=350,
    )
    fig.update_xaxes(title_text="Turn")
    fig.update_yaxes(title_text="Flag count", col=1)

    return plotly_to_html(fig, div_id="flags-over-turns-by-game")


def _flags_over_turns_by_player(edf: pd.DataFrame) -> str:
    """Return a Plotly bar chart of flag counts by turn with a per-player dropdown."""
    if edf.empty or "player_id" not in edf.columns or "flags" not in edf.columns:
        return ""

    flagged = edf[edf["flags"].fillna("") != ""].copy()
    if flagged.empty or "turn_index" not in flagged.columns:
        return ""

    flagged = _parse_flag_cols(flagged)

    players = sorted(flagged["player_id"].dropna().astype(str).unique())
    if not players:
        return ""

    import plotly.graph_objects as go

    fig = go.Figure()
    n_flag_types = len(_FLAG_LABELS)

    for p_idx, player in enumerate(players):
        subset = flagged[flagged["player_id"].astype(str) == player]
        for label, color in zip(_FLAG_LABELS, _FLAG_COLORS):
            counts = subset[subset[label]].groupby("turn_index").size().reset_index(name="count")
            fig.add_trace(
                go.Bar(
                    x=counts["turn_index"],
                    y=counts["count"],
                    name=label,
                    marker_color=color,
                    legendgroup=label,
                    showlegend=(p_idx == 0),
                    visible=(p_idx == 0),
                )
            )

    # Build dropdown: each button makes only the selected player's traces visible
    buttons = []
    for p_idx, player in enumerate(players):
        visible = [(i // n_flag_types == p_idx) for i in range(len(players) * n_flag_types)]
        buttons.append(
            dict(
                label=str(player),
                method="update",
                args=[
                    {"visible": visible},
                    {"title": ""},
                ],
            )
        )

    fig.update_layout(
        updatemenus=[
            dict(
                buttons=buttons,
                direction="down",
                x=0.0,
                xanchor="left",
                y=1.15,
                yanchor="top",
                showactive=True,
            )
        ],
        annotations=[
            dict(
                text="Select Player:",
                x=0.0,
                xanchor="right",
                xref="paper",
                y=1.15,
                yanchor="top",
                yref="paper",
                showarrow=False,
            )
        ],
        barmode="group",
        xaxis_title="Turn",
        yaxis_title="Flag count",
        legend_title="Flag type",
        margin={"t": 60, "b": 40, "l": 50, "r": 20},
        height=350,
    )

    return plotly_to_html(fig, div_id="flags-over-turns-by-player")


def _player_segments_table(edf: pd.DataFrame) -> str:
    """Return a DataTable HTML of per-player feedback segments, or '' if no data."""
    if edf.empty or "player_id" not in edf.columns:
        return ""

    agg = (
        edf.groupby("player_id")
        .apply(
            lambda g: pd.Series(
                {
                    "total": len(g),
                    "positive": int((g["liked"] == True).sum()) if "liked" in g.columns else 0,  # noqa: E712
                    "negative": int((g["liked"] == False).sum()) if "liked" in g.columns else 0,  # noqa: E712
                    "commented": int((g["comment"].fillna("").str.len() > 0).sum()) if "comment" in g.columns else 0,
                    "flags_count": int((g["flags"].fillna("") != "").sum()) if "flags" in g.columns else 0,
                }
            )
        )
        .reset_index()
    )

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
            "player_id": "Player",
            "total": "Total",
            "positive": "Positive",
            "negative": "Negative",
            "commented": "w/ Comment",
            "flags_count": "Flagged",
            "segment": "Segment",
        },
        scroll_y="",
        export_buttons=True,
    )


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "—"
    return f"{numerator} / {denominator} ({numerator / denominator:.0%})"


def _feedback_summary_card(edf: pd.DataFrame, transcripts_df: pd.DataFrame) -> str:
    """Return a titled Bootstrap card summarising key feedback proportion metrics."""
    total_fb = len(edf) if not edf.empty else 0
    positive = int((edf["liked"] == True).sum()) if not edf.empty and "liked" in edf.columns else 0  # noqa: E712
    negative = int((edf["liked"] == False).sum()) if not edf.empty and "liked" in edf.columns else 0  # noqa: E712

    # Total NPC turns across all sessions — denominator for ICF / flag rates
    if not transcripts_df.empty and "event_source" in transcripts_df.columns:
        total_npc_turns = int((transcripts_df["event_source"].fillna("") == "npc").sum())
    else:
        total_npc_turns = 0

    def _row(label: str, value: str) -> str:
        return f"<dt class='col-sm-6'>{label}</dt><dd class='col-sm-6'>{value}</dd>"

    rows = (
        _row("Feedback Rate", _fmt_pct(total_fb, total_npc_turns))
        + _row("👍 Thumbs Up", _fmt_pct(positive, total_fb))
        + _row("👎 Thumbs Down", _fmt_pct(negative, total_fb))
    )

    return (
        '<h3 class="h5 mb-2">Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{rows}</dl>'
        "</div></div>"
    )


def render(data: AnalysisData) -> str:
    parts = [section_intro("player_feedback")]

    edf = data.event_feedback_df
    tdf = data.transcripts_df

    # --- Summary card ---
    parts.append(_feedback_summary_card(edf, tdf))

    # --- Flag distribution over turns ---
    flags_chart = _flags_over_turns_chart(tdf)
    if flags_chart:
        parts.append("<h5>Flag Distribution Over Turns</h5>")
        parts.append(f'<div class="row"><div class="col-12 chart-container">{flags_chart}</div></div>')
        parts.append(chart_caption("player_feedback", "flags_over_turns"))

    # --- Flag distribution by game ---
    by_game_chart = _flags_over_turns_by_game(edf)
    if by_game_chart:
        parts.append("<h5>Flag Distribution Over Turns — by Game</h5>")
        parts.append(f'<div class="row"><div class="col-12 chart-container">{by_game_chart}</div></div>')
        parts.append(chart_caption("player_feedback", "flags_over_turns_by_game"))

    # --- Flag distribution by player ---
    by_player_chart = _flags_over_turns_by_player(edf)
    if by_player_chart:
        parts.append("<h5>Flag Distribution Over Turns — by Player</h5>")
        parts.append(f'<div class="row"><div class="col-12 chart-container">{by_player_chart}</div></div>')
        parts.append(chart_caption("player_feedback", "flags_over_turns_by_player"))

    # --- In-play (per-message) feedback ---
    if not edf.empty:
        edf = _build_context_column(edf, tdf)
        cols = [c for c in _EVENT_COLUMNS if c in edf.columns]
        rename = {k: v for k, v in _EVENT_RENAME.items() if k in cols}
        parts.append("<h5>In-Play Feedback</h5>")
        parts.append(
            df_to_datatable(
                edf,
                table_id="event-feedback-table",
                columns=cols,
                rename=rename,
                truncate_cols=["comment", "context"],
                truncate_at=300,
            )
        )
        parts.append(chart_caption("player_feedback", "inplay_feedback_table"))

    # --- Player feedback patterns ---
    if not edf.empty:
        segments_table = _player_segments_table(edf)
        if segments_table:
            parts.append("<h5>Player Feedback Patterns</h5>")
            parts.append(segments_table)
            parts.append(chart_caption("player_feedback", "player_segments_table"))

    if edf.empty and not _flags_over_turns_chart(tdf):
        return '<div class="alert alert-info">No feedback responses found.</div>'

    return "\n".join(parts)
