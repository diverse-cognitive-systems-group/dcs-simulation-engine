"""Character dev specific helper functions."""

import json
import math

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from notebooks.helpers import message


def build_character_context(characters_df, characters_abilities_df, hid):
    """Build a context dictionary for a character, including their attributes and abilities."""
    char_row = characters_df.loc[characters_df["hid"] == hid].iloc[0]

    ability_rows = characters_abilities_df.loc[characters_abilities_df["hid"] == hid, ["ability_category", "ability"]]

    abilities_by_category = {}
    for _, row in ability_rows.iterrows():
        abilities_by_category.setdefault(row["ability_category"], []).append(row["ability"])

    return {
        "hid": hid,
        "short_description": char_row["short_description"],
        "long_description": char_row["long_description"],
        "abilities": abilities_by_category,
    }


def classify_all_hsn_abilities_for_character(
    character_context,
    hsn_abilities_df,
):
    """Classify every HSN ability for a character as "normative" or "divergent"."""
    hsn_items = hsn_abilities_df[["category", "assumption", "description"]].to_dict(orient="records")

    system_prompt = """
You are classifying whether a character satisfies a human normative baseline ability.

You must classify EVERY HSN ability as either:
- "normative"
- "divergent"

Decision rule:
- "normative" = the character can perform or satisfy the assumption in a way that fits the assumption.
- "divergent" = the character cannot perform it, can only partially perform it, performs it unreliably, fluctuates too much, or requires significant adaptation such that the baseline assumption does not hold.

Important:
- Judge against the baseline assumption itself, not whether the character can compensate in another way.
- If evidence is insufficient or ambiguous, prefer "divergent".
- Return JSON only.
- Return one result for every HSN ability.

Return this exact schema:
{
  "results": [
    {
      "hsn_category": "...",
      "hsn_assumption": "...",
      "score": "normative" or "divergent",
      "reason": "brief explanation"
    }
  ]
}
""".strip()

    user_prompt = f"""
Character:
{json.dumps(character_context, indent=2, default=str)}

HSN baseline abilities:
{json.dumps(hsn_items, indent=2)}

Classify every HSN ability for this character.
Return JSON only.
""".strip()

    raw = message(
        user_prompt,
        system_prompt=system_prompt,
        parse_response=True,
        # temperature=0,
    ).strip()

    if raw.startswith("```"):
        raw = raw.strip()
        if raw.startswith("```json"):
            raw = raw[len("```json") :].strip()
        elif raw.startswith("```"):
            raw = raw[len("```") :].strip()
        if raw.endswith("```"):
            raw = raw[:-3].strip()

    parsed = json.loads(raw)
    return parsed["results"]


def build_hsn_divergence_df(
    characters_df,
    characters_abilities_df,
    hsn_abilities_df,
):
    """Build a DataFrame where each row is a character x HSN ability, with columns for the character's hid, the HSN category and assumption, and the classification result (normative/divergent) and reason."""
    rows = []

    for hid in characters_df["hid"].tolist():
        character_context = build_character_context(
            characters_df=characters_df,
            characters_abilities_df=characters_abilities_df,
            hid=hid,
        )

        results = classify_all_hsn_abilities_for_character(
            character_context=character_context,
            hsn_abilities_df=hsn_abilities_df,
        )

        result_map = {(r["hsn_category"], r["hsn_assumption"]): r for r in results}

        for _, hsn_row in hsn_abilities_df.iterrows():
            key = (hsn_row["category"], hsn_row["assumption"])
            result = result_map.get(key, {})

            rows.append(
                {
                    "hid": hid,
                    "hsn_category": hsn_row["category"],
                    "hsn_assumption": hsn_row["assumption"],
                    "hsn_description": hsn_row["description"],
                    "score": result.get("score", "divergent"),
                    "reason": result.get("reason", "No result returned for this ability."),
                }
            )

    return pd.DataFrame(rows)


