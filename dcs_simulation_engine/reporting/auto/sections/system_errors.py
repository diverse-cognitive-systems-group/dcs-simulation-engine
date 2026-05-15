"""Section 10 — System Errors.

Two views of errors:
  1. Summary stats card — log-level counts, in-game error event count,
     validation-lockout and internal-failure session counts.
  2. Charts — log level breakdown (bar) + in-game error events per session (bar).
  3. Tables — player-facing error events and the full logs collection.
"""

import pandas as pd
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.chart_utils import use_integer_ticks
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

_PREFERRED_LOG_COLUMNS = [
    "timestamp",
    "event_ts",
    "persisted_at",
    "source",
    "level",
    "level_no",
    "log_file",
    "module",
    "function",
    "line",
    "message",
    "exception",
    "event_id",
    "event_idx",
    "parse_error",
]

_LOG_RENAME = {
    "timestamp": "Timestamp",
    "event_ts": "Event Timestamp",
    "persisted_at": "Persisted At",
    "source": "Source",
    "level": "Level",
    "level_no": "Level No",
    "log_file": "Log File",
    "module": "Module",
    "function": "Function",
    "line": "Line",
    "message": "Message",
    "exception": "Exception",
    "event_id": "Event ID",
    "event_idx": "Event Index",
    "parse_error": "Parse Error",
}


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render(data: AnalysisData) -> str:
    parts: list[str] = [section_intro("system_errors")]

    parts.append(_summary_card(data))

    # Charts row
    row_charts = "".join(
        [
            f'<div class="col-md-6 chart-container">'
            f"{_log_level_breakdown(data.logs_df)}"
            f"{chart_caption('system_errors', 'log_level_breakdown')}"
            f"</div>",
            f'<div class="col-md-6 chart-container">'
            f"{_error_events_per_session(data)}"
            f"{chart_caption('system_errors', 'error_events_per_session')}"
            f"</div>",
        ]
    )
    parts.append(f'<div class="row">{row_charts}</div>')

    parts.append('<h3 class="h5 mt-4 mb-2">Player-Facing Error Events</h3>')
    parts.append(_inplay_error_events_table(data))
    parts.append(chart_caption("system_errors", "inplay_error_events_table"))

    parts.append('<h3 class="h5 mt-4 mb-2">Engine Logs</h3>')
    parts.append(_logs_table(data))
    parts.append(chart_caption("system_errors", "logs_table"))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Summary card
# ---------------------------------------------------------------------------


def _summary_card(data: AnalysisData) -> str:
    # Log-level counts
    def _level_count(level: str) -> int:
        if data.errors_df.empty or "level" not in data.errors_df.columns:
            return 0
        return int(data.errors_df["level"].eq(level).sum())

    warnings = _level_count("WARNING")
    errors = _level_count("ERROR")
    criticals = _level_count("CRITICAL")

    # In-game error events
    n_inplay = 0
    if not data.transcripts_df.empty and "event_type" in data.transcripts_df.columns:
        n_inplay = int(data.transcripts_df["event_type"].eq("error").sum())

    # Sessions ending from player lockout or internal system failures
    n_player_lockout = 0
    n_internal_terminal = 0
    if not data.runs_df.empty and "termination_reason" in data.runs_df.columns:
        reasons = data.runs_df["termination_reason"].fillna("").str.lower()
        n_player_lockout = int(
            reasons.str.contains("player_validation_retry_exhausted|validation_retry_exhausted|retry_budget|retry budget").sum()
        )
        n_internal_terminal = int(
            reasons.str.contains(
                "simulator_validation_retry_exhausted|simulator_recovery_budget_exhausted|internal_error|server_error"
            ).sum()
        )

    rows = [
        ("Log WARNINGs", str(warnings)),
        ("Log ERRORs", str(errors)),
        ("Log CRITICALs", str(criticals)),
        ("In-game error events", str(n_inplay)),
        ("Sessions (player validation lockout)", str(n_player_lockout)),
        ("Sessions (internal/system failure)", str(n_internal_terminal)),
    ]
    dl_items = "".join(f"<dt class='col-sm-5'>{label}</dt><dd class='col-sm-7'>{value}</dd>" for label, value in rows)
    return (
        '<h3 class="h5 mb-2">Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{dl_items}</dl>'
        "</div></div>"
    )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def _log_level_breakdown(logs_df: pd.DataFrame) -> str:
    import plotly.express as px

    if logs_df.empty or "level" not in logs_df.columns:
        return '<div class="alert alert-success">No engine log entries were recorded for this run.</div>'

    counts = logs_df["level"].fillna("unknown").value_counts().rename_axis("level").reset_index(name="count")
    color_map = {
        "CRITICAL": "#c0392b",
        "ERROR": "#e74c3c",
        "WARNING": "#f39c12",
        "INFO": "#3498db",
        "DEBUG": "#95a5a6",
    }
    fig = px.bar(
        counts,
        x="count",
        y="level",
        orientation="h",
        title="Log Entries by Severity",
        labels={"level": "Level", "count": "Count"},
        color="level",
        color_discrete_map=color_map,
    )
    use_integer_ticks(fig, x=True)
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=40, b=40),
        showlegend=False,
        yaxis={"categoryorder": "total ascending"},
    )
    return _plotly(fig)


