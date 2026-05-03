"""Section — Simulation Quality.

Renders:
1. Scores summary card — overall ICF, NCo, and Other rates across all NPC turns.
2. Per-NPC scores table — ICF, NCo, Other, and Scenario Coverage broken down by NPC character.
"""

import html as html_lib
import json
from pathlib import Path

import pandas as pd
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

_PRESSURE_CATEGORIES_PATH = Path(__file__).resolve().parents[3] / "hitl" / "character-evaluation-template.json"


def _fmt_pct(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "—"
    return f"{numerator / denominator:.1%}"


def _flag_count(transcripts_df: pd.DataFrame, col: str) -> int:
    if col not in transcripts_df.columns:
        return 0
    return int(transcripts_df[col].fillna(False).astype(bool).sum())


def _load_pressure_categories() -> list[dict]:
    """Load evaluation category definitions from the HITL template."""
    try:
        raw = json.loads(_PRESSURE_CATEGORIES_PATH.read_text(encoding="utf-8"))
        return raw.get("evaluation_categories", [])
    except Exception:
        return []


def _compute_covered_categories(npc_hid: str, runs_df: pd.DataFrame) -> set[str]:
    """Return the set of pressure category IDs covered by this NPC's sessions."""
    col = "game_config_snapshot.pressure_category"
    if runs_df.empty or "npc_hid" not in runs_df.columns or col not in runs_df.columns:
        return set()
    char_runs = runs_df[runs_df["npc_hid"] == npc_hid]
    return set(char_runs[col].dropna().astype(str).unique()) - {""}


def _scenario_coverage_section(npc_hid: str, runs_df: pd.DataFrame) -> str:
    """Render a Bootstrap checklist of all pressure categories with coverage marks."""
    categories = _load_pressure_categories()
    if not categories:
        return '<p class="text-muted">Pressure category definitions not found.</p>'

    covered = _compute_covered_categories(npc_hid, runs_df)
    total = len(categories)
    n_covered = sum(1 for cat in categories if cat["id"] in covered)

    if total > 0:
        score_pct = f"{n_covered / total:.1%}"
        header_text = f"{n_covered} of {total} pressure categories covered ({score_pct})"
    else:
        header_text = "No pressure categories defined."

    items = []
    for cat in categories:
        cat_id = cat.get("id", "")
        description = html_lib.escape(cat.get("description", ""))
        label = cat_id.replace("_", " ").title()
        is_covered = cat_id in covered
        if is_covered:
            icon = '<span class="text-success fw-bold" style="min-width:1.2em;">✓</span>'
        else:
            icon = '<span class="text-danger fw-bold" style="min-width:1.2em;">✗</span>'
        items.append(
            f'<li class="list-group-item d-flex align-items-start gap-2 py-2">'
            f"{icon}"
            f"<div>"
            f'<span class="fw-semibold">{html_lib.escape(label)}</span>'
            f'<span class="text-muted ms-2" style="font-size:0.88rem;">{description}</span>'
            f"</div>"
            f"</li>"
        )

    list_html = '<ul class="list-group list-group-flush">' + "".join(items) + "</ul>"

    return f'<p class="mb-2">{html_lib.escape(header_text)}</p><div class="card"><div class="card-body p-0">{list_html}</div></div>'


def _scores_summary_card(
    transcripts_df: pd.DataFrame,
    coverage_text: str | None = None,
) -> str:
    """Return a Bootstrap dl-meta card with overall ICF, NCo, Other, and optional Scenario Coverage."""
    if not transcripts_df.empty and "event_source" in transcripts_df.columns:
        total_npc_turns = int((transcripts_df["event_source"].fillna("") == "npc").sum())
    else:
        total_npc_turns = 0

    ooc_count = _flag_count(transcripts_df, "feedback.out_of_character")
    dms_count = _flag_count(transcripts_df, "feedback.doesnt_make_sense")
    other_count = _flag_count(transcripts_df, "feedback.other")
    in_char = total_npc_turns - ooc_count

    rows = [
        ("Total NPC Turns", str(total_npc_turns)),
        ("In-Character Fidelity (ICF)", _fmt_pct(in_char, total_npc_turns)),
        ("Narrative Coherence (NCo)", _fmt_pct(dms_count, total_npc_turns)),
        ("Other", _fmt_pct(other_count, total_npc_turns)),
    ]
    if coverage_text is not None:
        rows.append(("Scenario Coverage", coverage_text))

    dl_items = "".join(f"<dt class='col-sm-4'>{label}</dt><dd class='col-sm-8'>{value}</dd>" for label, value in rows)
    return (
        '<h3 class="h5 mb-2">Scores Summary</h3>'
        '<div class="card mb-4"><div class="card-body">'
        f'<dl class="row dl-meta mb-0">{dl_items}</dl>'
        "</div></div>"
    )


def _per_npc_scores_table(
    transcripts_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    characters_df: pd.DataFrame,
) -> str:
    """Return a DataTable of ICF, NCo, Other, and Scenario Coverage scores per NPC character."""
    if transcripts_df.empty or "event_source" not in transcripts_df.columns:
        return ""

    npc_turns = transcripts_df[transcripts_df["event_source"].fillna("") == "npc"].copy()
    if npc_turns.empty:
        return ""

    # Join npc_hid from runs_df via session_id
    if not runs_df.empty and "session_id" in runs_df.columns and "npc_hid" in runs_df.columns and "session_id" in npc_turns.columns:
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
        "ooc": "feedback.out_of_character",
        "dms": "feedback.doesnt_make_sense",
        "other": "feedback.other",
    }

    # Ensure flag columns exist (default False)
    for key, col in flag_cols.items():
        if col not in npc_turns.columns:
            npc_turns[col] = False
        npc_turns[col] = npc_turns[col].fillna(False).astype(bool)

    # Build hid → short_description lookup from characters_df
    desc_by_hid: dict[str, str] = {}
    if not characters_df.empty and "hid" in characters_df.columns and "short_description" in characters_df.columns:
        desc_by_hid = dict(zip(characters_df["hid"], characters_df["short_description"].fillna("")))

    all_categories = _load_pressure_categories()

    rows = []
    for npc_hid, grp in npc_turns.groupby("npc_hid", sort=True):
        total = len(grp)
        ooc = int(grp[flag_cols["ooc"]].sum())
        dms = int(grp[flag_cols["dms"]].sum())
        other = int(grp[flag_cols["other"]].sum())
        in_char = total - ooc

        covered = _compute_covered_categories(str(npc_hid), runs_df)
        rows.append(
            {
                "npc_hid": npc_hid,
                "descriptor": desc_by_hid.get(str(npc_hid), ""),
                "turns": total,
                "icf": _fmt_pct(in_char, total),
                "nco": _fmt_pct(dms, total),
                "other": _fmt_pct(other, total),
                "scenario_coverage": _fmt_pct(len(covered), len(all_categories)),
            }
        )

    if not rows:
        return ""

    df = pd.DataFrame(rows)
    return df_to_datatable(
        df,
        table_id="sim-quality-per-npc-table",
        columns=["npc_hid", "descriptor", "turns", "icf", "nco", "other", "scenario_coverage"],
        rename={
            "npc_hid": "HID",
            "descriptor": "Character",
            "turns": "Turns",
            "icf": "ICF",
            "nco": "NCo",
            "other": "Other",
            "scenario_coverage": "Scenario Coverage",
        },
        scroll_y="",
        export_buttons=True,
        truncate_cols=["descriptor"],
        truncate_at=80,
    )


