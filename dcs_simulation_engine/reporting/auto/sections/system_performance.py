"""Section 3 — System Performance.

Plotly charts covering run durations, pacing, exit reasons,
retry budget, PC/NPC pairings, and a session timeline (Gantt), followed by
system error details.
"""

from datetime import timezone

import numpy as np
import pandas as pd
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.chart_utils import plotly_to_html
from dcs_simulation_engine.reporting.auto.sections import system_errors
from dcs_simulation_engine.reporting.loader import AnalysisData


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
        parts.append(section_intro("system_performance"))
        parts.append(
            _row(
                _exit_reasons(df) + chart_caption("system_performance", "exit_reasons"),
                _duration_histogram(df) + chart_caption("system_performance", "duration_distribution"),
            )
        )
        parts.append(
            _row(
                _duration_by_game(df) + chart_caption("system_performance", "duration_by_game"),
                _turns_vs_runtime(df) + chart_caption("system_performance", "turns_vs_runtime"),
            )
        )
        parts.append(
            _row(
                _retry_budget(df) + chart_caption("system_performance", "retry_budget"),
            )
        )
        parts.append(_full(_session_timeline(df) + chart_caption("system_performance", "session_timeline")))

    # --- Load-test-style performance charts derived from session data ---
    game_lt = _build_game_df(data.runs_df)
    wait_lt = _build_wait_df(data.transcripts_df, data.runs_df)
    wait_turn = wait_lt[wait_lt["phase"] == "turn"] if not wait_lt.empty else wait_lt
    wait_opening = wait_lt[wait_lt["phase"] == "opening"] if not wait_lt.empty else wait_lt
    wait_close = wait_lt[wait_lt["phase"] == "close"] if not wait_lt.empty else wait_lt

    parts.append('<h3 class="h5 mt-4 mb-3">Response Time Analysis</h3>')
    parts.append(
        _row(
            _lt_violin_game_by_player(game_lt) + chart_caption("system_performance", "lt_game_duration_by_player"),
            _lt_violin_wait_by_player(wait_turn) + chart_caption("system_performance", "lt_wait_by_player"),
        )
    )
    parts.append(_full(_lt_violin_wait_by_player_and_game(wait_turn) + chart_caption("system_performance", "lt_wait_by_player_and_game")))
    if not game_lt.empty:
        parts.append(
            _full(
                _lt_hist_kde(game_lt["game_duration_ms"], "Game Duration Distribution (All Players)", "Duration (ms)")
                + chart_caption("system_performance", "lt_hist_game_duration")
            )
        )
    if not wait_turn.empty:
        parts.append(
            _full(
                _lt_hist_kde(wait_turn["wait_response_duration_ms"], "Wait Response Distribution — Turn Phase", "Duration (ms)")
                + chart_caption("system_performance", "lt_hist_wait_turn")
            )
        )
    if not wait_opening.empty:
        parts.append(
            _full(
                _lt_hist_kde(wait_opening["wait_response_duration_ms"], "Wait Response Distribution — Opening Phase", "Duration (ms)")
                + chart_caption("system_performance", "lt_hist_wait_opening")
            )
        )
    if not wait_close.empty:
        parts.append(
            _full(
                _lt_hist_kde(wait_close["wait_response_duration_ms"], "Wait Response Distribution — Close Phase", "Duration (ms)")
                + chart_caption("system_performance", "lt_hist_wait_close")
            )
        )

    parts.append('<h3 class="h5 mt-4">System Errors</h3>')
    parts.append(system_errors.render(data))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Individual charts
# ---------------------------------------------------------------------------


def _pairing_heatmap(df: pd.DataFrame) -> str:
    games = df["game_name"].dropna().unique() if "game_name" in df.columns else []

    if len(games) <= 1 or "pc_hid" not in df.columns or "npc_hid" not in df.columns:
        return _single_heatmap(df, title="PC / NPC Pairing Heatmap")

    tab_nav = []
    tab_content = []
    for i, game in enumerate(sorted(games)):
        slug = game.replace(" ", "-").lower()
        active_nav = "active" if i == 0 else ""
        active_pane = "show active" if i == 0 else ""
        tab_nav.append(f'<li class="nav-item"><a class="nav-link {active_nav}" data-bs-toggle="tab" href="#hm-{slug}">{game}</a></li>')
        chart_html = _single_heatmap(df[df["game_name"] == game], title=game)
        tab_content.append(f'<div class="tab-pane fade {active_pane}" id="hm-{slug}">{chart_html}</div>')

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
        df.groupby(["pc_hid", "npc_hid"]).size().reset_index(name="runs").pivot(index="pc_hid", columns="npc_hid", values="runs").fillna(0)
    )
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="Blues",
            text=pivot.values.astype(int),
            texttemplate="%{text}",
            hovertemplate="PC: %{y}<br>NPC: %{x}<br>Runs: %{z}<extra></extra>",
        )
    )
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


