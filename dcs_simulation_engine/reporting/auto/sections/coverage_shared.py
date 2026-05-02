"""Shared scorecard helpers for coverage sections.

Provides score computation and Bootstrap card rendering used by both the
standalone coverage report (coverage_overview) and the embedded coverage
sections in the main report (coverage_human, coverage_nonhuman).
"""

import pandas as pd


def _score_color(score: float) -> str:
    if score >= 0.75:
        return "#198754"  # Bootstrap success green
    if score >= 0.5:
        return "#fd7e14"  # Bootstrap orange
    return "#dc3545"  # Bootstrap danger red


def nonhuman_score(nonhuman: list[dict]) -> tuple[float, str]:
    """Fraction of dimension pair combinations covered (non-zero character count)."""
    if not nonhuman:
        return 0.0, "No non-human characters found."

    long_rows = []
    for c in nonhuman:
        for dk, entry in c["dimensions"].items():
            for v in entry.get("value") or []:
                long_rows.append({"hid": c["hid"], "dimension": dk, "value": v})

    if not long_rows:
        return 0.0, "No dimension data found."

    long_df = pd.DataFrame(long_rows)
    pairs = [("substrate", "size"), ("common_labels", "form")]
    total_combos = 0
    covered_combos = 0
    pair_details: list[str] = []

    for dim_a, dim_b in pairs:
        a_vals = sorted(long_df[long_df["dimension"] == dim_a]["value"].unique())
        b_vals = sorted(long_df[long_df["dimension"] == dim_b]["value"].unique())
        if not a_vals or not b_vals:
            continue
        pair_covered = 0
        for a in a_vals:
            hids_a = set(long_df[(long_df["dimension"] == dim_a) & (long_df["value"] == a)]["hid"])
            for b in b_vals:
                hids_b = set(long_df[(long_df["dimension"] == dim_b) & (long_df["value"] == b)]["hid"])
                if hids_a & hids_b:
                    pair_covered += 1
        pair_total = len(a_vals) * len(b_vals)
        total_combos += pair_total
        covered_combos += pair_covered
        pair_details.append(f"{dim_a}\u00d7{dim_b}: {pair_covered}/{pair_total}")

    if total_combos == 0:
        return 0.0, "No pairing data available."

    score = covered_combos / total_combos
    detail = (
        f"Dimension pair combination coverage: {covered_combos} of {total_combos} "
        f"combinations have at least one character "
        f"({', '.join(pair_details)})."
    )
    return score, detail


def human_score(human: list[dict]) -> tuple[float, str]:
    """Fraction of HSN ability assumptions covered by at least one divergent character."""
    if not human:
        return 0.0, "No human characters with HSN divergence data found."

    long_rows = []
    for c in human:
        for category, abilities in c["hsn_divergence"].items():
            for ability, data in abilities.items():
                long_rows.append(
                    {
                        "hid": c["hid"],
                        "ability": ability,
                        "value": data["value"],
                    }
                )

    long_df = pd.DataFrame(long_rows)
    all_abilities = long_df["ability"].unique()
    total = len(all_abilities)
    covered = int(long_df[long_df["value"] == "divergent"]["ability"].nunique())

    score = covered / total if total > 0 else 0.0
    detail = f"HSN assumption coverage: {covered} of {total} ability assumptions have at least one divergent human character."
    return score, detail


def nonhuman_score_card(nonhuman: list[dict]) -> str:
    """Bootstrap card summarising non-human dimension combination coverage."""
    score, detail = nonhuman_score(nonhuman)
    pct = f"{score:.0%}"
    color = _score_color(score)
    return f"""
<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Non-human Coverage</h5>
        <p class="display-6 fw-bold mb-2" style="color:{color};">{pct}</p>
        <p class="text-muted mb-0" style="font-size:0.85rem;">{detail}</p>
      </div>
    </div>
  </div>
</div>
"""


def human_score_card(human: list[dict]) -> str:
    """Bootstrap card summarising human HSN divergence coverage."""
    score, detail = human_score(human)
    pct = f"{score:.0%}"
    color = _score_color(score)
    return f"""
<div class="row g-3 mb-4">
  <div class="col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <h5 class="card-title">Human Coverage</h5>
        <p class="display-6 fw-bold mb-2" style="color:{color};">{pct}</p>
        <p class="text-muted mb-0" style="font-size:0.85rem;">{detail}</p>
      </div>
    </div>
  </div>
</div>
"""
