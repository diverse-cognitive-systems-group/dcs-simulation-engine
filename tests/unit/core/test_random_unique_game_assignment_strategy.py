"""Tests for the random_unique_game assignment strategy."""

import pytest
from dcs_simulation_engine.core.assignment_strategies import get_assignment_strategy
from dcs_simulation_engine.core.run_config import RunConfig
from dcs_simulation_engine.dal.mongo.const import MongoColumns

pytestmark = [pytest.mark.unit, pytest.mark.anyio]


def _load_strategy_config(
    write_yaml,
    *,
    name: str,
    games: list[str],
    quota_per_game: int = 1,
    max_assignments_per_player: int = 1,
    allow_choice_if_multiple: bool = False,
    require_completion: bool = True,
) -> RunConfig:
    games_yaml = "\n".join(f"  - name: {game}" for game in games)
    path = write_yaml(
        f"{name}.yaml",
        "\n".join(
            [
                f"name: {name}",
                "description: Strategy test fixture",
                "games:",
                games_yaml,
                "next_game_strategy:",
                "  strategy:",
                "    id: random_unique_game",
                f"    quota_per_game: {quota_per_game}",
                f"    max_assignments_per_player: {max_assignments_per_player}",
                f"    seed: {name}-seed",
                f"    allow_choice_if_multiple: {str(allow_choice_if_multiple).lower()}",
                f"    require_completion: {str(require_completion).lower()}",
            ]
        )
        + "\n",
    )
    return RunConfig.load(path)


async def _create_assignment(
    provider,
    *,
    player_id: str,
    game_name: str,
    pc_hid: str,
    npc_hid: str = "test-npc-a",
    status: str = "assigned",
) -> None:
    assignment = await provider.create_assignment(
        assignment_doc={
            MongoColumns.PLAYER_ID: player_id,
            MongoColumns.GAME_NAME: game_name,
            MongoColumns.PC_HID: pc_hid,
            MongoColumns.NPC_HID: npc_hid,
            MongoColumns.FORM_RESPONSES: {},
        }
    )
    if status == "in_progress":
        await provider.update_assignment_status(
            assignment_id=assignment.assignment_id,
            status="in_progress",
            active_session_id=f"session-{player_id}",
        )
    elif status in {"completed", "interrupted"}:
        await provider.update_assignment_status(
            assignment_id=assignment.assignment_id,
            status=status,
        )


async def test_random_unique_game_progress_closes_on_in_progress_quota(async_mongo_provider, write_yaml) -> None:
    """Progress should close once in-progress plus completed players fill the quota."""
    config = _load_strategy_config(write_yaml, name="single-progress", games=["Explore"])
    strategy = get_assignment_strategy("random_unique_game")
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})

    await _create_assignment(
        async_mongo_provider,
        player_id=player.id,
        game_name="Explore",
        pc_hid="test-char-a",
        status="in_progress",
    )

    progress = await strategy.compute_progress_async(provider=async_mongo_provider, config=config)

    assert progress == {"total": 1, "completed": 0, "is_complete": True}


async def test_random_unique_game_status_closes_on_counted_quota(async_mongo_provider, write_yaml) -> None:
    """Status openness should be based on counted players, not only completed rows."""
    config = _load_strategy_config(write_yaml, name="single-status", games=["Explore"])
    strategy = get_assignment_strategy("random_unique_game")
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "A"}})

    await _create_assignment(
        async_mongo_provider,
        player_id=player.id,
        game_name="Explore",
        pc_hid="test-char-a",
        status="in_progress",
    )

    status_payload = await strategy.compute_status_async(provider=async_mongo_provider, config=config)

    assert status_payload["is_open"] is False
    assert status_payload["per_game"]["Explore"] == {"total": 1, "completed": 0, "in_progress": 1}


