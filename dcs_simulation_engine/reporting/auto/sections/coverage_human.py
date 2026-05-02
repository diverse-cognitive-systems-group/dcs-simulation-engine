"""Human character HSN divergence coverage section.

Loads human characters from database_seeds/prod/characters.json and renders:
  - HSN divergence heatmap (character × ability assumption, normative/divergent)
  - Divergent assumption count per character (sorted bar chart)
"""

import json
from pathlib import Path

import pandas as pd

from dcs_utils.auto.rendering.chart_utils import matplotlib_to_base64, plotly_to_html
from dcs_utils.auto.sections import coverage_shared


def render(repo_root: Path, hids_filter: list[str] | None = None, db: str = "prod") -> str:
    chars_path = repo_root / "database_seeds" / db / "characters.json"
    chars_raw: list[dict] = json.loads(chars_path.read_text(encoding="utf-8"))

    human = [c for c in chars_raw if c.get("is_human") and c.get("hsn_divergence")]
    if hids_filter:
        human = [c for c in human if c["hid"] in hids_filter]

    parts: list[str] = []

    if not human:
        parts.append('<p class="text-muted">No human characters with HSN divergence data found.</p>')
        return "\n".join(parts)

    parts.append(coverage_shared.human_score_card(human))

    # Build HID → display label mapping: "HID (first common label)"
    def _display_label(c: dict) -> str:
        labels = c.get("common_labels") or []
        first = labels[0] if labels else None
        return f"{c['hid']} ({first})" if first else c["hid"]

    hid_label = {c["hid"]: _display_label(c) for c in human}

    # Build long-form DataFrame
    long_rows = []
    for c in human:
        label = hid_label[c["hid"]]
        for category, abilities in c["hsn_divergence"].items():
            for ability, data in abilities.items():
                long_rows.append({
                    "hid": label,
                    "category": category,
                    "ability": ability,
                    "value": data["value"],  # "normative" | "divergent"
                })
    long_df = pd.DataFrame(long_rows)

    parts.append(
        '<p class="text-muted mb-3" style="font-size:0.9rem;">'
        "HSN (Human Standard Normal) divergence scores each human character against "
        "the ability assumptions embedded in the scenario design. "
        "Red cells indicate the character diverges from the normative assumption; "
        "blue cells indicate normative behaviour. "
        "Characters are ordered from least to most divergent."
        "</p>"
    )

    # --- Heatmap ---
    parts.append('<h3 class="mt-3 mb-2" style="font-size:1.1rem;">HSN Divergence Heatmap</h3>')
    parts.append(_hsn_heatmap(long_df))
    parts.append(
        '<p class="text-muted mt-1 mb-4" style="font-size:0.82rem;"><em>'
        "Rows = human characters (HID); columns = individual ability assumptions grouped by category. "
        "Red = divergent, blue = normative."
        "</em></p>"
    )

    # --- Bar chart ---
    parts.append('<h3 class="mt-3 mb-2" style="font-size:1.1rem;">Divergent Assumptions per Character</h3>')
    parts.append(_divergence_bar(long_df))
    parts.append(
        '<p class="text-muted mt-1 mb-3" style="font-size:0.82rem;"><em>'
        "Count of ability assumptions where each character diverges from the normative baseline, "
        "sorted from most to least divergent."
        "</em></p>"
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hsn_heatmap(long_df: pd.DataFrame) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    # Build pivot: rows=hid, cols=ability (ordered by category then name)
    col_order = (
        long_df[["category", "ability"]]
        .drop_duplicates()
        .sort_values(["category", "ability"])["ability"]
        .tolist()
    )

    pivot = long_df.pivot_table(
        index="hid",
        columns="ability",
        values="value",
        aggfunc=lambda s: 1 if "divergent" in s.values else 0,
    ).fillna(0).astype(int)

    # Reorder columns
    col_order = [c for c in col_order if c in pivot.columns]
    pivot = pivot[col_order]

    # Sort rows: least divergent at top, most at bottom
    row_order = pivot.sum(axis=1).sort_values(ascending=True).index
    pivot = pivot.loc[row_order]

    n_rows, n_cols = pivot.shape
    fig, ax = plt.subplots(figsize=(max(14, n_cols * 0.55), max(5, n_rows * 0.38)))
    sns.heatmap(
        pivot,
        annot=False,
        cmap=["#aec6cf", "#c0392b"],
        vmin=0,
        vmax=1,
        linewidths=0.3,
        linecolor="#eeeeee",
        ax=ax,
        cbar=False,
    )
    ax.set_title(
        "Human Characters × HSN Ability Assumptions  (red = divergent, blue = normative)",
        fontsize=10,
    )
    ax.set_xlabel("")
    ax.set_ylabel("Character (HID)", fontsize=9)
    plt.xticks(rotation=40, ha="right", fontsize=7)
    plt.yticks(fontsize=8)
    plt.tight_layout()
    return matplotlib_to_base64(fig)


def _divergence_bar(long_df: pd.DataFrame) -> str:
    import plotly.express as px

    div_counts = (
        long_df[long_df["value"] == "divergent"]
        .groupby("hid")
        .size()
        .reset_index(name="divergent_count")
    )
    all_hids = long_df["hid"].unique()
    full = (
        pd.DataFrame({"hid": all_hids})
        .merge(div_counts, on="hid", how="left")
        .fillna(0)
    )
    full["divergent_count"] = full["divergent_count"].astype(int)
    full = full.sort_values("divergent_count", ascending=False)

    fig = px.bar(
        full,
        x="hid",
        y="divergent_count",
        title="Divergent HSN Assumptions per Character",
        labels={"hid": "Character (HID)", "divergent_count": "# Divergent Assumptions"},
        color="divergent_count",
        color_continuous_scale="Reds",
    )
    fig.update_layout(
        height=350,
        margin={"l": 20, "r": 20, "t": 40, "b": 60},
        coloraxis_showscale=False,
    )
    return plotly_to_html(fig)
