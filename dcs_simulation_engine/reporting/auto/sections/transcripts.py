"""Section 7 — Transcripts.

Transcript-focused session-events DataTable. PC/NPC/player columns are joined
from runs_df since session_events only carries session_id.
"""

from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

_COLUMNS = [
    "session_id",
    "player_id",
    "pc_hid",
    "npc_hid",
    "turn_index",
    "event_source",
    "event_type",
    "content",
    "event_ts",
]

_RENAME = {
    "session_id": "Gameplay Session",
    "player_id": "Player",
    "pc_hid": "PC",
    "npc_hid": "NPC",
    "turn_index": "Turn",
    "event_source": "Source",
    "event_type": "Type",
    "content": "Transcript",
    "event_ts": "Timestamp",
}


def render(data: AnalysisData) -> str:
    df = data.transcripts_df.copy()

    if df.empty:
        return '<div class="alert alert-info">No transcript events found.</div>'

    if not data.runs_df.empty:
        run_attrs = data.runs_df[
            [c for c in ["session_id", "pc_hid", "npc_hid", "player_id"] if c in data.runs_df.columns]
        ].drop_duplicates("session_id")
        df = df.merge(run_attrs, on="session_id", how="left")

    sort_cols = [c for c in ["session_id", "turn_index", "event_ts"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    table = df_to_datatable(
        df,
        table_id="transcripts-table",
        columns=cols,
        rename=rename,
        truncate_cols=["content"],
        truncate_at=400,
    )
    return (
        section_intro("transcripts") + '<h3 class="h5 mb-2">Session Events</h3>' + table + chart_caption("transcripts", "transcripts_table")
    )
