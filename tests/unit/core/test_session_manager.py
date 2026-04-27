"""Tests for SessionManager."""

import pytest
from dcs_simulation_engine.core.session_manager import SessionManager

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("player finished", "game_completed"),
        ("player_finished", "game_completed"),
        ("game_completed", "game_completed"),
        ("game_complete", "game_complete"),
        ("received close request", "user_close_button"),
        ("retry budget exhausted", "validation_retry_exhausted"),
        ("server_error", "server_error"),
    ],
)
def test_normalize_termination_reason(reason: str, expected: str) -> None:
    """Persist only current canonical terminal reasons."""
    manager = object.__new__(SessionManager)

    assert manager._normalize_termination_reason(reason) == expected
