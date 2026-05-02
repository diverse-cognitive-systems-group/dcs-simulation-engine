"""Section 10 — System Errors.

Three views of errors:
  1. Summary stats card — log-level counts, in-game error event count,
     retry-budget-exhausted session count.
  2. Charts — log level breakdown (bar) + in-game error events per session (bar).
  3. Tables — top error messages, in-game error events, raw filtered log table.
"""



import pandas as pd

from dcs_utils.auto.constants import chart_caption, section_intro
from dcs_utils.auto.rendering.table_utils import df_to_datatable
from dcs_utils.common.loader import AnalysisData

# ---------------------------------------------------------------------------
# Column definitions for the raw log table (unchanged from original)
# ---------------------------------------------------------------------------

_LOG_COLUMNS = [
    "timestamp",
    "level",
    "log_file",
    "module",
    "function",
    "line",
    "message",
    "exception",
]

_LOG_RENAME = {
    "timestamp": "Timestamp",
    "level":     "Level",
    "log_file":  "Log File",
    "module":    "Module",
    "function":  "Function",
    "line":      "Line",
    "message":   "Message",
    "exception": "Exception",
}

_LEVEL_COL_INDEX = 1  # 0-based index of "Level" in _LOG_COLUMNS, used in JS


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------

def render(data: AnalysisData) -> str:
    parts: list[str] = [section_intro("system_errors")]

    parts.append(_summary_card(data))

    # Charts row
    row_charts = "".join([
        f'<div class="col-md-6 chart-container">'
        f'{_log_level_breakdown(data.logs_df)}'
        f'{chart_caption("system_errors", "log_level_breakdown")}'
        f'</div>',
        f'<div class="col-md-6 chart-container">'
        f'{_error_events_per_session(data)}'
        f'{chart_caption("system_errors", "error_events_per_session")}'
        f'</div>',
    ])
    parts.append(f'<div class="row">{row_charts}</div>')

    parts.append('<h3 class="h5 mt-4 mb-2">Top Error Messages</h3>')
    parts.append(_top_error_messages(data.errors_df))
    parts.append(chart_caption("system_errors", "top_error_messages"))

    parts.append('<h3 class="h5 mt-4 mb-2">In-Game Error Events</h3>')
    parts.append(_inplay_error_events_table(data))
    parts.append(chart_caption("system_errors", "inplay_error_events_table"))

    parts.append('<h3 class="h5 mt-4 mb-2">Engine Log Errors</h3>')
    parts.append(_log_errors_table(data))
    parts.append(chart_caption("system_errors", "errors_log_table"))

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

    warnings  = _level_count("WARNING")
    errors    = _level_count("ERROR")
    criticals = _level_count("CRITICAL")

    # In-game error events
    n_inplay = 0
    if not data.transcripts_df.empty and "event_type" in data.transcripts_df.columns:
        n_inplay = int(data.transcripts_df["event_type"].eq("error").sum())

    # Sessions ending with retry budget exhausted
    n_retry = 0
    if not data.runs_df.empty and "termination_reason" in data.runs_df.columns:
        n_retry = int(
            data.runs_df["termination_reason"]
            .fillna("")
            .str.lower()
            .str.contains("retry_budget|retry budget")
            .sum()
        )

    rows = [
        ("Log WARNINGs",                  str(warnings)),
        ("Log ERRORs",                    str(errors)),
        ("Log CRITICALs",                 str(criticals)),
        ("In-game error events",          str(n_inplay)),
        ("Sessions (retry budget exhausted)", str(n_retry)),
    ]
    dl_items = "".join(
        f"<dt class='col-sm-5'>{label}</dt><dd class='col-sm-7'>{value}</dd>"
        for label, value in rows
    )
    return (
        '<h3 class="h5 mb-2">Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{dl_items}</dl>'
        '</div></div>'
    )


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _log_level_breakdown(logs_df: pd.DataFrame) -> str:
    import plotly.express as px

    if logs_df.empty or "level" not in logs_df.columns:
        return '<div class="alert alert-secondary">No log data available.</div>'

    counts = (
        logs_df["level"].fillna("unknown")
        .value_counts()
        .rename_axis("level")
        .reset_index(name="count")
    )
    color_map = {
        "CRITICAL": "#c0392b",
        "ERROR":    "#e74c3c",
        "WARNING":  "#f39c12",
        "INFO":     "#3498db",
        "DEBUG":    "#95a5a6",
    }
    fig = px.bar(
        counts, x="count", y="level", orientation="h",
        title="Log Entries by Severity",
        labels={"level": "Level", "count": "Count"},
        color="level",
        color_discrete_map=color_map,
    )
    fig.update_layout(
        height=300, margin=dict(l=20, r=20, t=40, b=40),
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
            on="session_id", how="left",
        )
        counts["label"] = counts["session_id"].str[:8] + " (" + counts["game_name"].fillna("?") + ")"
    else:
        counts["label"] = counts["session_id"].str[:8]

    fig = px.bar(
        counts, x="errors", y="label", orientation="h",
        title="In-Game Error Events per Session",
        labels={"label": "Session", "errors": "Error Events"},
    )
    fig.update_layout(
        height=max(250, 60 + len(counts) * 28),
        margin=dict(l=20, r=20, t=40, b=40),
        yaxis={"categoryorder": "total ascending"},
    )
    return _plotly(fig)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _top_error_messages(errors_df: pd.DataFrame) -> str:
    if errors_df.empty or "message" not in errors_df.columns:
        return '<div class="alert alert-secondary">No error log data available.</div>'

    top = (
        errors_df["message"]
        .fillna("")
        .value_counts()
        .head(20)
        .rename_axis("message")
        .reset_index(name="count")
    )
    return df_to_datatable(
        top,
        table_id="top-errors-table",
        columns=["message", "count"],
        rename={"message": "Error Message", "count": "Occurrences"},
        truncate_cols=["message"],
        truncate_at=300,
    )


