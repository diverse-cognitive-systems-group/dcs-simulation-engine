"""Section 2 — Runs Overview Table.

Renders a DataTables interactive table with one row per session (run),
showing player, game, characters, turn count, duration, exit reason, etc.
"""

from __future__ import annotations

from analysis.auto.constants import chart_caption, section_intro
from analysis.auto.rendering.table_utils import df_to_datatable
from analysis.auto.sections.system_performance import _pairing_heatmap
from analysis.common.loader import AnalysisData

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
    "session_id":        "Run ID",
    "player_id":         "Player",
    "game_name":         "Game",
    "pc_hid":            "PC",
    "npc_hid":           "NPC",
    "turns_completed":   "Turns",
    "duration_human":    "Duration",
    "termination_reason":"Exit Reason",
    "last_seq":          "Last Seq",
    "status":            "Status",
    "session_started_at":"Started",
    "session_ended_at":  "Ended",
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

    return "\n".join([
        section_intro("runs_overview"),
        '<div class="chart-container mb-4">' + _pairing_heatmap(df) + '</div>',
        chart_caption("runs_overview", "pairing_heatmap"),
        table_html,
        chart_caption("runs_overview", "sessions_table"),
    ])
