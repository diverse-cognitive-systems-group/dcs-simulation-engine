"""Non-human character dimensional coverage section.

Loads non-human characters from database_seeds/prod/characters.json and
the dimension schema from database_seeds/dev/character_dimensions.json,
then renders:
  - Per-dimension distribution bar charts (10, 2 per row)
  - Coverage heatmap (dimension × option, binary covered/not)
  - Combination gap tables (substrate × size, origin × form)
"""

import json
from pathlib import Path

import pandas as pd

from analysis.auto.rendering.chart_utils import plotly_to_html
from analysis.auto.rendering.table_utils import df_to_datatable
from analysis.auto.sections import coverage_shared


def render(repo_root: Path, hids_filter: list[str] | None = None, db: str = "prod") -> str:
    chars_path = repo_root / "database_seeds" / db / "characters.json"
    dims_path = repo_root / "database_seeds" / "dev" / "character_dimensions.json"

    chars_raw: list[dict] = json.loads(chars_path.read_text(encoding="utf-8"))
    dims_raw: dict = json.loads(dims_path.read_text(encoding="utf-8"))[0]

    nonhuman = [c for c in chars_raw if not c.get("is_human") and c.get("dimensions")]
    if hids_filter:
        nonhuman = [c for c in nonhuman if c["hid"] in hids_filter]

    dim_schema: dict[str, dict] = {
        k: v for k, v in dims_raw["dimensions"].items() if k != "description"
    }

    # Build long-form DataFrame: one row per (hid, dimension_key, value)
    long_rows = []
    for c in nonhuman:
        hid = c["hid"]
        for dk, entry in c["dimensions"].items():
            for v in (entry.get("value") or []):
                long_rows.append({"hid": hid, "dimension": dk, "value": v})
    long_df = pd.DataFrame(long_rows) if long_rows else pd.DataFrame(columns=["hid", "dimension", "value"])

    parts: list[str] = []

    if long_df.empty:
        parts.append('<p class="text-muted">No non-human characters found.</p>')
        return "\n".join(parts)

    parts.append(coverage_shared.nonhuman_score_card(nonhuman))

    parts.append(
        '<p class="text-muted mb-3" style="font-size:0.9rem;">'
        "Coverage of the 10 cognitive dimensions across non-human characters. "
        "Each chart shows how many characters use each category option within that dimension. "
        "The heatmap summarises which options are covered at all, and the gap tables "
        "highlight dimension-pair combinations absent from the current character set."
        "</p>"
    )

    # --- Per-dimension distribution bar charts (2 per row) ---
    parts.append('<h3 class="mt-4 mb-3" style="font-size:1.1rem;">Distribution by Dimension</h3>')
    dim_keys = list(dim_schema.keys())
    for i in range(0, len(dim_keys), 2):
        pair = dim_keys[i : i + 2]
        cols_html = []
        for dk in pair:
            options = dim_schema[dk]["options"]
            if len(options) == 1:
                # Single-option dimension: skip chart, show a note
                used = set(long_df[long_df["dimension"] == dk]["value"])
                note = options[0] if used else f"{options[0]} (no characters assigned)"
                label = dk.replace("_", " ").title()
                col_content = (
                    f'<p class="fw-semibold mb-1" style="font-size:0.9rem;">{label}</p>'
                    f'<p class="text-muted" style="font-size:0.85rem;">'
                    f'Only one category defined: <code>{note}</code>. '
                    f'All {len(long_df[long_df["dimension"] == dk]["hid"].unique())} characters use it.'
                    f"</p>"
                )
            else:
                col_content = _dim_bar_chart(long_df, dk, options)
            cols_html.append(f'<div class="col-md-6 chart-container">{col_content}</div>')
        parts.append(f'<div class="row mb-2">{"".join(cols_html)}</div>')

    # --- Coverage heatmap ---
    parts.append('<h3 class="mt-4 mb-2" style="font-size:1.1rem;">Coverage Heatmap</h3>')
    parts.append(
        '<p class="text-muted mb-2" style="font-size:0.82rem;"><em>'
        "Each cell shows whether that option is represented in at least one non-human character "
        "(blue = covered, white = not covered, grey = not applicable to this dimension)."
        "</em></p>"
    )
    parts.append(_coverage_heatmap(long_df, dim_schema))

    # --- Combination gap tables ---
    parts.append('<h3 class="mt-4 mb-2" style="font-size:1.1rem;">Combination Gaps</h3>')
    parts.append(
        '<p class="text-muted mb-3" style="font-size:0.82rem;"><em>'
        "Pairwise counts of non-human characters covering both category values. "
        "Highlighted rows (zero count) indicate combinations absent from the current set."
        "</em></p>"
    )
    parts.append("<h5>substrate × size</h5>")
    parts.append(_combo_table_html(long_df, "substrate", "size", "combo-substrate-size"))
    parts.append("<h5 class='mt-3'>origin × form</h5>")
    parts.append(_combo_table_html(long_df, "origin", "form", "combo-origin-form"))

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dim_bar_chart(long_df: pd.DataFrame, dk: str, options: list[str]) -> str:
    import plotly.express as px

    ddf = long_df[long_df["dimension"] == dk]
    counts = (
        ddf["value"].value_counts()
        .reindex(options, fill_value=0)
        .rename_axis("value")
        .reset_index(name="count")
    )
    title = dk.replace("_", " ").title()
    fig = px.bar(
        counts,
        x="count",
        y="value",
        orientation="h",
        title=title,
        labels={"value": "", "count": "Characters"},
        color="count",
        color_continuous_scale="Viridis",
    )
    fig.update_layout(
        height=max(260, 40 + len(options) * 26),
        margin={"l": 10, "r": 10, "t": 40, "b": 20},
        coloraxis_showscale=False,
        yaxis={"categoryorder": "total ascending"},
    )
    return plotly_to_html(fig)


