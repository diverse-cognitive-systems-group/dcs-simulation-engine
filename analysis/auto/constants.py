"""Centralised text descriptions for auto-analysis report sections and charts.

Edit the strings here to update what appears in the generated HTML report
without touching any rendering or section code.
"""

# ---------------------------------------------------------------------------
# Section-level descriptions
# Shown once at the top of each section, immediately below the <h2> heading.
# ---------------------------------------------------------------------------

SECTION_DESCRIPTIONS: dict[str, str] = {
    "metadata": (
        "Experiment configuration and participant counts at a glance. "
        "Confirms the right games, players, and assignment settings were used."
    ),
    "simulation_quality": (
        "Aggregate and per-character simulation quality scores. "
        "ICF (In-Character Fidelity) measures the proportion of NPC turns not flagged as out-of-character; "
        "NCo (Narrative Coherence) measures the proportion flagged as not making sense."
    ),
    "runs_overview": (
        "Health snapshot of all gameplay sessions: character pairings, daily "
        "activity, exit reasons, session length and depth, game coverage, and "
        "how participation funneled from assignment through completion. "
        "Start here to spot data gaps or imbalances before reading deeper sections."
    ),
    "system_performance": (
        "Engine-level diagnostics: how long sessions ran, how turns mapped to "
        "wall-clock time, NPC response latency, and where sessions fell short "
        "of expected depth. Use this to identify infrastructure bottlenecks or "
        "sessions that behaved abnormally."
    ),
    "player_engagement": (
        "How much each player participated and how activity broke down by "
        "player attributes. Useful for spotting drop-out patterns and "
        "understanding which participant groups engaged most."
    ),
    "player_feedback": (
        "In-session reactions (likes, flags, freeform comments on NPC messages) "
        "and structured survey responses. Use this to connect player sentiment "
        "to specific moments in gameplay."
    ),
    "player_performance": (
        "Outcome metrics measuring how well players performed during gameplay. "
        "(Not yet implemented.)"
    ),
    "system_errors": (
        "Three views of errors across the experiment: a summary card, "
        "in-game error events delivered to players (from session events), "
        "and filtered engine log entries. Use this section to distinguish "
        "player-visible failures from internal warnings, and to spot "
        "recurring or session-specific problems."
    ),
    "transcripts": (
        "Turn-by-turn event log for all sessions. Filter by session, player, "
        "PC, or NPC to read specific exchanges. Use alongside Feedback to "
        "find the dialogue that prompted a reaction."
    ),
}

# ---------------------------------------------------------------------------
# Chart / table-level descriptions
# Shown as a small caption immediately after each chart or table.
# Keyed as CHART_DESCRIPTIONS[section_key][chart_key].
# ---------------------------------------------------------------------------

