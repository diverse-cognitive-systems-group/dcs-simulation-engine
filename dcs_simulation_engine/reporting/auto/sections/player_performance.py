"""Section - Player Performance.

Summarizes scored gameplay sessions by player and game.
"""

import re

import pandas as pd
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.chart_utils import add_short_player_id_column, plotly_to_html, use_integer_ticks
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

_SCORE_COLUMNS = [
    "runtime_state.game_state.score.score",
    "game_state.score.score",
    "score.score",
    "evaluation.score",
    "score",
]

_TIER_COLUMNS = [
    "runtime_state.game_state.score.tier",
    "game_state.score.tier",
    "score.tier",
    "evaluation.tier",
    "tier",
]

_REASONING_COLUMNS = [
    "runtime_state.game_state.score.reasoning",
    "game_state.score.reasoning",
    "score.reasoning",
    "evaluation.reasoning",
    "reasoning",
]

_SESSION_COLUMNS = [
    "session_id",
    "player_id",
    "game_name",
    "pc_hid",
    "npc_hid",
    "score",
    "tier",
    "turns_completed",
    "duration_human",
    "termination_reason",
    "reasoning",
]

_SESSION_RENAME = {
    "session_id": "Session",
    "player_id": "Player",
    "game_name": "Game",
    "pc_hid": "PC",
    "npc_hid": "NPC",
    "score": "Score",
    "tier": "Tier",
    "turns_completed": "Turns",
    "duration_human": "Duration",
    "termination_reason": "Exit Reason",
    "reasoning": "Reasoning",
}


def render(data: AnalysisData) -> str:
    scores = _score_frame(data)
    if scores.empty:
        return section_intro("player_performance") + (
            '<div class="alert alert-secondary mb-0">'
            "No scored gameplay sessions found. Scored games persist scores in session runtime state or final score events."
            "</div>"
        )

    parts = [section_intro("player_performance")]
    parts.append(_summary_card(scores))

    def _row(*divs: str) -> str:
        cols = "".join(f'<div class="col-md-6 chart-container">{d}</div>' for d in divs)
        return f'<div class="row">{cols}</div>'

    parts.append(
        _row(
            _score_by_game(scores) + chart_caption("player_performance", "score_by_game"),
            _score_by_player(scores) + chart_caption("player_performance", "score_by_player"),
        )
    )
    parts.append(
        _row(
            _score_distribution(scores) + chart_caption("player_performance", "score_distribution"),
            _score_vs_turns(scores) + chart_caption("player_performance", "score_vs_turns"),
        )
    )

    parts.append('<h3 class="h5 mt-4 mb-2">Player by Game Summary</h3>')
    parts.append(_player_game_table(scores))
    parts.append(chart_caption("player_performance", "player_game_table"))

    parts.append('<h3 class="h5 mt-4 mb-2">Scored Sessions</h3>')
    parts.append(_scored_sessions_table(scores))
    parts.append(chart_caption("player_performance", "scored_sessions_table"))

    return "\n".join(parts)


def _score_frame(data: AnalysisData) -> pd.DataFrame:
    runtime_scores = _runtime_score_frame(data)
    event_scores = _score_event_frame(data)

    if runtime_scores.empty:
        return event_scores
    if event_scores.empty:
        return runtime_scores

    combined = pd.concat([runtime_scores, event_scores], ignore_index=True)
    if "session_id" in combined.columns:
        combined = combined.drop_duplicates("session_id", keep="first")
    return combined.reset_index(drop=True)


def _runtime_score_frame(data: AnalysisData) -> pd.DataFrame:
    df = data.runs_df.copy()
    if df.empty:
        return pd.DataFrame()

    score_col = _first_column(df, _SCORE_COLUMNS)
    if score_col is None:
        return pd.DataFrame()

    result = pd.DataFrame(index=df.index)
    for col in [
        "session_id",
        "player_id",
        "game_name",
        "pc_hid",
        "npc_hid",
        "turns_completed",
        "duration_human",
        "termination_reason",
    ]:
        if col in df.columns:
            result[col] = df[col]

    result["score"] = pd.to_numeric(df[score_col], errors="coerce")
    result = result[result["score"].notna()].copy()
    if result.empty:
        return pd.DataFrame()

    tier_col = _first_column(df, _TIER_COLUMNS)
    if tier_col is not None:
        result["tier"] = pd.to_numeric(df.loc[result.index, tier_col], errors="coerce")

    reasoning_col = _first_column(df, _REASONING_COLUMNS)
    if reasoning_col is not None:
        result["reasoning"] = df.loc[result.index, reasoning_col].fillna("").astype(str)

    if "player_id" not in result.columns:
        result["player_id"] = "unknown"
    result["player_id"] = result["player_id"].fillna("unknown").astype(str)

    if "game_name" not in result.columns:
        result["game_name"] = "unknown"
    result["game_name"] = result["game_name"].fillna("unknown").astype(str)

    if "session_id" in result.columns:
        result = result.sort_values(["player_id", "game_name", "session_id"])

    return result.reset_index(drop=True)


