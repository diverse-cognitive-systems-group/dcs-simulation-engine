"""Section — Simulation Quality.

Renders:
1. Scores summary card — overall ICF, NCo, and Other rates across all NPC turns.
2. Per-NPC scores table — ICF, NCo, and Other broken down by NPC character.
"""



import pandas as pd

from analysis.auto.constants import chart_caption, section_intro
from analysis.auto.rendering.table_utils import df_to_datatable
from analysis.common.loader import AnalysisData


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "—"
    return f"{numerator / denominator:.1%}"


def _flag_count(transcripts_df: pd.DataFrame, col: str) -> int:
    if col not in transcripts_df.columns:
        return 0
    return int(transcripts_df[col].fillna(False).astype(bool).sum())


def _scores_summary_card(transcripts_df: pd.DataFrame) -> str:
    """Return a Bootstrap dl-meta card with overall ICF, NCo, and Other scores."""
    if not transcripts_df.empty and "event_source" in transcripts_df.columns:
        total_npc_turns = int((transcripts_df["event_source"].fillna("") == "npc").sum())
    else:
        total_npc_turns = 0

    ooc_count   = _flag_count(transcripts_df, "feedback.out_of_character")
    dms_count   = _flag_count(transcripts_df, "feedback.doesnt_make_sense")
    other_count = _flag_count(transcripts_df, "feedback.other")
    in_char     = total_npc_turns - ooc_count

    rows = [
        ("Total NPC Turns",              str(total_npc_turns)),
        ("In-Character Fidelity (ICF)",  _fmt_pct(in_char,     total_npc_turns)),
        ("Narrative Coherence (NCo)",    _fmt_pct(dms_count,   total_npc_turns)),
        ("Other",                        _fmt_pct(other_count, total_npc_turns)),
    ]

    dl_items = "".join(
        f"<dt class='col-sm-4'>{label}</dt><dd class='col-sm-8'>{value}</dd>"
        for label, value in rows
    )
    return (
        '<h3 class="h5 mb-2">Scores Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{dl_items}</dl>'
        '</div></div>'
    )


def _per_npc_scores_table(transcripts_df: pd.DataFrame, runs_df: pd.DataFrame) -> str:
    """Return a DataTable of ICF, NCo, and Other scores per NPC character."""
    if transcripts_df.empty or "event_source" not in transcripts_df.columns:
        return ""

    npc_turns = transcripts_df[transcripts_df["event_source"].fillna("") == "npc"].copy()
    if npc_turns.empty:
        return ""

    # Join npc_hid from runs_df via session_id
    if (
        not runs_df.empty
        and "session_id" in runs_df.columns
        and "npc_hid" in runs_df.columns
        and "session_id" in npc_turns.columns
    ):
        npc_turns = npc_turns.merge(
            runs_df[["session_id", "npc_hid"]].drop_duplicates(),
            on="session_id",
            how="left",
        )
    elif "npc_hid" not in npc_turns.columns:
        return ""

    if "npc_hid" not in npc_turns.columns or npc_turns["npc_hid"].isna().all():
        return ""

    flag_cols = {
        "ooc":   "feedback.out_of_character",
        "dms":   "feedback.doesnt_make_sense",
        "other": "feedback.other",
    }

    # Ensure flag columns exist (default False)
    for key, col in flag_cols.items():
        if col not in npc_turns.columns:
            npc_turns[col] = False
        npc_turns[col] = npc_turns[col].fillna(False).astype(bool)

    rows = []
    for npc_hid, grp in npc_turns.groupby("npc_hid", sort=True):
        total  = len(grp)
        ooc    = int(grp[flag_cols["ooc"]].sum())
        dms    = int(grp[flag_cols["dms"]].sum())
        other  = int(grp[flag_cols["other"]].sum())
        in_char = total - ooc
        rows.append({
            "npc_hid": npc_hid,
            "turns":   total,
            "icf":     _fmt_pct(in_char, total),
            "nco":     _fmt_pct(dms,     total),
            "other":   _fmt_pct(other,   total),
        })

    if not rows:
        return ""

    df = pd.DataFrame(rows)
    return df_to_datatable(
        df,
        table_id="sim-quality-per-npc-table",
        columns=["npc_hid", "turns", "icf", "nco", "other"],
        rename={
            "npc_hid": "NPC",
            "turns":   "Turns",
            "icf":     "ICF",
            "nco":     "NCo",
            "other":   "Other",
        },
        scroll_y="",
        export_buttons=True,
    )


def render(data: AnalysisData) -> str:
    tdf = data.transcripts_df
    rdf = data.runs_df

    if tdf.empty:
        return '<div class="alert alert-info">No transcript data found.</div>'

    parts = [section_intro("simulation_quality")]
    parts.append(_scores_summary_card(tdf))

    table = _per_npc_scores_table(tdf, rdf)
    if table:
        parts.append('<h3 class="h5 mt-4 mb-2">Scores per NPC</h3>')
        parts.append(table)
        parts.append(chart_caption("simulation_quality", "per_npc_scores_table"))

    return "\n".join(parts)