def _error_events_per_session(data: AnalysisData) -> str:
    import plotly.express as px

    if data.transcripts_df.empty or "event_type" not in data.transcripts_df.columns:
        return '<div class="alert alert-secondary">No session event data available.</div>'

    error_events = data.transcripts_df[data.transcripts_df["event_type"] == "error"]
    if error_events.empty:
        return '<div class="alert alert-success">No in-game error events found.</div>'

    counts = (
        error_events.groupby("session_id")
        .size()
        .rename_axis("session_id")
        .reset_index(name="errors")
        .sort_values("errors", ascending=False)
    )

    # Join game name if available
    if not data.runs_df.empty and "game_name" in data.runs_df.columns:
        counts = counts.merge(
            data.runs_df[["session_id", "game_name"]].drop_duplicates("session_id"),
            on="session_id",
            how="left",
        )
        counts["label"] = counts["session_id"].str[:8] + " (" + counts["game_name"].fillna("?") + ")"
    else:
        counts["label"] = counts["session_id"].str[:8]

    fig = px.bar(
        counts,
        x="errors",
        y="label",
        orientation="h",
        title="In-Game Error Events per Session",
        labels={"label": "Session", "errors": "Error Events"},
    )
    use_integer_ticks(fig, x=True)
    fig.update_layout(
        height=max(250, 60 + len(counts) * 28),
        margin=dict(l=20, r=20, t=40, b=40),
        yaxis={"categoryorder": "total ascending"},
    )
    return _plotly(fig)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _inplay_error_events_table(data: AnalysisData) -> str:
    if data.transcripts_df.empty or "event_type" not in data.transcripts_df.columns:
        return '<div class="alert alert-secondary">No session event data available.</div>'

    df = data.transcripts_df[data.transcripts_df["event_type"] == "error"].copy()
    if df.empty:
        return '<div class="alert alert-success">No in-game error events found.</div>'

    if not data.runs_df.empty:
        run_attrs = data.runs_df[
            [c for c in ["session_id", "player_id", "game_name", "pc_hid", "npc_hid"] if c in data.runs_df.columns]
        ].drop_duplicates("session_id")
        df = df.merge(run_attrs, on="session_id", how="left")

    cols_ordered = ["session_id", "player_id", "game_name", "pc_hid", "npc_hid", "turn_index", "content", "event_ts"]
    cols = [c for c in cols_ordered if c in df.columns]
    rename = {
        "session_id": "Session",
        "player_id": "Player",
        "game_name": "Game",
        "pc_hid": "PC",
        "npc_hid": "NPC",
        "turn_index": "Turn",
        "content": "Error Message",
        "event_ts": "Timestamp",
    }
    return df_to_datatable(
        df,
        table_id="inplay-errors-table",
        columns=cols,
        rename={k: v for k, v in rename.items() if k in cols},
    )


def _logs_table(data: AnalysisData) -> str:
    df = data.logs_df

    if df.empty:
        return _no_engine_logs_message(data)

    preferred = [c for c in _PREFERRED_LOG_COLUMNS if c in df.columns]
    remaining = [c for c in df.columns if c not in preferred]
    cols = preferred + remaining
    rename = {col: _LOG_RENAME.get(col, col.replace("_", " ").title()) for col in cols}

    table_html = df_to_datatable(
        df,
        table_id="engine-logs-table",
        columns=cols,
        rename=rename,
    )

    if "level" not in cols:
        return table_html

    level_col_index = cols.index("level")
    highlight_script = f"""
<script>
$(document).ready(function () {{
    var table = $('#engine-logs-table').DataTable();
    table.on('draw.dt', function () {{
        table.rows().every(function () {{
            var data = this.data();
            var level = data[{level_col_index}];
            var row = this.node();
            if (level === 'ERROR' || level === 'CRITICAL') {{
                $(row).addClass('table-danger');
            }} else if (level === 'WARNING') {{
                $(row).addClass('table-warning');
            }}
        }});
    }});
}});
</script>"""

    return table_html + highlight_script


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plotly(fig) -> str:
    from dcs_simulation_engine.reporting.auto.rendering.chart_utils import plotly_to_html

    return plotly_to_html(fig)


def _no_engine_logs_message(data: AnalysisData) -> str:
    if data.logs_source:
        return f'<div class="alert alert-success">{data.logs_source} was found, but no engine log entries were recorded for this run.</div>'
    return '<div class="alert alert-secondary">No engine log source was found in this results directory.</div>'
