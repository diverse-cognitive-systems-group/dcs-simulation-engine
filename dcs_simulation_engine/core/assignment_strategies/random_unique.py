"""Random unique assignment strategy implementation."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.utils.async_utils import maybe_await

if TYPE_CHECKING:
    from dcs_simulation_engine.core.experiment_config import ExperimentConfig
    from dcs_simulation_engine.dal.base import AssignmentRecord, PlayerRecord


class RandomUniqueAssignmentStrategy:
    """Assign each player a deterministic random game without repeats."""

    name = "random_unique"

    def validate_config(self, *, config: "ExperimentConfig") -> None:
        """Validate the required knobs for the random-unique strategy."""
        if not config.assignment_strategy.games:
            raise ValueError("random_unique requires assignment_strategy.games")
        if config.assignment_strategy.quota_per_game is None or config.assignment_strategy.quota_per_game <= 0:
            raise ValueError("random_unique requires a positive quota_per_game")

        max_assignments = config.assignment_strategy.max_assignments_per_player
        if max_assignments is not None and max_assignments <= 0:
            raise ValueError("random_unique requires max_assignments_per_player to be positive")
        if max_assignments is not None and max_assignments > len(config.games):
            raise ValueError(
                "random_unique cannot assign more games per player than are listed in assignment_strategy.games"
            )

    def max_assignments_per_player(self, *, config: "ExperimentConfig") -> int:
        """Return the configured max assignments, capped by the game list."""
        configured = config.assignment_strategy.max_assignments_per_player
        if configured is None:
            return len(config.games)
        return min(int(configured), len(config.games))

    async def compute_progress_async(self, *, provider: Any, config: "ExperimentConfig") -> dict[str, Any]:
        """Compute progress while closing the study on counted quota saturation."""
        quota = int(config.assignment_strategy.quota_per_game or 0)
        completed_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["completed"],
        )
        counted_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress", "completed"],
        )

        completed_total = sum(len(players) for players in completed_players_by_game.values())
        return {
            "total": quota * len(config.games),
            "completed": completed_total,
            "is_complete": all(
                len(counted_players_by_game.get(game_name, set())) >= quota for game_name in config.games
            ),
        }

    async def compute_status_async(self, *, provider: Any, config: "ExperimentConfig") -> dict[str, Any]:
        """Compute per-game counts with quota openness based on active plus finished players."""
        quota = int(config.assignment_strategy.quota_per_game or 0)
        completed_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["completed"],
        )
        in_progress_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress"],
        )
        counted_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress", "completed"],
        )

        per_game: dict[str, dict[str, int]] = {}
        for game_name in config.games:
            per_game[game_name] = {
                "total": quota,
                "completed": len(completed_players_by_game.get(game_name, set())),
                "in_progress": len(in_progress_players_by_game.get(game_name, set())),
            }

        completed_total = sum(item["completed"] for item in per_game.values())
        return {
            "is_open": any(len(counted_players_by_game.get(game_name, set())) < quota for game_name in config.games),
            "total": quota * len(config.games),
            "completed": completed_total,
            "per_game": per_game,
        }

    async def get_or_create_assignment_async(
        self,
        *,
        provider: Any,
        config: "ExperimentConfig",
        player: "PlayerRecord",
    ) -> "AssignmentRecord | None":
        """Reuse active work or create a new random unique assignment for a player."""
        active_assignment = await maybe_await(
            provider.get_active_assignment(experiment_name=config.name, player_id=player.id)
        )
        if active_assignment is not None:
            return active_assignment

        player_assignments = await maybe_await(
            provider.list_assignments(experiment_name=config.name, player_id=player.id)
        )
        completed_count = sum(1 for item in player_assignments if item.status == "completed")
        if completed_count >= self.max_assignments_per_player(config=config):
            return None

        counted_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress", "completed"],
        )
        quota = int(config.assignment_strategy.quota_per_game or 0)
        assigned_games = {item.game_name for item in player_assignments}
        eligible_games = [
            game_name
            for game_name in config.games
            if game_name not in assigned_games and len(counted_players_by_game.get(game_name, set())) < quota
        ]
        if not eligible_games:
            return None

        game_rng = self._rng_for(config=config, player_id=player.id, salt="game")
        game_candidates = list(eligible_games)
        game_rng.shuffle(game_candidates)

        for game_name in game_candidates:
            game_config = SessionManager.get_game_config_cached(game_name)
            get_valid = getattr(game_config, "get_valid_characters_async", None)
            if get_valid is None:
                valid_pcs, _ = await maybe_await(
                    game_config.get_valid_characters(player_id=player.id, provider=provider)
                )
            else:
                valid_pcs, _ = await maybe_await(get_valid(player_id=player.id, provider=provider))

            valid_pc_hids = [hid for _, hid in valid_pcs]
            if not valid_pc_hids:
                continue

            pc_rng = self._rng_for(config=config, player_id=player.id, salt=f"pc:{game_name}")
            character_hid = pc_rng.choice(valid_pc_hids)
            return await maybe_await(
                provider.create_assignment(
                    assignment_doc={
                        MongoColumns.EXPERIMENT_NAME: config.name,
                        MongoColumns.PLAYER_ID: player.id,
                        MongoColumns.GAME_NAME: game_name,
                        MongoColumns.CHARACTER_HID: character_hid,
                        MongoColumns.STATUS: "assigned",
                        MongoColumns.FORM_RESPONSES: {},
                    }
                )
            )

        return None

    async def _players_by_game(
        self,
        *,
        provider: Any,
        experiment_name: str,
        statuses: list[str],
    ) -> dict[str, set[str]]:
        """Group unique player ids by game for the requested assignment states."""
        assignments = await maybe_await(provider.list_assignments(experiment_name=experiment_name, statuses=statuses))
        players_by_game: dict[str, set[str]] = defaultdict(set)
        for assignment in assignments:
            players_by_game[assignment.game_name].add(assignment.player_id)
        return players_by_game

    def _rng_for(self, *, config: "ExperimentConfig", player_id: str, salt: str) -> random.Random:
        """Derive a deterministic RNG for one player and selection phase."""
        seed_value = config.assignment_strategy.seed or config.name
        return random.Random(f"{seed_value}:{player_id}:{salt}")