# ---------------------------------------------------------------------------
# Response-time analysis — data prep
# ---------------------------------------------------------------------------


def _build_game_df(runs_df: pd.DataFrame) -> pd.DataFrame:
    """Build a per-session DataFrame with game_duration_ms and sequential game_number per player."""
    needed = {"player_id", "duration_minutes", "session_started_at"}
    if runs_df.empty or not needed.issubset(runs_df.columns):
        return pd.DataFrame()

    df = runs_df.dropna(subset=["player_id", "duration_minutes"]).copy()
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("session_started_at")
    df["game_number"] = df.groupby("player_id").cumcount() + 1
    df["game_label"] = "g" + df["game_number"].astype(str)
    df["game_duration_ms"] = (df["duration_minutes"] * 60_000).round().astype(float)
    return df[["player_id", "game_number", "game_label", "game_duration_ms"]].reset_index(drop=True)


def _build_wait_df(transcripts_df: pd.DataFrame, runs_df: pd.DataFrame) -> pd.DataFrame:
    """Compute wait_response_duration_ms by pairing inbound→outbound message events per session."""
    needed = {"session_id", "event_ts", "seq", "direction", "event_type", "turn_index"}
    if transcripts_df.empty or not needed.issubset(transcripts_df.columns):
        return pd.DataFrame()

    try:
        msgs = (
            transcripts_df[transcripts_df["event_type"] == "message"][["session_id", "seq", "event_ts", "direction", "turn_index"]]
            .dropna(subset=["event_ts"])
            .copy()
        )

        if msgs.empty:
            return pd.DataFrame()

        msgs = msgs.sort_values(["session_id", "seq"]).reset_index(drop=True)

        # Pair each inbound with the next outbound in the same session
        inbound = msgs[msgs["direction"] == "inbound"].reset_index(drop=True)
        outbound = msgs[msgs["direction"] == "outbound"].reset_index(drop=True)

        if inbound.empty or outbound.empty:
            return pd.DataFrame()

        rows = []
        out_idx = 0
        for _, in_row in inbound.iterrows():
            # Advance to the first outbound event in the same session after this inbound seq
            while out_idx < len(outbound):
                o = outbound.iloc[out_idx]
                if o["session_id"] == in_row["session_id"] and o["seq"] > in_row["seq"]:
                    break
                if o["session_id"] != in_row["session_id"] and o["session_id"] > in_row["session_id"]:
                    break
                out_idx += 1
            if out_idx >= len(outbound):
                break
            o = outbound.iloc[out_idx]
            if o["session_id"] != in_row["session_id"] or o["seq"] <= in_row["seq"]:
                continue
            wait_ms = (o["event_ts"] - in_row["event_ts"]).total_seconds() * 1000
            if wait_ms > 0:
                rows.append(
                    {
                        "session_id": in_row["session_id"],
                        "turn_index": in_row["turn_index"],
                        "wait_response_duration_ms": wait_ms,
                    }
                )

        if not rows:
            return pd.DataFrame()

        wait_df = pd.DataFrame(rows)

        # Classify phase per session
        max_turn = msgs.groupby("session_id")["turn_index"].max().rename("max_turn")
        wait_df = wait_df.join(max_turn, on="session_id")
        wait_df["phase"] = "turn"
        wait_df.loc[wait_df["turn_index"] == 0, "phase"] = "opening"
        wait_df.loc[wait_df["turn_index"] == wait_df["max_turn"], "phase"] = "close"
        wait_df = wait_df.drop(columns=["max_turn"])

        # Join player_id and game_number from runs_df
        if not runs_df.empty and "session_id" in runs_df.columns and "player_id" in runs_df.columns:
            runs_sorted = runs_df.dropna(subset=["player_id"]).sort_values("session_started_at")
            runs_sorted["game_number"] = runs_sorted.groupby("player_id").cumcount() + 1
            runs_sorted["game_label"] = "g" + runs_sorted["game_number"].astype(str)
            session_meta = runs_sorted[["session_id", "player_id", "game_number", "game_label"]]
            wait_df = wait_df.merge(session_meta, on="session_id", how="left")

        return wait_df.reset_index(drop=True)

    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Response-time analysis — charts
