"""Tests for reporting loader."""

import json

import pytest
from dcs_simulation_engine.reporting import load_all

pytestmark = pytest.mark.unit


def test_load_all_flattens_player_scoped_forms(tmp_path):
    """Entry forms stored in forms.json should appear in feedback_df."""
    (tmp_path / "forms.json").write_text(
        json.dumps(
            [
                {
                    "player_id": "player-1",
                    "data": {
                        "entry_consent": {
                            "form_name": "entry_consent",
                            "trigger": {"event": "before_all_assignments", "match": None},
                            "submitted_at": "2026-04-01T00:00:00Z",
                            "answers": {
                                "consent": {
                                    "key": "consent",
                                    "prompt": "Do you agree to participate?",
                                    "answer_type": "single_choice",
                                    "required": True,
                                    "answer": "I agree.",
                                }
                            },
                        }
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    data = load_all(tmp_path)

    assert data.player_forms_df.shape[0] == 1
    assert data.feedback_df.shape[0] == 1
    row = data.feedback_df.iloc[0]
    assert row["player_id"] == "player-1"
    assert row["form_name"] == "entry_consent"
    assert row["trigger_event"] == "before_all_assignments"
    assert row["question_key"] == "consent"
    assert row["answer"] == "I agree."