def plot_character_divergence_fingerprints(
    hsn_divergence_df,
    hids,
    hid_col="hid",
    category_col="hsn_category",
    score_col="score",
    figsize_per_row=(12, 4),
):
    """Plot radar divergence fingerprints for multiple characters."""
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()
    df["is_divergent"] = (df[score_col] == "divergent").astype(int)

    n = len(hids)
    ncols = 2
    nrows = math.ceil(n / ncols)

    fig_width = figsize_per_row[0] * ncols
    fig_height = figsize_per_row[1] * nrows

    fig, axes = plt.subplots(
        nrows=nrows,
        ncols=ncols,
        figsize=(fig_width, fig_height),
        subplot_kw={"polar": True},
    )

    if nrows == 1:
        axes = np.array([axes])

    axes = axes.flatten()

    results = {}

    for idx, hid in enumerate(hids):
        ax = axes[idx]

        char_df = df.loc[df[hid_col] == hid]

        grouped = char_df.groupby(category_col, as_index=False).agg(
            divergent_count=("is_divergent", "sum"),
            total_count=("is_divergent", "size"),
        )

        grouped["divergence_rate"] = grouped["divergent_count"] / grouped["total_count"]

        grouped = grouped.sort_values(category_col)

        categories = grouped[category_col].tolist()
        values = grouped["divergence_rate"].tolist()

        angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()

        values += values[:1]
        angles += angles[:1]

        ax.plot(angles, values, linewidth=2)
        ax.fill(angles, values, alpha=0.25)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories)

        ax.set_ylim(0, 1)

        ax.set_title(hid, pad=15)

        results[hid] = grouped

    # hide unused axes
    for i in range(len(hids), len(axes)):
        axes[i].set_visible(False)

    plt.tight_layout()
    plt.show()

    return results


def plot_character_divergence_fingerprint(
    hsn_divergence_df,
    hid,
    hid_col="hid",
    category_col="hsn_category",
    score_col="score",
    figsize=(7, 7),
    title=None,
):
    """Plot a radar chart showing one character's divergence profile across HSN categories.

    Value on each axis =
        divergent_count_in_category / total_count_in_category
    """
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()

    char_df = df.loc[df[hid_col] == hid].copy()
    if char_df.empty:
        raise ValueError(f"No rows found for hid={hid!r}")

    char_df["is_divergent"] = (char_df[score_col] == "divergent").astype(int)

    category_df = char_df.groupby(category_col, as_index=False).agg(
        divergent_count=("is_divergent", "sum"),
        total_count=("is_divergent", "size"),
    )
    category_df["divergence_rate"] = category_df["divergent_count"] / category_df["total_count"]

    category_df = category_df.sort_values(category_col).reset_index(drop=True)

    categories = category_df[category_col].tolist()
    values = category_df["divergence_rate"].tolist()

    # close the loop
    angles = np.linspace(0, 2 * np.pi, len(categories), endpoint=False).tolist()
    angles += angles[:1]
    values += values[:1]

    fig, ax = plt.subplots(figsize=figsize, subplot_kw={"polar": True})

    ax.plot(angles, values, linewidth=2)
    ax.fill(angles, values, alpha=0.25)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories)

    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"])

    ax.set_title(title or f"Character Divergence Fingerprint: {hid}", pad=20)

    plt.tight_layout()
    plt.show()

    return category_df


