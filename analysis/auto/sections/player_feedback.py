"""Section 5 — Player Feedback.

Interactive DataTable of all form responses from assignments,
one row per answered question.
"""

from __future__ import annotations

from analysis.auto.rendering.table_utils import df_to_datatable
from analysis.common.loader import AnalysisData

_COLUMNS = [
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

_RENAME = {
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


def render(data: AnalysisData) -> str:
    df = data.feedback_df

    if df.empty:
        return '<div class="alert alert-info">No feedback responses found.</div>'

    cols = [c for c in _COLUMNS if c in df.columns]
    rename = {k: v for k, v in _RENAME.items() if k in cols}

    return df_to_datatable(
        df,
        table_id="feedback-table",
        columns=cols,
        rename=rename,
        page_length=50,
        truncate_cols=["answer", "question_prompt"],
        truncate_at=300,
    )
