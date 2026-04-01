"""Tests for ExperimentManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from dcs_simulation_engine.core.experiment_manager import ExperimentManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


def _entry_form_payload() -> dict[str, dict[str, object]]:
    return {
        "intake": {
            "age": 28,
            "technical_experience": ["Programming or scripting experience"],
            "technical_savviness": "High",
            "technical_experience_details": "Research computing background",
        }
    }


async def test_submit_before_play_stores_entry_form_on_assignment(async_mongo_provider, cached_usability_experiment) -> None:
    """Submitting before-play answers should persist the form on the player's assignment."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Ada Lovelace"}})
    assignment = await ExperimentManager.submit_before_play_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player_id=player.id,
        responses=_entry_form_payload(),
    )

    assert assignment is not None
    assert assignment.data[MongoColumns.FORM_RESPONSES]["intake"]["answers"]["age"]["answer"] == 28


async def test_interrupted_assignment_is_reused(async_mongo_provider, cached_usability_experiment) -> None:
    """Interrupted assignments should be returned again instead of generating a new row."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Ada"}})
    first = await ExperimentManager.get_or_create_assignment_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player=player,
    )
    assert first is not None

    await async_mongo_provider.update_assignment_status(
        assignment_id=first.assignment_id,
        status="interrupted",
    )

    second = await ExperimentManager.get_or_create_assignment_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player=player,
    )
    assert second is not None
    assert second.assignment_id == first.assignment_id


async def test_completed_assignment_blocks_further_assignment_when_max_is_one(async_mongo_provider, cached_usability_experiment) -> None:
    """A player should stop receiving assignments after one completed game when max_assignments=1."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Bob"}})
    assignment = await ExperimentManager.get_or_create_assignment_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player=player,
    )
    assert assignment is not None

    await async_mongo_provider.update_assignment_status(
        assignment_id=assignment.assignment_id,
        status="completed",
    )

    blocked = await ExperimentManager.get_or_create_assignment_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player=player,
    )
    assert blocked is None


