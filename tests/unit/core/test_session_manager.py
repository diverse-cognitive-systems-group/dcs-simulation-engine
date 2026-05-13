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
        ("player_validation_retry_exhausted", "player_validation_retry_exhausted"),
        ("simulator_validation_retry_exhausted", "simulator_validation_retry_exhausted"),
        ("simulator_recovery_budget_exhausted", "simulator_recovery_budget_exhausted"),
        ("internal_error", "internal_error"),
        ("model_provider_error", "model_provider_error"),
        ("server_error", "server_error"),
    ],
)
def test_normalize_termination_reason(reason: str, expected: str) -> None:
    """Persist only current canonical terminal reasons."""
    manager = object.__new__(SessionManager)

    assert manager._normalize_termination_reason(reason) == expected


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("server_error", True),
        ("internal_error", True),
        ("simulator_validation_retry_exhausted", True),
        ("simulator_recovery_budget_exhausted", True),
        ("model_provider_error", True),
        ("game_completed", False),
        ("player_validation_retry_exhausted", False),
    ],
)
def test_error_termination_reasons(reason: str, expected: bool) -> None:
    """Only engine/provider terminal failures should persist with status=error."""
    manager = object.__new__(SessionManager)

    assert manager._is_error_termination(reason) is expected


class _FakeGame:
    exited = False
    exit_reason = ""

    def exit(self, reason: str) -> None:
        self.exited = True
        self.exit_reason = reason


class _FakeRecorder:
    def __init__(self) -> None:
        self.finalized: dict | None = None
        self.closed = False

    async def finalize(self, *, termination_reason: str, status: str, turns_completed: int) -> None:
        self.finalized = {
            "termination_reason": termination_reason,
            "status": status,
            "turns_completed": turns_completed,
        }

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_exit_async_persists_model_provider_error_status() -> None:
    """Provider terminal failures should persist as errored sessions."""
    manager = object.__new__(SessionManager)
    recorder = _FakeRecorder()
    manager.game = _FakeGame()
    manager._exited = False
    manager._exit_reason = ""
    manager.end_ts = None
    manager._finalized = False
    manager._recorder_open = True
    manager._recorder = recorder
    manager._validation_recorder = None
    manager._turn_count = 0

    await manager.exit_async("model_provider_error")

    assert recorder.finalized == {
        "termination_reason": "model_provider_error",
        "status": "error",
        "turns_completed": 0,
    }
    assert recorder.closed is True
    assert manager._finalized is True
