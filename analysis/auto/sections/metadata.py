"""Section 1 — Metadata Summary.

Renders a Bootstrap card with key facts about the experiment and the
results directory: experiment name, description, DB info, run/player
counts, and report generation timestamp.
"""

from __future__ import annotations

import html

from analysis.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    exp = data.experiment
    cfg = exp.get("config_snapshot") or {}
    strategy = (cfg.get("assignment_strategy") or {}).get("strategy", "—")
    games = (cfg.get("assignment_strategy") or {}).get("games") or []
    games_str = ", ".join(games) if games else "—"
    condition = cfg.get("condition") or "—"

    created_at = data.manifest.get("created_at") or "—"
    db_name = data.manifest.get("db_name") or "—"

    n_runs = len(data.runs_df)
    n_players = len(data.players_df)
    n_assignments = len(data.assignments_df)
    n_events = len(data.transcripts_df)
    n_characters = len(data.characters_df)

    # Duration stats
    dur_info = ""
    if not data.runs_df.empty and "duration_minutes" in data.runs_df.columns:
        valid = data.runs_df["duration_minutes"].dropna()
        if not valid.empty:
            dur_info = (
                f"{valid.min():.1f} – {valid.max():.1f} min "
                f"(mean {valid.mean():.1f} min)"
            )

    rows = [
        ("Experiment", _esc(exp.get("name") or "—")),
        ("Description", _esc(cfg.get("description") or exp.get("description") or "—")),
        ("Condition", _esc(condition)),
        ("Assignment strategy", _esc(strategy)),
        ("Games", _esc(games_str)),
        ("DB name", _esc(db_name)),
        ("Exported at", _esc(str(created_at))),
        ("Results directory", f"<code>{_esc(str(data.results_dir))}</code>"),
        ("Runs (sessions)", str(n_runs)),
        ("Players", str(n_players)),
        ("Assignments", str(n_assignments)),
        ("Session events", str(n_events)),
        ("Characters available", str(n_characters)),
    ]
    if dur_info:
        rows.append(("Run duration range", _esc(dur_info)))

    dl_items = "".join(
        f"<dt class='col-sm-3'>{label}</dt><dd class='col-sm-9'>{value}</dd>"
        for label, value in rows
    )

    return f"""
<div class="card">
  <div class="card-body">
    <dl class="row dl-meta mb-0">
      {dl_items}
    </dl>
  </div>
</div>
"""


def _esc(s: str) -> str:
    return html.escape(str(s))
