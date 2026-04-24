"""Tests for ExperimentManager."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from dcs_simulation_engine.core.experiment_config import ExperimentConfig
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


def _cache_config(config: ExperimentConfig):
    original_cache = ExperimentManager._experiment_config_cache.copy()
    ExperimentManager._experiment_config_cache = {ExperimentManager._cache_key(config.name): config}
    return original_cache


async def test_submit_before_play_stores_entry_form_in_forms_collection(async_mongo_provider, cached_usability_experiment) -> None:
    """Submitting before-play answers should persist the form in the forms collection, not on the assignment."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Ada Lovelace"}})
    assignment = await ExperimentManager.submit_before_play_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player_id=player.id,
        responses=_entry_form_payload(),
    )

    assert assignment is not None
    # Before-play forms now live in the forms collection, not on the assignment.
    assert assignment.data.get(MongoColumns.FORM_RESPONSES, {}).get("intake") is None
    player_forms = await async_mongo_provider.get_player_forms(
        player_id=player.id,
        experiment_name=cached_usability_experiment.name,
    )
    assert player_forms is not None
    assert player_forms.data["intake"]["answers"]["age"]["answer"] == 28


@pytest.mark.parametrize(
    "reason,expected",
    [
        ("game_completed", True),
        ("game_complete", True),
        ("game completed", True),
        ("Game Completed", True),
        ("max predictions reached", True),
        ("max_predictions_reached", True),
        ("player exited", True),
        ("player_exited", True),
        ("stopping_condition_met:max_turns", True),
        ("stopping_condition_met:anything", True),
        ("retry budget exhausted", False),
        ("websocket_disconnect", False),
        ("server_error", False),
        ("received close request", False),
        ("", False),
    ],
)
def test_is_completion_reason(reason: str, expected: bool) -> None:
    """Test that _is_completion_reason correctly identifies completion reasons."""
    assert ExperimentManager._is_completion_reason(reason) is expected


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
            MongoColumns.PC_HID: "test-char-a",
            MongoColumns.NPC_HID: "test-npc-a",
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
            MongoColumns.PC_HID: "test-char-b",
            MongoColumns.NPC_HID: "test-npc-b",
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
            MongoColumns.PC_HID: "test-char-a",
            MongoColumns.NPC_HID: "test-npc-a",
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
            MongoColumns.PC_HID: "test-char-b",
            MongoColumns.NPC_HID: "test-npc-b",
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
            MongoColumns.PC_HID: "test-char-c",
            MongoColumns.NPC_HID: "test-npc-c",
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
            MongoColumns.PC_HID: "test-char-a",
            MongoColumns.NPC_HID: "test-npc-a",
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
            MongoColumns.PC_HID: "test-char-b",
            MongoColumns.NPC_HID: "test-npc-b",
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
            MongoColumns.PC_HID: "test-char-a",
            MongoColumns.NPC_HID: "test-npc-a",
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


async def test_create_player_choice_assignment_persists_pc_and_npc(
    monkeypatch: pytest.MonkeyPatch, async_mongo_provider, cached_usability_experiment
) -> None:
    """Player-choice assignment creation should persist the selected PC/NPC triple."""
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Chooser"}})
    monkeypatch.setattr(
        ExperimentManager,
        "get_eligible_options_async",
        AsyncMock(return_value=[{"game_name": "Explore", "pc_hid": "pc-alpha", "npc_hid": "npc-beta"}]),
    )

    assignment = await ExperimentManager.create_player_choice_assignment_async(
        provider=async_mongo_provider,
        experiment_name=cached_usability_experiment.name,
        player=player,
        game_name="Explore",
        pc_hid="pc-alpha",
        npc_hid="npc-beta",
    )

    assert assignment.pc_hid == "pc-alpha"
    assert assignment.npc_hid == "npc-beta"


async def test_require_assignment_completion_false_allows_new_assignment_after_interruption(
    async_mongo_provider,
    write_yaml,
) -> None:
    """Interrupted assignments should stop blocking new work when completion gating is disabled."""
    path = write_yaml(
        "no-completion-gate.yaml",
        """
        name: no-completion-gate
        description: Strategy test fixture
        assignment_strategy:
          strategy: full_character_access
          games:
            - Explore
          quota_per_game: 5
          max_assignments_per_player: 2
          assignment_mode: auto
          require_assignment_completion: false
          seed: no-completion-gate
        """,
    )
    config = ExperimentConfig.load(Path(path))
    original_cache = _cache_config(config)
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Gate"}})

    try:
        first = await ExperimentManager.get_or_create_assignment_async(
            provider=async_mongo_provider,
            experiment_name=config.name,
            player=player,
        )
        assert first is not None
        await async_mongo_provider.update_assignment_status(assignment_id=first.assignment_id, status="interrupted")

        second = await ExperimentManager.get_or_create_assignment_async(
            provider=async_mongo_provider,
            experiment_name=config.name,
            player=player,
        )
    finally:
        ExperimentManager._experiment_config_cache = original_cache

    assert second is not None
    assert second.assignment_id != first.assignment_id


async def test_completed_assignment_reflected_in_player_state_after_multi_assignment_game(
    async_mongo_provider, cached_multi_assignment_experiment
) -> None:
    """After completing one game in a 3-assignment experiment, get_player_state_async must.

    Return one completed assignment and two assigned ones — confirming that progress (1 of 3)
    is correctly reflected for the player.
    """
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Progress Tester"}})

    # Register: creates assignment 1 and pre-generates assignments 2 & 3.
    await ExperimentManager.submit_before_play_async(
        provider=async_mongo_provider,
        experiment_name=cached_multi_assignment_experiment.name,
        player_id=player.id,
        responses={"intake": {"age": 30}},
    )

    # Retrieve the active assignment (whichever was selected) and mark it completed.
    state_before = await ExperimentManager.get_player_state_async(
        provider=async_mongo_provider,
        experiment_name=cached_multi_assignment_experiment.name,
        player_id=player.id,
    )
    active = state_before["active_assignment"]
    assert active is not None
    assert len(state_before["assignments"]) == 3, "All 3 assignments should be pre-generated"

    await async_mongo_provider.update_assignment_status(
        assignment_id=active.assignment_id,
        status="completed",
    )

    # Submit post-play so pending_post_play is cleared.
    await ExperimentManager.store_post_play_async(
        provider=async_mongo_provider,
        experiment_name=cached_multi_assignment_experiment.name,
        player_id=player.id,
        responses={
            "usability_feedback": {
                "usability_issues": "",
                "positive_usability": "Good",
                "bugs_or_issues": "",
                "experience_preferences": "Fine",
                "additional_feedback": "",
            }
        },
    )

    state_after = await ExperimentManager.get_player_state_async(
        provider=async_mongo_provider,
        experiment_name=cached_multi_assignment_experiment.name,
        player_id=player.id,
    )

    statuses = [a.status for a in state_after["assignments"]]
    completed_count = statuses.count("completed")
    assert len(state_after["assignments"]) == 3, "All 3 assignments must still be present"
    assert completed_count == 1, f"Expected 1 completed assignment, got {completed_count} — statuses: {statuses}"
    assert state_after["has_finished_experiment"] is False
    assert state_after["active_assignment"] is not None
