"""Section — Simulation Quality.

Renders:
1. Scores summary card — overall ICF, NCo, and Other rates across all NPC turns.
2. Per-NPC scores table — ICF, NCo, Other, and Scenario Coverage broken down by NPC character.
"""

import html as html_lib
from pathlib import Path

import pandas as pd
import yaml
from dcs_simulation_engine.reporting.auto.constants import chart_caption, section_intro
from dcs_simulation_engine.reporting.auto.rendering.table_utils import df_to_datatable
from dcs_simulation_engine.reporting.loader import AnalysisData

_PRESSURE_CATEGORIES_PATH = Path(__file__).resolve().parents[3] / "hitl" / "character-evaluation-template.yml"


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
        raw = yaml.safe_load(_PRESSURE_CATEGORIES_PATH.read_text(encoding="utf-8"))
        return raw.get("evaluation_categories", [])
    except Exception:
        return []


def _compute_covered_categories(npc_hid: str, runs_df: pd.DataFrame) -> set[str]:
    """Return the set of pressure category IDs covered by this NPC's sessions."""
    col = "game_config_snapshot.group_id"
    if runs_df.empty or "npc_hid" not in runs_df.columns or col not in runs_df.columns:
        return set()
    char_runs = runs_df[runs_df["npc_hid"] == npc_hid]
    category_ids = {cat["id"] for cat in _load_pressure_categories()}
    return set(char_runs[col].dropna().astype(str).unique()) & category_ids


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


def render_evaluation_summary(data: AnalysisData) -> str:
    """Show the evaluator's summary and publication readiness for HITL results."""
    manifest = data.manifest
    status = manifest.get("evaluation_status")
    if not isinstance(status, dict) or not isinstance(complete := status.get("complete"), bool):
        return ""
    if complete:
        status_html = '<div class="alert alert-success">Evaluation status: <strong>Complete</strong></div>'
    else:
        issues = status.get("issues")
        details = ""
        if isinstance(issues, list) and issues:
            details = '<ul class="mb-0 mt-2">' + "".join(f"<li>{html_lib.escape(str(issue))}</li>" for issue in issues) + "</ul>"
        status_html = (
            '<div class="alert alert-warning" role="alert">Evaluation status: <strong>Incomplete</strong>. '
            f"Finish the evaluation before publishing.{details}</div>"
        )

    fields = [
        ("Evaluator ID", manifest.get("evaluator_id") or "ID missing"),
        ("Sessions (including branches)", manifest.get("total_sessions")),
        ("PC turns", manifest.get("total_turns")),
    ]
    metadata = "".join(
        f'<dt class="col-sm-4">{label}</dt><dd class="col-sm-8">{html_lib.escape(str(value))}</dd>'
        for label, value in fields
        if value is not None
    )
    summary = manifest.get("evaluation_summary")
    summary_html = html_lib.escape(summary) if isinstance(summary, str) and summary.strip() else "No written summary provided."
    return (
        f'{status_html}<div class="card"><div class="card-body">'
        f'<dl class="row dl-meta">{metadata}</dl>'
        '<h3 class="h6">Evaluator summary</h3>'
        f'<p class="mb-0" style="white-space: pre-wrap;">{summary_html}</p></div></div>'
    )


def build_character_quality_report(hid: str, data: AnalysisData) -> str:
    """Build a standalone per-character quality HTML report for the given NPC HID."""
    from dcs_simulation_engine.reporting.auto.rendering.html_builder import build_html
    from dcs_simulation_engine.reporting.auto.sections import event_log, player_feedback, quality_coverage

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
        player_forms_df=data.player_forms_df,
        transcripts_df=_filter(data.transcripts_df),
        assignments_df=data.assignments_df,
        feedback_df=data.feedback_df,
        event_feedback_df=_filter(data.event_feedback_df),
        logs_df=data.logs_df,
        logs_source=data.logs_source,
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

    # 4. Feedback
    feedback_fragment = player_feedback.render(char_data)

    # 5. Full Event Log
    event_log_fragment = event_log.render(char_data)

    # --- Assemble ---
    sections = [
        ("metadata", "Metadata", metadata_fragment, "top"),
        ("overview", "Overview", overview_fragment, "top"),
        ("coverage", "Coverage", quality_coverage.render(char_data), "top"),
        ("feedback", "Feedback", feedback_fragment, "top"),
        ("event-log", "Full Event Log", event_log_fragment, "top"),
    ]
    if summary_fragment := render_evaluation_summary(data):
        sections.insert(0, ("evaluation-summary", "Summary", summary_fragment, "top"))

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