async def test_post_play_completion_marks_experiment_finished_after_single_assignment(
    async_mongo_provider, cached_usability_experiment
) -> None:
    """Once post-play feedback is complete, single-game participants should be marked finished."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Dana"}})
    first = await ExperimentManager.submit_before_play_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player_id=player.id,
        responses=_entry_form_payload(),
    )
    assert first is not None

    await async_mongo_provider.update_assignment_status(
        assignment_id=first.assignment_id,
        status="completed",
    )
    await ExperimentManager.store_post_play_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player_id=player.id,
        responses={
            "usability_feedback": {
                "usability_issues": "None",
                "positive_usability": "Straightforward flow",
                "bugs_or_issues": "",
                "experience_preferences": "Liked the pacing",
                "additional_feedback": "",
            }
        },
    )

    state = await ExperimentManager.get_player_state_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player_id=player.id,
    )
    assert state["pending_post_play"] is None
    assert state["active_assignment"] is None
    assert state["has_finished_experiment"] is True


async def test_progress_counts_completed_assignments_and_unique_players(async_mongo_provider, cached_usability_experiment) -> None:
    """Experiment progress should report total, completed rows, and per-game unique-player counts."""
    player_a, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
    player_b, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "B"}})

    assignment_a = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player_a.id,
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.CHARACTER_HID: "test-char-a",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=assignment_a.assignment_id,
        status="completed",
    )

    assignment_b = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player_b.id,
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.CHARACTER_HID: "test-char-b",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=assignment_b.assignment_id,
        status="completed",
    )

    progress = await ExperimentManager.compute_progress_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
    )

    assert progress["total"] == cached_usability_experiment.assignment_strategy.quota_per_game * len(cached_usability_experiment.games)
    assert progress["completed"] == 2
    assert progress["is_complete"] is False


async def test_status_empty_experiment_reports_open_quota_totals(async_mongo_provider, cached_usability_experiment) -> None:
    """Experiment status should report zero live counts before any assignments exist."""
    quota = cached_usability_experiment.assignment_strategy.quota_per_game or 0

    status_payload = await ExperimentManager.compute_status_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
    )

    assert status_payload["is_open"] is True
    assert status_payload["total"] == quota * len(cached_usability_experiment.games)
    assert status_payload["completed"] == 0
    assert status_payload["per_game"]["Explore"] == {"total": quota, "completed": 0, "in_progress": 0}


async def test_status_counts_completed_and_in_progress_per_game(async_mongo_provider, cached_usability_experiment) -> None:
    """Experiment status should split completed and in-progress unique-player counts by game."""
    quota = cached_usability_experiment.assignment_strategy.quota_per_game or 0
    player_a, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
    player_b, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "B"}})
    player_c, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "C"}})

    completed_assignment = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player_a.id,
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.CHARACTER_HID: "test-char-a",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=completed_assignment.assignment_id,
        status="completed",
    )

    in_progress_assignment = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player_b.id,
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.CHARACTER_HID: "test-char-b",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=in_progress_assignment.assignment_id,
        status="in_progress",
        active_session_id="sess-exp-1",
    )

    second_completed_assignment = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player_c.id,
            MongoColumns.GAME_NAME: "Foresight",
            MongoColumns.CHARACTER_HID: "test-char-c",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=second_completed_assignment.assignment_id,
        status="completed",
    )

    status_payload = await ExperimentManager.compute_status_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
    )

    assert status_payload["is_open"] is True
    assert status_payload["completed"] == 2
    assert status_payload["per_game"]["Explore"] == {"total": quota, "completed": 1, "in_progress": 1}
    assert status_payload["per_game"]["Foresight"] == {"total": quota, "completed": 1, "in_progress": 0}


async def test_status_deduplicates_completed_players_per_game(async_mongo_provider, cached_usability_experiment) -> None:
    """Completed counts should be unique by player within each game."""
    quota = cached_usability_experiment.assignment_strategy.quota_per_game or 0
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})

    first = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player.id,
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.CHARACTER_HID: "test-char-a",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=first.assignment_id,
        status="completed",
    )

    second = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player.id,
            MongoColumns.GAME_NAME: "Explore",
            MongoColumns.CHARACTER_HID: "test-char-b",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=second.assignment_id,
        status="completed",
    )

    status_payload = await ExperimentManager.compute_status_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
    )

    assert status_payload["completed"] == 1
    assert status_payload["per_game"]["Explore"] == {"total": quota, "completed": 1, "in_progress": 0}


async def test_stopping_condition_reason_marks_assignment_completed(async_mongo_provider, cached_usability_experiment) -> None:
    """Stopping-condition exits should count as experiment completion."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})
    assignment = await async_mongo_provider.create_assignment(
        assignment_doc={
            MongoColumns.EXPERIMENT_NAME: cached_usability_experiment.name,
            MongoColumns.PLAYER_ID: player.id,
            MongoColumns.GAME_NAME: "Goal Horizon",
            MongoColumns.CHARACTER_HID: "test-char-a",
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    await async_mongo_provider.update_assignment_status(
        assignment_id=assignment.assignment_id,
        status="in_progress",
        active_session_id="sess-goal-1",
    )

    updated = await ExperimentManager.handle_session_terminal_state_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        assignment_id=assignment.assignment_id,
        exit_reason="stopping condition met: turns >=10",
    )

    assert updated is not None
    assert updated.status == "completed"


async def test_compute_progress_dispatches_to_assignment_strategy(
    monkeypatch: pytest.MonkeyPatch, async_mongo_provider, cached_usability_experiment
) -> None:
    """ExperimentManager should delegate progress calculation to the configured strategy."""
    strategy = MagicMock()
    strategy.compute_progress_async = AsyncMock(return_value={"total": 4, "completed": 1, "is_complete": False})

    monkeypatch.setattr("dcs_simulation_engine.core.experiment_manager.get_assignment_strategy", lambda _name: strategy)

    progress = await ExperimentManager.compute_progress_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
    )

    assert progress == {"total": 4, "completed": 1, "is_complete": False}
    strategy.compute_progress_async.assert_awaited_once()


async def test_compute_status_dispatches_to_assignment_strategy(
    monkeypatch: pytest.MonkeyPatch, async_mongo_provider, cached_usability_experiment
) -> None:
    """ExperimentManager should delegate status calculation to the configured strategy."""
    strategy = MagicMock()
    strategy.compute_status_async = AsyncMock(return_value={"is_open": True, "total": 4, "completed": 1, "per_game": {}})

    monkeypatch.setattr("dcs_simulation_engine.core.experiment_manager.get_assignment_strategy", lambda _name: strategy)

    status_payload = await ExperimentManager.compute_status_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
    )

    assert status_payload == {"is_open": True, "total": 4, "completed": 1, "per_game": {}}
    strategy.compute_status_async.assert_awaited_once()


async def test_get_or_create_assignment_dispatches_to_assignment_strategy(
    monkeypatch: pytest.MonkeyPatch, async_mongo_provider, cached_usability_experiment
) -> None:
    """ExperimentManager should delegate assignment creation to the configured strategy."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Delegated"}})
    assignment = object()
    strategy = MagicMock()
    strategy.get_or_create_assignment_async = AsyncMock(return_value=assignment)

    monkeypatch.setattr("dcs_simulation_engine.core.experiment_manager.get_assignment_strategy", lambda _name: strategy)

    result = await ExperimentManager.get_or_create_assignment_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player=player,
    )

    assert result is assignment
    strategy.get_or_create_assignment_async.assert_awaited_once()