def _inplay_error_events_table(data: AnalysisData) -> str:
    if data.transcripts_df.empty or "event_type" not in data.transcripts_df.columns:
        return '<div class="alert alert-secondary">No session event data available.</div>'

    df = data.transcripts_df[data.transcripts_df["event_type"] == "error"].copy()
    if df.empty:
        return '<div class="alert alert-success">No in-game error events found.</div>'

    if not data.runs_df.empty:
        run_attrs = data.runs_df[
            [c for c in ["session_id", "player_id", "game_name", "pc_hid", "npc_hid"]
             if c in data.runs_df.columns]
        ].drop_duplicates("session_id")
        df = df.merge(run_attrs, on="session_id", how="left")

    cols_ordered = ["session_id", "player_id", "game_name", "pc_hid", "npc_hid",
                    "turn_index", "content", "event_ts"]
    cols = [c for c in cols_ordered if c in df.columns]
    rename = {
        "session_id": "Session",
        "player_id":  "Player",
        "game_name":  "Game",
        "pc_hid":     "PC",
        "npc_hid":    "NPC",
        "turn_index": "Turn",
        "content":    "Error Message",
        "event_ts":   "Timestamp",
    }
    return df_to_datatable(
        df,
        table_id="inplay-errors-table",
        columns=cols,
        rename={k: v for k, v in rename.items() if k in cols},
        truncate_cols=["content"],
        truncate_at=400,
    )


def _log_errors_table(data: AnalysisData) -> str:
    df = data.errors_df

    if df.empty:
        if data.logs_df.empty:
            return (
                '<div class="alert alert-secondary">'
                'No log files found — cannot check for errors.'
                '</div>'
            )
        return (
            '<div class="alert alert-success">'
            'No warnings or errors found in logs.'
            '</div>'
        )

    cols = [c for c in _LOG_COLUMNS if c in df.columns]
    rename = {k: v for k, v in _LOG_RENAME.items() if k in cols}

    table_html = df_to_datatable(
        df,
        table_id="errors-table",
        columns=cols,
        rename=rename,
        truncate_cols=["message", "exception"],
        truncate_at=300,
    )

    highlight_script = f"""
<script>
$(document).ready(function () {{
    var table = $('#errors-table').DataTable();
    $('#errors-table tbody').on('draw.dt', function () {{
        table.rows().every(function () {{
            var data = this.data();
            var level = data[{_LEVEL_COL_INDEX}];
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
    from dcs_utils.auto.rendering.chart_utils import plotly_to_html
    return plotly_to_html(fig)
