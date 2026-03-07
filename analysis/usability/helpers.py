"""Usability specific helper functions."""

import json
import textwrap

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib.ticker import MaxNLocator

from analysis.helpers import message

FEEDBACK_THEME_SYSTEM_PROMPT = """
You are a careful qualitative research assistant.

Your task is to identify feedback themes from a single game run's feedback item, using:
- the feedback source
- the feedback text
- the question text if available
- the player character (pc)
- the non-player character (npc)
- the transcript / interaction history

Your job is NOT to summarize the whole run. Your job is to classify the feedback itself.

Instructions:
1. Focus primarily on the user's feedback_text.
2. Use transcript and character context only to interpret ambiguity.
3. Distinguish between:
   - literal surface complaint/praise
   - likely underlying theme
   - whether the issue is about gameplay, difficulty, realism, character consistency, accessibility, clarity, UX, pacing, or something else
4. Do not over-interpret. If evidence is weak, say so.
5. If the text is not actually feedback (for example a goal inference answer), mark that clearly.
6. Prefer a small number of precise themes over many vague ones.
7. Be robust to typos and short answers.
8. Return valid JSON only. No markdown. No extra commentary.

Return JSON with exactly this schema:
{
  "is_feedback": true,
  "confidence": 0.0,
  "primary_theme": "string",
  "secondary_themes": ["string"],
  "sentiment": "negative|mixed|neutral|positive",
  "specificity": "high|medium|low",
  "actionability": "high|medium|low",
  "theme_rationale": "string",
  "evidence": {
    "feedback_text_cues": ["string"],
    "transcript_cues": ["string"]
  },
  "tags": ["string"],
  "suggested_label": "string"
}

Theme guidance:
- difficulty_too_easy
- difficulty_too_hard
- out_of_character
- unrealistic_behavior
- goal_too_obvious
- goal_too_unclear
- accessibility_barrier
- instruction_clarity
- immersion
- pacing
- interface_or_ux
- character_consistency
- communication_modality
- inclusivity_or_representation
- no_actionable_feedback
- other

Tag guidance:
Use short snake_case tags, such as:
["too_easy", "explicit_goal", "npc_broke_character", "asl_interaction", "accessibility", "immersion"]

Interpretation rules:
- If feedback says things like "too easy", "obvious", "gave it away", prefer difficulty_too_easy or goal_too_obvious.
- If feedback says things like "out of character", "didn't fit", "broke the role", prefer out_of_character or character_consistency.
- If the feedback item is actually an answer to a study question rather than evaluative feedback, set is_feedback=false and use primary_theme="no_actionable_feedback".
- Confidence should reflect how strongly the text supports the classification.
- Keep theme_rationale concise but specific.
""".strip()


def identify_feedback_theme(feedback_row):
    """Ask an LLM to identify the theme of a single feedback item.

    Expected input:
      feedback_row: dict-like object with fields such as
        - feedback_source
        - feedback_text
        - question_text
        - pc_hid / pc_description
        - npc_hid / npc_description
        - transcript
        - run_id
        - player_id

    Returns parsed JSON if possible, otherwise raw text from message().
    """

    def _get(obj, key, default=None):
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    transcript = _get(feedback_row, "transcript", [])
    if transcript is None:
        transcript = []

    # Keep transcript compact but informative
    transcript_min = []
    if isinstance(transcript, list):
        for turn in transcript:
            if isinstance(turn, dict):
                transcript_min.append(
                    {
                        "type": turn.get("type"),
                        "content": turn.get("content"),
                    }
                )
            else:
                transcript_min.append(str(turn))

    payload = {
        "run_id": _get(feedback_row, "run_id"),
        "player_id": _get(feedback_row, "player_id"),
        "feedback_source": _get(feedback_row, "feedback_source"),
        "feedback_key": _get(feedback_row, "feedback_key"),
        "feedback_text": _get(feedback_row, "feedback_text"),
        "question_text": _get(feedback_row, "question_text"),
        "pc": {
            "hid": _get(feedback_row, "pc_hid"),
            "description": _get(feedback_row, "pc_description"),
        },
        "npc": {
            "hid": _get(feedback_row, "npc_hid"),
            "description": _get(feedback_row, "npc_description"),
        },
        "transcript": transcript_min,
    }

    user_msg = textwrap.dedent(
        f"""
        Identify the feedback theme for this single feedback item.

        Analyze the feedback in context and return JSON only.

        {json.dumps(payload, ensure_ascii=False, indent=2)}
        """
    ).strip()

    raw = message(
        user_msg,
        system_prompt=FEEDBACK_THEME_SYSTEM_PROMPT,
        parse_response=True,
    )

    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    return raw


def identify_feedback_themes_df(feedback_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in feedback_df.iterrows():
        result = identify_feedback_theme(row.to_dict())
        rows.append(
            {
                "run_id": row.get("run_id"),
                "feedback_source": row.get("feedback_source"),
                "feedback_key": row.get("feedback_key"),
                "feedback_text": row.get("feedback_text"),
                "theme_result": result,
            }
        )
    return pd.DataFrame(rows)


def plot_play_time_distribution(runs_df, bins=30):
    """Plot distribution of play times (seconds)."""
    df = runs_df.copy()

    plt.figure()
    df["runtime_seconds"].dropna().plot(kind="hist", bins=bins)

    plt.xlabel("Play Time (seconds)")
    plt.ylabel("Count")
    plt.title("Play Time Distribution")

    plt.show()


def plot_playtime_over_time(runs_df):
    """Plot play time (seconds) over start time."""
    df = runs_df.copy()
    df["start_dt"] = pd.to_datetime(df["start_dt"])

    plt.figure()
    plt.scatter(df["start_dt"], df["runtime_seconds"])

    plt.xlabel("Start Time")
    plt.ylabel("Play Time (seconds)")
    plt.title("Play Time Over Time")

    plt.show()


def plot_engagement_by(players_engagement_df, column, max_categories=20):
    """Plot total runs grouped by a selected player column."""
    df = players_engagement_df.copy()

    def normalize_value(x):
        if isinstance(x, list):
            if len(x) == 0:
                return "None"
            return " | ".join(map(str, x))
        if pd.isna(x):
            return "Missing"
        if isinstance(x, str) and x.strip() == "":
            return "Blank"
        return str(x)

    group_col = f"{column}__grouped"
    df[group_col] = df[column].apply(normalize_value)

    agg = df.groupby(group_col, dropna=False)["runs"].sum().reset_index().sort_values("runs", ascending=False)

    # keep only top categories if there are too many
    if len(agg) > max_categories:
        top = agg.iloc[:max_categories].copy()
        other_runs = agg.iloc[max_categories:]["runs"].sum()
        agg = pd.concat(
            [
                top,
                pd.DataFrame([{group_col: "Other", "runs": other_runs}]),
            ],
            ignore_index=True,
        )

    plt.figure(figsize=(10, 6))

    ax = sns.barplot(
        data=agg,
        x=group_col,
        y="runs",
    )

    ax.set_title(f"Player Engagement by {column}")
    ax.set_xlabel(column.replace("_", " ").title())
    ax.set_ylabel("Total Runs")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    plt.xticks(rotation=45, ha="right")
    plt.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.show()
