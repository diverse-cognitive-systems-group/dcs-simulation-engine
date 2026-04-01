"""Section 10 — System Errors.

Filtered log table showing only WARNING/ERROR/CRITICAL rows and any
rows whose message matches error/exception/failure/traceback/critical.
Rows are highlighted by severity using Bootstrap contextual classes via
a DataTables createdRow callback.
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

# Index of the "Level" column after rename (0-based, used in createdRow JS)
_LEVEL_COL_INDEX = 1  # position of "Level" in _COLUMNS


def render(data: AnalysisData) -> str:
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

    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    table_html = df_to_datatable(
        df,
        table_id="errors-table",
        columns=cols,
        rename=rename,
        page_length=50,
        truncate_cols=["message", "exception"],
        truncate_at=300,
    )

    # Inject row-highlighting callback after DataTable init
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