def _score_event_frame(data: AnalysisData) -> pd.DataFrame:
    events = data.transcripts_df.copy()
    if events.empty or "content" not in events.columns:
        return pd.DataFrame()

    content = events["content"].fillna("").astype(str)
    score_events = events[content.str.contains(r"(?m)^-\s*Score:", regex=True)].copy()
    if score_events.empty:
        return pd.DataFrame()

    parsed = score_events["content"].fillna("").astype(str).apply(_parse_score_markdown)
    parsed_df = pd.DataFrame(parsed.tolist(), index=score_events.index)
    for col in ["score", "tier", "reasoning"]:
        score_events[col] = parsed_df[col]
    score_events = score_events[score_events["score"].notna()].copy()
    if score_events.empty:
        return pd.DataFrame()

    if "event_ts" in score_events.columns:
        score_events = score_events.sort_values("event_ts")
    if "session_id" in score_events.columns:
        score_events = score_events.drop_duplicates("session_id", keep="last")

    result_cols = [c for c in ["session_id", "score", "tier", "reasoning"] if c in score_events.columns]
    result = score_events[result_cols].copy()

    if not data.runs_df.empty and "session_id" in result.columns and "session_id" in data.runs_df.columns:
        meta_cols = [
            c
            for c in [
                "session_id",
                "player_id",
                "game_name",
                "pc_hid",
                "npc_hid",
                "turns_completed",
                "duration_human",
                "termination_reason",
            ]
            if c in data.runs_df.columns
        ]
        result = result.merge(data.runs_df[meta_cols].drop_duplicates("session_id"), on="session_id", how="left")

    if "player_id" not in result.columns:
        result["player_id"] = "unknown"
    result["player_id"] = result["player_id"].fillna("unknown").astype(str)

    if "game_name" not in result.columns:
        result["game_name"] = "unknown"
    result["game_name"] = result["game_name"].fillna("unknown").astype(str)

    result["score"] = pd.to_numeric(result["score"], errors="coerce")
    if "tier" in result.columns:
        result["tier"] = pd.to_numeric(result["tier"], errors="coerce")
    result = result[result["score"].notna()].copy()
    if result.empty:
        return pd.DataFrame()

    if "session_id" in result.columns:
        result = result.sort_values(["player_id", "game_name", "session_id"])
    return result.reset_index(drop=True)


def _parse_score_markdown(content: str) -> dict:
    score_match = re.search(r"(?im)^-\s*Score:\s*([+-]?\d+(?:\.\d+)?)\s*$", content)
    tier_match = re.search(r"(?im)^-\s*Tier:\s*([+-]?\d+(?:\.\d+)?)\s*$", content)
    reasoning_match = re.search(r"(?ims)^###\s*Reasoning\s*(.*)$", content)
    return {
        "score": float(score_match.group(1)) if score_match else pd.NA,
        "tier": float(tier_match.group(1)) if tier_match else pd.NA,
        "reasoning": reasoning_match.group(1).strip() if reasoning_match else "",
    }


def _first_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _summary_card(scores: pd.DataFrame) -> str:
    rows = [
        ("Scored Sessions", str(len(scores))),
        ("Scored Players", str(scores["player_id"].nunique())),
        ("Scored Games", str(scores["game_name"].nunique())),
        ("Average Score", f"{scores['score'].mean():.1f}"),
        ("Median Score", f"{scores['score'].median():.1f}"),
    ]
    dl_items = "".join(f"<dt class='col-sm-4'>{label}</dt><dd class='col-sm-8'>{value}</dd>" for label, value in rows)
    return (
        '<h3 class="h5 mb-2">Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{dl_items}</dl>'
        "</div></div>"
    )


