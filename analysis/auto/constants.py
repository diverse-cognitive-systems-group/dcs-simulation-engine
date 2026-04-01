"""Centralised text descriptions for auto-analysis report sections and charts.

Edit the strings here to update what appears in the generated HTML report
without touching any rendering or section code.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Section-level descriptions
# Shown once at the top of each section, immediately below the <h2> heading.
# ---------------------------------------------------------------------------

SECTION_DESCRIPTIONS: dict[str, str] = {
    "metadata": (
        "High-level facts about this experiment: its configuration, participant "
        "counts, and links to raw data artifacts."
    ),
    "runs_overview": (
        "A searchable, filterable table of every gameplay session alongside a "
        "PC/NPC pairing heatmap showing which character combinations were played "
        "together and how often."
    ),
    "system_performance": (
        "Charts and metrics covering how the game engine performed across all "
        "sessions — durations, pacing, exit reasons, retry usage, and a "
        "chronological session timeline."
    ),
    "player_engagement": (
        "Charts showing how much each player participated and how engagement "
        "varied across player attributes such as consent status and prior "
        "experience."
    ),
    "player_feedback": (
        "In-play reactions (thumbs-up, flags, and freeform comments left on "
        "individual NPC messages) alongside structured survey responses collected "
        "before or after sessions."
    ),
    "player_performance": (
        "Outcome metrics measuring how well players performed during gameplay "
        "sessions. (Section not yet implemented.)"
    ),
    "transcripts": (
        "Full event log for all sessions. Use the Transcript column to read "
        "dialogue turns, and filter by session, player, or turn index to focus "
        "on specific interactions."
    ),
}

# ---------------------------------------------------------------------------
# Chart / table-level descriptions
# Shown as a small caption immediately after each chart or table.
# Keyed as CHART_DESCRIPTIONS[section_key][chart_key].
# ---------------------------------------------------------------------------

CHART_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "runs_overview": {
        "pairing_heatmap": (
            "How many times each PC was paired with each NPC across all runs. "
            "Uneven distribution may reflect assignment strategy constraints or "
            "player drop-out."
        ),
        "sessions_table": (
            "One row per gameplay session. Use the column search boxes to filter "
            "by player, game, or exit reason, and the export buttons to download "
            "a CSV or Excel file."
        ),
    },
    "system_performance": {
        "exit_reasons": (
            "How each session ended — e.g., completed normally, timed out, or "
            "hit an error. A high proportion of error exits may indicate "
            "stability issues."
        ),
        "duration_distribution": (
            "Distribution of session lengths across all runs. Outliers on the "
            "high end may indicate sessions that stalled or were left idle."
        ),
        "duration_by_game": (
            "Compares session length distributions across games. Useful for "
            "spotting games with consistently shorter or longer play times."
        ),
        "turns_vs_runtime": (
            "Relationship between number of turns completed and total session "
            "duration. Points far from the overall trend may indicate slow turns, "
            "long player think-times, or pauses mid-session."
        ),
        "retry_budget": (
            "Frequency of each last-sequence value across sessions. A high "
            "count at low values may indicate sessions ending much earlier than "
            "expected."
        ),
        "session_timeline": (
            "Chronological Gantt view of all sessions. Useful for spotting "
            "concurrency, maintenance windows, or unexpected gaps in data "
            "collection."
        ),
        "lt_game_duration_by_player": (
            "Distribution of total game duration (ms) for each player. Wide or "
            "skewed violins indicate high variability in how long that player's "
            "sessions ran."
        ),
        "lt_wait_by_player": (
            "Distribution of NPC response wait times (ms) during turn-phase "
            "exchanges, grouped by player. Captures how long each player waited "
            "for an NPC reply across all their turns."
        ),
        "lt_wait_by_player_and_game": (
            "Same wait-response distributions as above, further split by game "
            "number (g1, g2, …) to reveal whether response latency changed across "
            "successive sessions for each player."
        ),
        "lt_hist_game_duration": (
            "Overall game-duration density across all players and sessions. "
            "Reference lines mark the mean, median, p90, p95, and p99 to "
            "highlight the tail of unusually long sessions."
        ),
        "lt_hist_wait_turn": (
            "Density of NPC response wait times during turn-phase exchanges across "
            "all players and sessions. Percentile markers help quantify the worst-"
            "case latency experienced during normal gameplay turns."
        ),
        "lt_hist_wait_opening": (
            "Density of NPC response wait times specifically during the opening "
            "turn (turn_index 0) of each session. Opening turns often show higher "
            "latency due to cold-start or context-loading overhead."
        ),
        "lt_hist_wait_close": (
            "Density of NPC response wait times during the final turn of each "
            "session. Elevated close-phase latency may indicate resource contention "
            "or slow session-teardown paths."
        ),
    },
    "player_engagement": {
        "runs_per_player": (
            "Number of sessions completed by each player, sorted highest to "
            "lowest. Highly uneven distribution may indicate player drop-out or "
            "a small group of repeat participants."
        ),
        "engagement_by_consent": (
            "Total runs grouped by whether the player consented to follow-up "
            "contact. Useful for understanding the reachable subset of "
            "participants for future studies."
        ),
        "engagement_by_experience": (
            "Total runs grouped by the player's self-reported prior experience "
            "with similar games or AI systems."
        ),
    },
    "player_feedback": {
        "inplay_feedback_table": (
            "Reactions left by players on individual NPC messages during "
            "gameplay — likes, flags, and freeform comments. Sorted by session "
            "and turn."
        ),
        "form_responses_table": (
            "Answers to structured pre- and post-session survey questions. "
            "Filter by player or form name to compare responses across "
            "participants."
        ),
    },
    "transcripts": {
        "transcripts_table": (
            "Complete turn-by-turn event log with gameplay context columns "
            "(player, PC, NPC) joined from session data. Long transcript entries "
            "are truncated — hover to read the full text."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def section_intro(key: str) -> str:
    """Return an HTML lead paragraph for the given section key, or '' if absent."""
    text = SECTION_DESCRIPTIONS.get(key, "")
    if not text:
        return ""
    return f'<p class="text-muted mb-3" style="font-size:0.9rem;">{text}</p>'


def chart_caption(section: str, chart: str) -> str:
    """Return an HTML caption for a chart or table, or '' if absent."""
    text = CHART_DESCRIPTIONS.get(section, {}).get(chart, "")
    if not text:
        return ""
    return f'<p class="text-muted mt-1 mb-3" style="font-size:0.82rem;"><em>{text}</em></p>'