def plot_most_violated_hsn_assumptions(
    hsn_divergence_df,
    assumption_col="hsn_assumption",
    score_col="score",
    figsize=(12, 8),
    title="Most Violated HSN Assumptions",
    top_n=None,
):
    """Plot how many characters are divergent for each HSN assumption."""
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()

    violated_df = (
        df.assign(is_divergent=(df[score_col] == "divergent").astype(int))
        .groupby(assumption_col, as_index=False)
        .agg(divergent_count=("is_divergent", "sum"))
        .sort_values("divergent_count", ascending=False)
        .reset_index(drop=True)
    )

    if top_n is not None:
        violated_df = violated_df.head(top_n)

    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.barh(violated_df[assumption_col], violated_df["divergent_count"])

    ax.set_title(title)
    ax.set_xlabel("Number of characters marked divergent")
    ax.set_ylabel("HSN assumption")
    ax.invert_yaxis()

    for bar, val in zip(bars, violated_df["divergent_count"]):
        ax.text(
            val + 0.05,
            bar.get_y() + bar.get_height() / 2,
            str(val),
            va="center",
        )

    plt.tight_layout()
    plt.show()

    return violated_df


def plot_character_category_divergence_heatmap(
    hsn_divergence_df,
    hid_col="hid",
    category_col="hsn_category",
    score_col="score",
    figsize=(10, 6),
    title="Character × Category Divergence Heatmap",
    annotate=True,
):
    """Heatmap of divergence proportion within each HSN category for each character.

    Cell value =
        divergent_count_in_category / total_count_in_category
    """
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()
    df["is_divergent"] = (df[score_col] == "divergent").astype(int)

    grouped = df.groupby([hid_col, category_col], as_index=False).agg(
        divergent_count=("is_divergent", "sum"),
        total_count=("is_divergent", "size"),
    )

    grouped["divergence_rate"] = grouped["divergent_count"] / grouped["total_count"]

    matrix = grouped.pivot(index=hid_col, columns=category_col, values="divergence_rate").fillna(0)

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(matrix.values, aspect="auto", vmin=0, vmax=1)

    ax.set_title(title)
    ax.set_xlabel("HSN Category")
    ax.set_ylabel("Character")

    ax.set_xticks(range(len(matrix.columns)))
    ax.set_xticklabels(matrix.columns, rotation=45, ha="right")

    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)

    if annotate:
        for i in range(matrix.shape[0]):
            for j in range(matrix.shape[1]):
                val = matrix.iloc[i, j]
                ax.text(
                    j,
                    i,
                    f"{val:.2f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                )

    cbar = plt.colorbar(im)
    cbar.set_label("Proportion divergent")

    plt.tight_layout()
    plt.show()

    return matrix


def plot_character_hsn_ability_clustermap(
    hsn_divergence_df,
    hid_col="hid",
    ability_col="hsn_assumption",
    score_col="score",
    figsize=(18, 10),
    title="Character × HSN Ability Divergence Clustermap",
    cmap="Greys",
):
    """Clustered heatmap showing which HSN abilities each character satisfies or diverges from.

    - rows: characters
    - columns: HSN abilities
    - value: normative=0, divergent=1

    Clustering groups characters and assumptions with similar divergence patterns.
    """
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()

    score_map = {"normative": 0, "divergent": 1}
    df["score_numeric"] = df[score_col].map(score_map)

    matrix = df.pivot(index=hid_col, columns=ability_col, values="score_numeric")

    g = sns.clustermap(
        matrix,
        cmap=cmap,
        linewidths=0.5,
        linecolor="white",
        vmin=0,
        vmax=1,
        figsize=figsize,
        cbar_kws={"label": "Classification"},
    )

    g.fig.suptitle(title, y=1.02)

    # label cleanup
    plt.setp(g.ax_heatmap.get_xticklabels(), rotation=75, ha="right")
    plt.setp(g.ax_heatmap.get_yticklabels(), rotation=0)

    # nicer colorbar labels
    cbar = g.ax_heatmap.collections[0].colorbar
    cbar.set_ticks([0.25, 0.75])
    cbar.set_ticklabels(["normative", "divergent"])

    plt.show()

    return matrix


def plot_character_hsn_ability_heatmap(
    hsn_divergence_df,
    hid_col="hid",
    ability_col="hsn_assumption",
    score_col="score",
    figsize=(18, 8),
    title="Character × HSN Ability Divergence Map",
    annotate=False,
):
    """Heatmap showing which HSN abilities each character satisfies or diverges from."""
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()

    score_map = {"normative": 0, "divergent": 1}
    df["score_numeric"] = df[score_col].map(score_map)

    matrix = df.pivot(index=hid_col, columns=ability_col, values="score_numeric")

    plt.figure(figsize=figsize)

    sns.heatmap(
        matrix,
        cmap="Greys",
        linewidths=0.5,
        linecolor="white",
        cbar=True,
        vmin=0,
        vmax=1,
        annot=annotate,
    )

    plt.title(title)
    plt.xlabel("HSN Ability")
    plt.ylabel("Character")

    plt.xticks(rotation=75, ha="right")
    plt.yticks(rotation=0)

    cbar = plt.gca().collections[0].colorbar
    cbar.set_ticks([0.25, 0.75])
    cbar.set_ticklabels(["normative", "divergent"])

    plt.tight_layout()
    plt.show()

    return matrix


def plot_divergence_distribution(
    hsn_divergence_df,
    hid_col="hid",
    score_col="score",
    bins=10,
    figsize=(9, 6),
    title="Divergence Distribution",
):
    """Plot a histogram of character-level divergence scores.

    Divergence score =
        divergent_count / total_count
    """
    df = hsn_divergence_df.copy()
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()
    df["is_divergent"] = (df[score_col] == "divergent").astype(int)

    score_df = df.groupby(hid_col, as_index=False).agg(
        divergent_count=("is_divergent", "sum"),
        total_count=("is_divergent", "size"),
    )

    score_df["divergence_score"] = score_df["divergent_count"] / score_df["total_count"]

    fig, ax = plt.subplots(figsize=figsize)
    ax.hist(score_df["divergence_score"], bins=bins)

    ax.set_title(title)
    ax.set_xlabel("Divergence score")
    ax.set_ylabel("Number of characters")
    ax.set_xlim(0, 1)

    plt.tight_layout()
    plt.show()

    return score_df


def plot_divergence_score_ranking(
    hsn_divergence_df,
    hid_col="hid",
    score_col="score",
    divergent_label="divergent",
    normative_label="normative",
    figsize=(10, 6),
    title="Divergence Score Ranking",
    annotate=True,
):
    """Plot divergence score for each character."""
    df = hsn_divergence_df.copy()

    # basic cleanup
    df[score_col] = df[score_col].astype(str).str.strip().str.lower()
    df[hid_col] = df[hid_col].astype(str)

    valid_scores = {divergent_label.lower(), normative_label.lower()}
    invalid = df.loc[~df[score_col].isin(valid_scores), score_col].unique()
    if len(invalid) > 0:
        raise ValueError(f"Unexpected score values found: {list(invalid)}")

    score_df = (
        df.assign(is_divergent=(df[score_col] == divergent_label.lower()).astype(int))
        .groupby(hid_col, as_index=False)
        .agg(
            divergent_count=("is_divergent", "sum"),
            total_count=("is_divergent", "size"),
        )
    )

    score_df["normative_count"] = score_df["total_count"] - score_df["divergent_count"]
    score_df["divergence_score"] = score_df["divergent_count"] / score_df["total_count"]
    score_df = score_df.sort_values("divergence_score", ascending=False).reset_index(drop=True)

    # plot
    fig, ax = plt.subplots(figsize=figsize)
    bars = ax.bar(score_df[hid_col], score_df["divergence_score"])

    ax.set_title(title)
    ax.set_xlabel("Character")
    ax.set_ylabel("Divergence score")
    ax.set_ylim(0, 1)
    plt.xticks(rotation=45, ha="right")

    if annotate:
        for bar, val in zip(bars, score_df["divergence_score"]):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{val:.2f}",
                ha="center",
                va="bottom",
                fontsize=9,
            )

    plt.tight_layout()
    plt.show()

    return score_df