# ---------------------------------------------------------------------------


def _lt_violin_game_by_player(game_df: pd.DataFrame) -> str:
    import plotly.graph_objects as go

    if game_df.empty:
        return '<div class="alert alert-secondary">No game duration data.</div>'

    fig = go.Figure()
    for player in sorted(game_df["player_id"].unique()):
        sub = game_df[game_df["player_id"] == player]
        fig.add_trace(
            go.Violin(
                x=[str(player)] * len(sub),
                y=sub["game_duration_ms"],
                name=str(player),
                box_visible=True,
                meanline_visible=True,
                points=False,
                showlegend=False,
            )
        )
    fig.update_layout(
        title="Game Duration by Player",
        xaxis_title="Player ID",
        yaxis_title="game_duration_ms",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return plotly_to_html(fig)


def _lt_violin_wait_by_player(wait_df: pd.DataFrame) -> str:
    import plotly.graph_objects as go

    if wait_df.empty or "player_id" not in wait_df.columns:
        return '<div class="alert alert-secondary">No wait response data.</div>'

    fig = go.Figure()
    for player in sorted(wait_df["player_id"].dropna().unique()):
        sub = wait_df[wait_df["player_id"] == player]
        fig.add_trace(
            go.Violin(
                x=[str(player)] * len(sub),
                y=sub["wait_response_duration_ms"],
                name=str(player),
                box_visible=True,
                meanline_visible=True,
                points=False,
                showlegend=False,
            )
        )
    fig.update_layout(
        title="Wait Response Duration by Player (Turn Phase)",
        xaxis_title="Player ID",
        yaxis_title="wait_response_duration_ms",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return plotly_to_html(fig)


def _lt_violin_wait_by_player_and_game(wait_df: pd.DataFrame) -> str:
    import plotly.graph_objects as go

    if wait_df.empty or "player_id" not in wait_df.columns or "game_label" not in wait_df.columns:
        return '<div class="alert alert-secondary">No wait response data.</div>'

    fig = go.Figure()
    for game in sorted(wait_df["game_label"].dropna().unique()):
        sub = wait_df[wait_df["game_label"] == game]
        fig.add_trace(
            go.Violin(
                x=sub["player_id"].astype(str),
                y=sub["wait_response_duration_ms"],
                name=game,
                legendgroup=game,
                box_visible=True,
                meanline_visible=True,
                points=False,
            )
        )
    fig.update_layout(
        title="Wait Response Duration by Player and Game (Turn Phase)",
        xaxis_title="Player ID",
        yaxis_title="wait_response_duration_ms",
        violinmode="group",
        height=450,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    return plotly_to_html(fig)


def _lt_hist_kde(values_series: pd.Series, title: str, xlabel: str) -> str:
    import plotly.graph_objects as go

    vals = values_series.dropna().to_numpy(dtype=float)
    if vals.size == 0:
        return '<div class="alert alert-secondary">No data.</div>'

    fig = go.Figure()
    fig.add_trace(
        go.Histogram(
            x=vals,
            nbinsx=40,
            histnorm="probability density",
            opacity=0.4,
            name="density",
            marker_color="steelblue",
        )
    )
    try:
        from scipy.stats import gaussian_kde

        kde = gaussian_kde(vals)
        xs = np.linspace(vals.min(), vals.max(), 300)
        fig.add_trace(go.Scatter(x=xs, y=kde(xs), mode="lines", name="KDE", line=dict(color="steelblue", width=2)))
    except Exception:
        pass

    for val, label, color, dash in [
        (float(np.mean(vals)), "mean", "crimson", "solid"),
        (float(np.median(vals)), "median", "darkorange", "dash"),
        (float(np.percentile(vals, 90)), "p90", "royalblue", "dot"),
        (float(np.percentile(vals, 95)), "p95", "seagreen", "dashdot"),
        (float(np.percentile(vals, 99)), "p99", "purple", "longdashdot"),
    ]:
        fig.add_vline(
            x=val,
            line_dash=dash,
            line_color=color,
            line_width=2,
            annotation_text=f"{label}={val:.0f} ms",
            annotation_position="top right",
            annotation_font_size=10,
        )
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title="Density",
        height=400,
        margin=dict(l=20, r=20, t=40, b=60),
        showlegend=True,
    )
    return plotly_to_html(fig)
