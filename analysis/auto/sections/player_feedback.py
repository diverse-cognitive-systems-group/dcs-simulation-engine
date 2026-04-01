"""Section 5 — Player Feedback.

Renders two sub-sections:
1. In-play feedback — inline thumbs/flags/comments left on individual NPC messages.
2. Form responses — flattened assignment form answers (pre/post-game surveys).
"""

from __future__ import annotations

from analysis.auto.constants import chart_caption, section_intro
from analysis.auto.rendering.table_utils import df_to_datatable
from analysis.common.loader import AnalysisData

_FORM_COLUMNS = [
    "player_id",
    "game_name",
    "form_name",
    "before_or_after",
    "question_key",
    "question_prompt",
    "answer_type",
    "answer",
    "submitted_at",
]

_FORM_RENAME = {
    "player_id":       "Player",
    "game_name":       "Game",
    "form_name":       "Form",
    "before_or_after": "When",
    "question_key":    "Question Key",
    "question_prompt": "Question",
    "answer_type":     "Type",
    "answer":          "Answer",
    "submitted_at":    "Submitted At",
}

_EVENT_COLUMNS = [
    "session_id",
    "game_name",
    "player_id",
    "turn_index",
    "liked",
    "flags",
    "comment",
    "submitted_at",
]

_EVENT_RENAME = {
    "session_id":  "Session",
    "game_name":   "Game",
    "player_id":   "Player",
    "turn_index":  "Turn",
    "liked":       "Liked",
    "flags":       "Flags",
    "comment":     "Comment",
    "submitted_at": "Submitted At",
}


def render(data: AnalysisData) -> str:
    parts = [section_intro("player_feedback")]

    # --- In-play (per-message) feedback ---
    edf = data.event_feedback_df
    if not edf.empty:
        cols = [c for c in _EVENT_COLUMNS if c in edf.columns]
        rename = {k: v for k, v in _EVENT_RENAME.items() if k in cols}
        parts.append("<h5>In-Play Feedback</h5>")
        parts.append(df_to_datatable(
            edf,
            table_id="event-feedback-table",
            columns=cols,
            rename=rename,
            truncate_cols=["comment"],
            truncate_at=300,
        ))
        parts.append(chart_caption("player_feedback", "inplay_feedback_table"))

    # --- Form-based (survey) feedback ---
    fdf = data.feedback_df
    if not fdf.empty:
        cols = [c for c in _FORM_COLUMNS if c in fdf.columns]
        rename = {k: v for k, v in _FORM_RENAME.items() if k in cols}
        parts.append("<h5>Form Responses</h5>")
        parts.append(df_to_datatable(
            fdf,
            table_id="feedback-table",
            columns=cols,
            rename=rename,
            truncate_cols=["answer", "question_prompt"],
            truncate_at=300,
        ))
        parts.append(chart_caption("player_feedback", "form_responses_table"))

    if not parts:
        return '<div class="alert alert-info">No feedback responses found.</div>'

    return "\n".join(parts)