def _score_by_game(scores: pd.DataFrame) -> str:
    import plotly.express as px

    grouped = _aggregate_scores(scores, ["game_name"]).sort_values("mean_score", ascending=True)
    fig = px.bar(
        grouped,
        x="mean_score",
        y="game_name",
        orientation="h",
        title="Average Score by Game",
        labels={"game_name": "Game", "mean_score": "Average Score", "sessions": "Scored Sessions"},
        hover_data=["sessions", "median_score", "min_score", "max_score"],
    )
    fig.update_layout(height=max(300, 70 + len(grouped) * 35), margin=dict(l=20, r=20, t=40, b=40))
    return plotly_to_html(fig)


def _score_by_player(scores: pd.DataFrame) -> str:
    import plotly.express as px

    grouped = add_short_player_id_column(_aggregate_scores(scores, ["player_id"]).sort_values("mean_score", ascending=True))
    grouped = grouped[["player_label", "mean_score", "sessions", "median_score", "min_score", "max_score"]]
    fig = px.bar(
        grouped,
        x="mean_score",
        y="player_label",
        orientation="h",
        title="Average Score by Player",
        labels={"player_label": "Player", "mean_score": "Average Score", "sessions": "Scored Sessions"},
        hover_data={"player_label": True, "sessions": True, "median_score": True, "min_score": True, "max_score": True},
    )
    fig.update_layout(height=max(300, 70 + len(grouped) * 30), margin=dict(l=20, r=20, t=40, b=40))
    return plotly_to_html(fig)


def _score_distribution(scores: pd.DataFrame) -> str:
    import plotly.express as px

    fig = px.histogram(
        scores,
        x="score",
        nbins=20,
        title="Score Distribution",
        labels={"score": "Score", "count": "Scored Sessions"},
    )
    use_integer_ticks(fig, y=True)
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=40), showlegend=False)
    return plotly_to_html(fig)


def _score_vs_turns(scores: pd.DataFrame) -> str:
    import plotly.express as px

    if "turns_completed" not in scores.columns:
        return '<div class="alert alert-secondary">Turn count data is unavailable for scored sessions.</div>'

    valid = add_short_player_id_column(scores.dropna(subset=["turns_completed"]))
    chart_cols = [c for c in ["player_label", "session_id", "pc_hid", "npc_hid", "turns_completed", "score", "game_name"] if c in valid.columns]
    valid = valid[chart_cols]
    if valid.empty:
        return '<div class="alert alert-secondary">Turn count data is unavailable for scored sessions.</div>'

    fig = px.scatter(
        valid,
        x="turns_completed",
        y="score",
        color="game_name",
        title="Score vs. Turns Completed",
        labels={"turns_completed": "Turns Completed", "score": "Score", "game_name": "Game"},
        hover_data=[c for c in ["player_label", "session_id", "pc_hid", "npc_hid"] if c in valid.columns],
    )
    use_integer_ticks(fig, x=True)
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=40, b=40))
    return plotly_to_html(fig)


def _player_game_table(scores: pd.DataFrame) -> str:
    grouped = _aggregate_scores(scores, ["player_id", "game_name"]).sort_values(["player_id", "game_name"])
    return df_to_datatable(
        grouped,
        table_id="player-game-performance-table",
        columns=["player_id", "game_name", "sessions", "mean_score", "median_score", "min_score", "max_score"],
        rename={
            "player_id": "Player",
            "game_name": "Game",
            "sessions": "Scored Sessions",
            "mean_score": "Average Score",
            "median_score": "Median Score",
            "min_score": "Min Score",
            "max_score": "Max Score",
        },
        scroll_y="",
        export_buttons=True,
    )


def _scored_sessions_table(scores: pd.DataFrame) -> str:
    cols = [c for c in _SESSION_COLUMNS if c in scores.columns]
    return df_to_datatable(
        scores,
        table_id="scored-sessions-table",
        columns=cols,
        rename={k: v for k, v in _SESSION_RENAME.items() if k in cols},
        scroll_y="",
        export_buttons=True,
    )


def _aggregate_scores(scores: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    grouped = (
        scores.groupby(by, dropna=False)["score"]
        .agg(sessions="count", mean_score="mean", median_score="median", min_score="min", max_score="max")
        .reset_index()
    )
    for col in ["mean_score", "median_score", "min_score", "max_score"]:
        grouped[col] = grouped[col].round(1)
    return grouped