async def test_random_unique_game_does_not_repeat_games_for_the_same_player(async_mongo_provider, write_yaml) -> None:
    """Players should receive a different game when multiple assignments are allowed."""
    config = _load_strategy_config(
        write_yaml,
        name="multi-player-unique",
        games=["Explore", "Foresight"],
        max_assignments_per_player=2,
    )
    strategy = get_assignment_strategy("random_unique_game")
    player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Repeat"}})

    first = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)
    assert first is not None
    await async_mongo_provider.update_assignment_status(assignment_id=first.assignment_id, status="completed")

    second = await strategy.get_or_create_assignment_async(provider=async_mongo_provider, config=config, player=player)

    assert second is not None
    assert second.game_name != first.game_name


async def test_random_unique_game_skips_games_at_counted_quota(async_mongo_provider, write_yaml) -> None:
    """Only games below quota should remain eligible for new assignments."""
    config = _load_strategy_config(
        write_yaml,
        name="remaining-games",
        games=["Explore", "Foresight"],
    )
    strategy = get_assignment_strategy("random_unique_game")
    filled_player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Filled"}})
    next_player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Next"}})

    await _create_assignment(
        async_mongo_provider,
        player_id=filled_player.id,
        game_name="Explore",
        pc_hid="test-char-a",
        status="in_progress",
    )

    assignment = await strategy.get_or_create_assignment_async(
        provider=async_mongo_provider,
        config=config,
        player=next_player,
    )

    assert assignment is not None
    assert assignment.game_name == "Foresight"


async def test_random_unique_game_assigned_rows_do_not_consume_quota(async_mongo_provider, write_yaml) -> None:
    """Assigned rows should not reserve one of the per-game quota slots."""
    config = _load_strategy_config(write_yaml, name="assigned-does-not-count", games=["Explore"])
    strategy = get_assignment_strategy("random_unique_game")
    first_player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Assigned"}})
    second_player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Fresh"}})

    await _create_assignment(
        async_mongo_provider,
        player_id=first_player.id,
        game_name="Explore",
        pc_hid="test-char-a",
    )

    assignment = await strategy.get_or_create_assignment_async(
        provider=async_mongo_provider,
        config=config,
        player=second_player,
    )

    assert assignment is not None
    assert assignment.game_name == "Explore"


async def test_random_unique_game_interrupted_rows_release_quota(async_mongo_provider, write_yaml) -> None:
    """Interrupted work should free the game for later players again."""
    config = _load_strategy_config(write_yaml, name="interrupted-releases", games=["Explore"])
    strategy = get_assignment_strategy("random_unique_game")
    first_player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Interrupted"}})
    second_player, _ = await async_mongo_provider.create_player(player_data={"full_name": {"answer": "Replacement"}})

    await _create_assignment(
        async_mongo_provider,
        player_id=first_player.id,
        game_name="Explore",
        pc_hid="test-char-a",
        status="in_progress",
    )
    interrupted = await async_mongo_provider.get_active_assignment(player_id=first_player.id)
    assert interrupted is not None
    await async_mongo_provider.update_assignment_status(
        assignment_id=interrupted.assignment_id,
        status="interrupted",
    )

    assignment = await strategy.get_or_create_assignment_async(
        provider=async_mongo_provider,
        config=config,
        player=second_player,
    )

    assert assignment is not None
    assert assignment.game_name == "Explore"


async def test_random_unique_player_choice_options_remain_available_with_existing_assignment(async_mongo_provider, write_yaml) -> None:
    """Player-choice mode should still offer another assignment while one is already assigned."""
    config = _load_strategy_config(
        write_yaml,
        name="player-choice-multi",
        games=["Explore", "foresight"],
        max_assignments_per_player=2,
        allow_choice_if_multiple=True,
        require_completion=False,
    )
    strategy = get_assignment_strategy("random_unique_game")
    player, _ = await async_mongo_provider.create_player(
        player_data={
            "full_name": {"answer": "Chooser"},
            "email": "chooser@example.com",
            "consent_signature": {"answer": ["I confirm that the information I have provided is true..."]},
        }
    )

    await _create_assignment(
        async_mongo_provider,
        player_id=player.id,
        game_name="Explore",
        pc_hid="test-char-a",
    )

    options = await strategy.get_eligible_options_async(
        provider=async_mongo_provider,
        config=config,
        player=player,
    )

    assert options, "Expected at least one remaining option after the first assignment"
    assert all(option["game_name"] != "Explore" for option in options)
