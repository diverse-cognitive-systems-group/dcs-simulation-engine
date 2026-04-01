"""Section 9 — Logs.

Full interactive DataTable of all log events parsed from *.log files.
"""

from __future__ import annotations

from dcs_utils.analysis.auto.rendering.table_utils import df_to_datatable
from dcs_utils.analysis.common.loader import AnalysisData

_COLUMNS = [
    "timestamp",
    "level",
    "log_file",
    "module",
    "function",
    "line",
    "message",
    "exception",
]

_RENAME = {
    "timestamp": "Timestamp",
    "level":     "Level",
    "log_file":  "Log File",
    "module":    "Module",
    "function":  "Function",
    "line":      "Line",
    "message":   "Message",
    "exception": "Exception",
}


def render(data: AnalysisData) -> str:
    df = data.logs_df

    if df.empty:
        return (
            '<div class="alert alert-secondary">'
            'No log files found in the results directory.'
            '</div>'
        )

    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    return df_to_datatable(
        df,
        table_id="logs-table",
        columns=cols,
        rename=rename,
        page_length=50,
        truncate_cols=["message", "exception"],
        truncate_at=300,
    )