def build_character_quality_report(hid: str, data: AnalysisData) -> str:
    """Build a standalone per-character quality HTML report for the given NPC HID."""
    from dcs_simulation_engine.reporting.auto.rendering.html_builder import build_html
    from dcs_simulation_engine.reporting.auto.sections import player_feedback
    from dcs_simulation_engine.reporting.auto.sections import transcripts as transcripts_section

    # --- Character metadata ---
    char_meta: dict = {"hid": hid}
    if not data.characters_df.empty and "hid" in data.characters_df.columns:
        matches = data.characters_df[data.characters_df["hid"] == hid]
        if not matches.empty:
            char_row = matches.iloc[0]
            for key in ("name", "short_description", "long_description"):
                if key in char_row.index and pd.notna(char_row[key]):
                    char_meta[key] = char_row[key]

    # --- Session IDs for this NPC ---
    session_ids: set = set()
    if not data.runs_df.empty and "npc_hid" in data.runs_df.columns and "session_id" in data.runs_df.columns:
        session_ids = set(data.runs_df[data.runs_df["npc_hid"] == hid]["session_id"].dropna())

    # --- Filtered DataFrames ---
    def _filter(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "session_id" not in df.columns:
            return pd.DataFrame()
        return df[df["session_id"].isin(session_ids)].copy()

    char_data = AnalysisData(
        results_dir=data.results_dir,
        manifest=data.manifest,
        run=data.run,
        runs_df=_filter(data.runs_df),
        players_df=data.players_df,
        transcripts_df=_filter(data.transcripts_df),
        assignments_df=data.assignments_df,
        feedback_df=data.feedback_df,
        event_feedback_df=_filter(data.event_feedback_df),
        logs_df=data.logs_df,
        characters_df=data.characters_df,
        errors_df=data.errors_df,
    )

    # --- Scenario coverage ---
    all_cats = _load_pressure_categories()
    covered = _compute_covered_categories(hid, data.runs_df)
    if all_cats:
        coverage_text = f"{len(covered)}/{len(all_cats)} ({len(covered) / len(all_cats):.1%})"
    else:
        coverage_text = None

    # --- Section fragments ---

    # 1. Metadata
    meta_rows = [("HID", html_lib.escape(hid))]
    for key, label in (("name", "Name"), ("short_description", "Description"), ("long_description", "Long Description")):
        if key in char_meta:
            meta_rows.append((label, html_lib.escape(str(char_meta[key]))))
    dl_items = "".join(f"<dt class='col-sm-3'>{lbl}</dt><dd class='col-sm-9'>{val}</dd>" for lbl, val in meta_rows)
    metadata_fragment = f'<div class="card"><div class="card-body"><dl class="row dl-meta mb-0">{dl_items}</dl></div></div>'

    # 2. Overview (scores summary filtered to this character)
    overview_fragment = _scores_summary_card(char_data.transcripts_df, coverage_text=coverage_text)

    # 3. Scenario Coverage
    scenario_fragment = _scenario_coverage_section(hid, data.runs_df)

    # 4. Feedback
    feedback_fragment = player_feedback.render(char_data)

    # 5. Transcripts
    transcripts_fragment = transcripts_section.render(char_data)

    # --- Assemble ---
    sections = [
        ("metadata", "Metadata", metadata_fragment, "top"),
        ("overview", "Overview", overview_fragment, "top"),
        ("scenario-coverage", "Scenario Coverage", scenario_fragment, "top"),
        ("feedback", "Feedback", feedback_fragment, "top"),
        ("transcripts", "Transcripts", transcripts_fragment, "top"),
    ]

    char_name = char_meta.get("name") or hid
    return build_html(sections, title=f"{char_name} — Quality Report", download_items=[])


def render(data: AnalysisData) -> str:
    tdf = data.transcripts_df
    rdf = data.runs_df

    if tdf.empty:
        return '<div class="alert alert-info">No transcript data found.</div>'

    parts = [section_intro("simulation_quality")]

    table = _per_npc_scores_table(tdf, rdf, data.characters_df)
    if table:
        parts.append('<h3 class="h5 mt-4 mb-2">Scores per NPC</h3>')
        parts.append(table)
        parts.append(chart_caption("simulation_quality", "per_npc_scores_table"))

    return "\n".join(parts)