CHART_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "simulation_quality": {
        "per_npc_scores_table": (
            "ICF, NCo, and Other flag rates per NPC character. "
            "Values are percentages of total NPC turns for that character. "
            "ICF = proportion of turns not flagged as out-of-character; "
            "NCo = proportion flagged as not making sense."
        ),
    },
    "runs_overview": {
        "pairing_heatmap": (
            "Session count for every PC × NPC combination. Blank cells mean "
            "that pairing was never played; dark cells flag over-represented "
            "pairs. Use this to verify that character coverage matches the "
            "intended assignment strategy."
        ),
        "sessions_over_time": (
            "Sessions started per day. Identifies recruitment bursts, quiet "
            "periods, and whether data collection was concentrated or spread "
            "across the study window."
        ),
        "exit_reasons": (
            "Breakdown of how sessions ended. A healthy experiment shows most "
            "sessions completing normally; elevated timeouts, errors, or "
            "abandoned counts point to UX or stability issues worth investigating."
        ),
        "turns_distribution": (
            "How many dialogue turns players completed per session. A spike at "
            "low turn counts suggests early drop-out; a long right tail means "
            "some players went well beyond the typical session length."
        ),
        "duration_distribution": (
            "Session lengths in minutes. Very short sessions often indicate "
            "immediate exits; very long ones may be idle sessions left open. "
            "Compare with the turns distribution to distinguish deep engagement "
            "from slow or stalled sessions."
        ),
        "runs_per_game": (
            "Total sessions per game. Shows whether play was spread across "
            "games as intended or skewed toward a subset — useful for catching "
            "assignment imbalances early."
        ),
        "participation_funnel": (
            "Players at each stage: assigned → started at least one session → "
            "completed at least one session. The size of each drop reveals "
            "where participants disengaged."
        ),
        "completion_by_game": (
            "Completed vs. non-completed sessions for each game. Games with "
            "disproportionate non-completion may have content, pacing, or "
            "technical issues driving players to quit."
        ),
        "sessions_per_player": (
            "How many sessions each player finished. A heavily skewed "
            "distribution (few players, many sessions) can bias per-session "
            "averages elsewhere in the report."
        ),
        "sessions_table": (
            "One row per gameplay session with player, characters, turn count, "
            "duration, and exit reason. Filter by any column or export to CSV / "
            "Excel for further analysis."
        ),
    },
    "system_performance": {
        "exit_reasons": (
            "Session exit reason counts. Complements the Overview breakdown "
            "with system-level context — error exits here are worth cross-"
            "referencing with the logs table."
        ),
        "duration_distribution": (
            "Session lengths in minutes across all runs. A heavy right tail "
            "often indicates sessions that stalled or were abandoned while still "
            "technically open."
        ),
        "duration_by_game": (
            "Session length distributions split by game. Reveals whether one "
            "game consistently runs shorter or longer, which can affect "
            "turn-count and latency comparisons elsewhere."
        ),
        "turns_vs_runtime": (
            "Turns completed vs. total session duration (scatter). Points well "
            "above the trend line had unusually slow turns — possible NPC "
            "latency spikes or long player think-times."
        ),
        "retry_budget": (
            "Distribution of last-sequence values reached per session. Low "
            "values mean the session ended before the NPC could reach its "
            "normal conclusion — a proxy for how much of the intended content "
            "players actually experienced."
        ),
        "session_timeline": (
            "Gantt chart of all sessions by start and end time. Useful for "
            "spotting concurrent sessions, maintenance windows, or unexpected "
            "gaps in data collection."
        ),
        "lt_game_duration_by_player": (
            "Total game duration (ms) per player as a violin plot. Wide or "
            "multi-modal violins indicate high variability — worth checking "
            "whether specific players experienced consistently slow sessions."
        ),
        "lt_wait_by_player": (
            "NPC response wait time (ms) per player across all turn-phase "
            "exchanges. Identifies players who consistently waited longer — "
            "could reflect network conditions or model load at the time they played."
        ),
        "lt_wait_by_player_and_game": (
            "Same NPC wait-time distributions split further by game number "
            "(g1, g2, …). Use this to check whether latency degraded or "
            "improved across successive sessions for the same player."
        ),
        "lt_hist_game_duration": (
            "Density of total game durations across all sessions. Percentile "
            "reference lines (mean, median, p90, p95, p99) highlight how extreme "
            "the long-session tail is."
        ),
        "lt_hist_wait_turn": (
            "Density of NPC response wait times during normal (non-opening, "
            "non-closing) turns. Percentile markers show worst-case latency "
            "experienced during typical gameplay exchanges."
        ),
        "lt_hist_wait_opening": (
            "NPC response wait times for the first turn of each session "
            "(turn_index 0). Opening turns tend to be slower due to context "
            "loading; compare with turn-phase wait times to quantify the "
            "cold-start overhead."
        ),
        "lt_hist_wait_close": (
            "NPC response wait times during the final turn of each session. "
            "Elevated close-phase latency relative to mid-session turns may "
            "point to slow teardown logic or resource contention at session end."
        ),
    },
    "player_engagement": {
        "runs_per_player": (
            "Sessions completed per player, sorted descending. A long tail of "
            "low-count players alongside a few high-count players can skew "
            "aggregate metrics — worth noting before drawing per-session conclusions."
        ),
        "engagement_by_consent": (
            "Session counts grouped by follow-up consent status. Shows the "
            "size of the reachable participant pool for any post-study contact "
            "or longitudinal follow-up."
        ),
        "engagement_by_experience": (
            "Session counts grouped by self-reported prior experience with "
            "similar games or AI. Useful for checking whether novice and "
            "experienced players engaged at different rates."
        ),
    },
    "player_feedback": {
        "flags_over_turns": (
            "Frequency of each flag type (out of character, doesn't make sense, other) "
            "at each turn index across all sessions. Peaks reveal which turns in the "
            "conversation arc the NPC most often breaks character or produces unclear responses."
        ),
        "inplay_feedback_table": (
            "Every in-session reaction (like, flag, or comment) left on an "
            "NPC message, with session and turn context. The Transcript Context column "
            "shows the preceding turns leading up to the flagged message — hover to read "
            "the full excerpt. Sort by turn or session to find clusters of negative reactions."
        ),
        "flags_over_turns_by_game": (
            "Flag frequency per turn split by game. Reveals whether specific games "
            "produce character or coherence issues at particular dialogue stages."
        ),
        "flags_over_turns_by_player": (
            "Per-player flag counts across turn indices. Use the dropdown to select "
            "a player and identify individuals whose feedback clusters at specific turns."
        ),
        "player_segments_table": (
            "Per-player feedback summary with a segment label (only positive, only negative, "
            "high/low feedback volume, mixed). Thresholds are set at the 25th and 75th "
            "percentile of total feedback count. Use this to identify outlier players whose "
            "feedback patterns may skew aggregate statistics."
        ),
        "form_responses_table": (
            "Structured survey answers collected before or after sessions. "
            "Filter by player or form name to compare how different participants "
            "responded to the same questions."
        ),
    },
    "system_errors": {
        "summary_card": (
            "Counts of WARNING / ERROR / CRITICAL log entries, in-game error "
            "events shown to players, and sessions that ended with retry budget "
            "exhausted. Use as a quick severity triage before reading the tables."
        ),
        "log_level_breakdown": (
            "Distribution of log entries by severity level across all log files. "
            "A large ERROR or CRITICAL bar relative to WARNING warrants immediate "
            "investigation."
        ),
        "error_events_per_session": (
            "Number of in-game error events (event_type='error') per session. "
            "Sessions with multiple errors likely had a degraded player experience."
        ),
        "top_error_messages": (
            "The 20 most frequent distinct error messages from the engine logs. "
            "High-count messages indicate systematic failures worth fixing; "
            "low-count messages are likely one-offs."
        ),
        "inplay_error_events_table": (
            "Every error event delivered to a player during gameplay, with "
            "session, player, game, turn, and message content. Cross-reference "
            "with the Transcripts section to see surrounding dialogue."
        ),
        "errors_log_table": (
            "Raw WARNING / ERROR / CRITICAL log entries from engine log files. "
            "Rows are highlighted by severity. Use the search box to filter by "
            "module, function, or message text."
        ),
    },
    "transcripts": {
        "transcripts_table": (
            "Full turn-by-turn event log with player, PC, and NPC columns "
            "joined from session data. Long entries are truncated — hover to "
            "read the full text. Cross-reference with Feedback to find the "
            "dialogue that prompted a specific reaction."
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
