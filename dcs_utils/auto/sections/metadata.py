"""Section 1 — Metadata.

Renders a Bootstrap card with key facts about the run and links to raw result
artifacts when available.
"""



import html

from dcs_utils.auto.constants import section_intro
from dcs_utils.common.loader import AnalysisData


def render(data: AnalysisData) -> str:
    run = data.run
    cfg = run.get("config_snapshot") or {}
    games = (cfg.get("assignment_strategy") or {}).get("games") or []
    games_str = ", ".join(games) if games else "—"

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

    pct = f" ({n_assignments_completed / n_assignments:.0%})" if n_assignments else ""
    assignments_str = f"{n_assignments_completed} / {n_assignments}{pct}"

    n_games_played = (
        int(data.runs_df["game_name"].nunique())
        if not data.runs_df.empty and "game_name" in data.runs_df.columns
        else 0
    )

    rows = [
        ("Run",           _esc(run.get("name") or "—")),
        ("Description",   _esc(cfg.get("description") or run.get("description") or "—")),
        ("Players",       str(n_players)),
        ("Games Played",  str(n_games_played)),
        ("Assignments",   assignments_str),
    ]

    dl_items = "".join(
        f"<dt class='col-sm-3'>{label}</dt><dd class='col-sm-9'>{value}</dd>"
        for label, value in rows
    )

    return section_intro("metadata") + f"""
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
