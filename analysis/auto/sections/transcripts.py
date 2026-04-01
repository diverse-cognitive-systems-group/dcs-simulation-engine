"""Section 7 — Transcripts.

Full session-events DataTable. PC/NPC/player columns are joined from
runs_df since session_events only carries session_id.
Content is truncated at 400 chars in-cell (full text in title tooltip).
"""

from __future__ import annotations

from dcs_utils.analysis.auto.rendering.table_utils import df_to_datatable
from dcs_utils.analysis.common.loader import AnalysisData

_COLUMNS = [
    "session_id",
    "player_id",
    "pc_hid",
    "npc_hid",
    "turn_index",
    "event_source",
    "direction",
    "event_type",
    "command_name",
    "content",
    "event_ts",
    "visible_to_user",
]

_RENAME = {
    "session_id":    "Run ID",
    "player_id":     "Player",
    "pc_hid":        "PC",
    "npc_hid":       "NPC",
    "turn_index":    "Turn",
    "event_source":  "Source",
    "direction":     "Direction",
    "event_type":    "Type",
    "command_name":  "Command",
    "content":       "Content",
    "event_ts":      "Timestamp",
    "visible_to_user": "Visible",
}


def render(data: AnalysisData) -> str:
    df = data.transcripts_df.copy()

    if df.empty:
        return '<div class="alert alert-info">No transcript events found.</div>'

    # Join PC/NPC/player from runs_df
    if not data.runs_df.empty:
        run_attrs = data.runs_df[
            [c for c in ["session_id", "pc_hid", "npc_hid", "player_id"] if c in data.runs_df.columns]
        ].drop_duplicates("session_id")
        df = df.merge(run_attrs, on="session_id", how="left")

    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    return df_to_datatable(
        df,
        table_id="transcripts-table",
        columns=cols,
        rename=rename,
        page_length=50,
        truncate_cols=["content"],
        truncate_at=400,
    )
