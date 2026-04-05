"""Character coverage report — overview section.

Renders two coverage score cards:
  - Non-human coverage score: fraction of dimension pairing combinations
    (substrate × size, common_labels × form) that have at least one character.
  - Human coverage score: fraction of HSN ability assumptions that have at
    least one divergent human character.
"""

import json
from pathlib import Path

from analysis.auto.sections.coverage_shared import (
    human_score,
    nonhuman_score,
    _score_color,
)


def render(repo_root: Path, hids_filter: list[str] | None = None, db: str = "prod") -> str:
    chars_path = repo_root / "database_seeds" / db / "characters.json"
    chars_raw: list[dict] = json.loads(chars_path.read_text(encoding="utf-8"))

    if hids_filter:
        chars_raw = [c for c in chars_raw if c["hid"] in hids_filter]

    nonhuman = [c for c in chars_raw if not c.get("is_human") and c.get("dimensions")]
    human = [c for c in chars_raw if c.get("is_human") and c.get("hsn_divergence")]

    nh_score, nh_detail = nonhuman_score(nonhuman)
    h_score, h_detail = human_score(human)

    nh_pct = f"{nh_score:.0%}"
    nh_color = _score_color(nh_score)
    h_pct = f"{h_score:.0%}"
    h_color = _score_color(h_score)

    return f"""
<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Non-human Coverage</h5>
        <p class="display-6 fw-bold mb-2" style="color:{nh_color};">{nh_pct}</p>
        <p class="text-muted mb-0" style="font-size:0.85rem;">{nh_detail}</p>
      </div>
    </div>
  </div>
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Human Coverage</h5>
        <p class="display-6 fw-bold mb-2" style="color:{h_color};">{h_pct}</p>
        <p class="text-muted mb-0" style="font-size:0.85rem;">{h_detail}</p>
      </div>
    </div>
  </div>
</div>
"""