def _coverage_heatmap(long_df: pd.DataFrame, dim_schema: dict) -> str:
    import base64
    import io
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import seaborn as sns

    # Collect all unique option values across all dimensions (in schema order)
    all_options: list[str] = []
    seen: set[str] = set()
    for meta in dim_schema.values():
        for opt in meta["options"]:
            if opt not in seen:
                all_options.append(opt)
                seen.add(opt)

    dim_keys = list(dim_schema.keys())
    dim_labels = [dk.replace("_", " ") for dk in dim_keys]

    # Build matrix: rows = options, cols = dimensions
    # 1 = covered, 0 = not covered, NaN = not applicable to that dimension
    matrix = pd.DataFrame(index=all_options, columns=dim_labels, dtype=float)
    for dk, meta in dim_schema.items():
        col = dk.replace("_", " ")
        used = set(long_df[long_df["dimension"] == dk]["value"])
        for opt in all_options:
            if opt in meta["options"]:
                matrix.loc[opt, col] = 1.0 if opt in used else 0.0
            # else: leave as NaN (not applicable)

    n_opts = len(all_options)
    n_dims = len(dim_keys)
    # Width: ~1.2in per dimension column so the image fills the page width at 90 DPI.
    # Height: ~0.15in per option row keeps cells compact.
    fig, ax = plt.subplots(figsize=(max(12, n_dims * 1.2), max(6, n_opts * 0.15)))
    mask = matrix.isna()
    sns.heatmap(
        matrix.fillna(-1),
        mask=mask,
        annot=False,
        cmap="YlGnBu",
        vmin=0,
        vmax=1,
        linewidths=0.3,
        linecolor="#dddddd",
        ax=ax,
        cbar=False,
    )
    # Grey out N/A cells
    sns.heatmap(
        matrix.isna().astype(float),
        mask=~mask,
        annot=False,
        cmap=["#eeeeee"],
        linewidths=0.3,
        linecolor="#dddddd",
        ax=ax,
        cbar=False,
        alpha=0.5,
    )
    ax.set_title("Option Coverage by Dimension (non-human characters)", fontsize=10)
    ax.set_xlabel("")
    ax.set_ylabel("")
    plt.xticks(rotation=30, ha="right", fontsize=8)
    plt.yticks(fontsize=7)
    plt.tight_layout()

    # Save at reduced DPI to keep the image compact in the browser
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=90)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f'<img src="data:image/png;base64,{encoded}" class="img-fluid" alt="coverage heatmap">'


def _combo_table_html(long_df: pd.DataFrame, dim_a: str, dim_b: str, table_id: str) -> str:
    a_vals = sorted(long_df[long_df["dimension"] == dim_a]["value"].unique())
    b_vals = sorted(long_df[long_df["dimension"] == dim_b]["value"].unique())

    rows = []
    for a in a_vals:
        hids_a = set(long_df[(long_df["dimension"] == dim_a) & (long_df["value"] == a)]["hid"])
        for b in b_vals:
            hids_b = set(long_df[(long_df["dimension"] == dim_b) & (long_df["value"] == b)]["hid"])
            count = len(hids_a & hids_b)
            rows.append({dim_a: a, dim_b: b, "count": count})

    if not rows:
        return '<p class="text-muted">No data available for this dimension pair.</p>'
    df = pd.DataFrame(rows).sort_values(["count"], ascending=[True])

    table_html = df_to_datatable(
        df,
        table_id=table_id,
        scroll_y="300px",
        export_buttons=True,
        column_filters=True,
    )

    # Highlight zero-count rows via DataTables createdRow callback
    table_html = table_html.replace(
        "order: [],",
        "order: [],"
        f"\n        createdRow: function(row, data) {{"
        f" if (parseInt(data[2]) === 0) {{ $(row).addClass('table-warning'); }} }},",
    )

    return table_html
