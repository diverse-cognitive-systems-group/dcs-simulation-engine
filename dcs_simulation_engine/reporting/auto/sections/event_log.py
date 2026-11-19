"""Section 7 — Full Event Log.

Session-events DataTable. PC/NPC/player and evaluator description are joined
from runs_df since session_events only carries session_id.
"""

from html import escape

from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable, hitl_player_label
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
    "evaluator_description",
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
    "evaluator_description": "Evaluator Description",
    "event_ts": "Timestamp",
}


def render(data: AnalysisData) -> str:
    df = data.transcripts_df.copy()

    if df.empty:
        return '<div class="alert alert-info">No transcript events found.</div>'

    if not data.runs_df.empty:
        session_columns = ["session_id", "pc_hid", "npc_hid", "player_id"]
        if "evaluator_description" not in df.columns:
            session_columns.append("evaluator_description")
        run_attrs = data.runs_df[[c for c in session_columns if c in data.runs_df.columns]].drop_duplicates("session_id")
        df = df.merge(run_attrs, on="session_id", how="left")

    if "evaluator_description" in df.columns:
        # Tables with truncation enabled render cells as HTML.
        df["evaluator_description"] = df["evaluator_description"].fillna("").astype(str).map(escape)

    sort_cols = [c for c in ["session_id", "turn_index", "event_ts"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)

    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    table = df_to_datatable(
        df,
        table_id="event-log-table",
        columns=cols,
        rename=rename,
        truncate_cols=["content"],
        truncate_at=400,
        player_label=hitl_player_label(data.manifest),
    )
    return section_intro("event_log") + '<h3 class="h5 mb-2">Events</h3>' + table + chart_caption("event_log", "event_log_table")
