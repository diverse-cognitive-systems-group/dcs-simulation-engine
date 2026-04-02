"""Section — Form Responses.

Renders flattened assignment form answers (pre/post-game surveys).
"""



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


def render(data: AnalysisData) -> str:
    fdf = data.feedback_df
    if fdf.empty:
        return '<div class="alert alert-info">No form responses found.</div>'

    cols = [c for c in _FORM_COLUMNS if c in fdf.columns]
    rename = {k: v for k, v in _FORM_RENAME.items() if k in cols}

    table = df_to_datatable(
        fdf,
        table_id="feedback-table",
        columns=cols,
        rename=rename,
        truncate_cols=["answer", "question_prompt"],
        truncate_at=300,
    )

    return table + "\n" + chart_caption("player_feedback", "form_responses_table")
