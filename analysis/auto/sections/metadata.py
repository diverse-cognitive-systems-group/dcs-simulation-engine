"""Section 1 — Metadata.

Renders a Bootstrap card with key facts about the experiment and links to
raw result artifacts when available.
"""

from __future__ import annotations

import html
from pathlib import Path

from analysis.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    exp = data.experiment
    cfg = exp.get("config_snapshot") or {}
    strategy = (cfg.get("assignment_strategy") or {}).get("strategy", "—")
    games = (cfg.get("assignment_strategy") or {}).get("games") or []
    games_str = ", ".join(games) if games else "—"
    condition = cfg.get("condition") or "—"

    n_runs = len(data.runs_df)
    n_players = len(data.players_df)
    n_assignments = len(data.assignments_df)
    if not data.assignments_df.empty:
        if "status" in data.assignments_df.columns:
            n_assignments_completed = int(
                data.assignments_df["status"].fillna("").eq("completed").sum()
            )
        elif "completed_at" in data.assignments_df.columns:
            n_assignments_completed = int(data.assignments_df["completed_at"].notna().sum())
        else:
            n_assignments_completed = 0
    else:
        n_assignments_completed = 0

    # Duration stats
    dur_info = ""
    if not data.runs_df.empty and "duration_minutes" in data.runs_df.columns:
        valid = data.runs_df["duration_minutes"].dropna()
        if not valid.empty:
            dur_info = (
                f"{valid.min():.1f} – {valid.max():.1f} min "
                f"(mean {valid.mean():.1f} min)"
            )

    raw_results_link = _artifact_link(
        data.results_dir.with_suffix('.zip'),
        label='raw results (.zip)',
        placeholder='Raw results (.zip)'
    )
    run_config_link = _artifact_link(
        data.results_dir / 'run_config.yml',
        label='run_config.yml',
        placeholder='run_config.yml'
    )

    rows = [
        ("Experiment", _esc(exp.get("name") or "—")),
        ("Description", _esc(cfg.get("description") or exp.get("description") or "—")),
        ("Condition", _esc(condition)),
        ("Assignment strategy", _esc(strategy)),
        ("Games", _esc(games_str)),
        ("Raw results", raw_results_link),
        ("Run config", run_config_link),
        ("Players", str(n_players)),
        ("Gameplay sessions", str(n_runs)),
        ("Assignments", f"{n_assignments_completed} / {n_assignments}"),
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


def _artifact_link(path: Path, *, label: str, placeholder: str) -> str:
    if path.exists():
        return f'<a href="{_esc(path.as_uri())}">{_esc(label)}</a>'
    return f'<a href="#" class="text-muted">{_esc(placeholder)}</a>'


def _esc(s: str) -> str:
    return html.escape(str(s))
