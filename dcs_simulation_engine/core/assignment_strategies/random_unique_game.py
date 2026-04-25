"""Random unique game assignment strategy module."""

import random
from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy
from dcs_simulation_engine.utils.async_utils import maybe_await


class RandomUniqueGameAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include allowed triplets from games the player has not already been assigned."""

    name = "random_unique_game"

    def validate_config(self, *, config) -> None:
        """Validate the legacy unique-game constraint for this strategy."""
        super().validate_config(config=config)
        if config.assignment_strategy.quota_per_game is None or config.assignment_strategy.quota_per_game <= 0:
            raise ValueError("random_unique_game requires a positive quota_per_game")
        max_assignments = config.assignment_strategy.max_assignments_per_player
        if max_assignments is not None and max_assignments > len(config.games):
            raise ValueError(
                "random_unique_game cannot assign more games per player than are listed in assignment_strategy.games"
            )

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return allowed triplets from unassigned games in deterministic random game order."""
        player_assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        assigned_games = {assignment.game_name for assignment in player_assignments}
        pool = await self._build_candidate_pool(provider=provider, config=config, player=player)
        eligible = [candidate for candidate in pool if candidate.game_name not in assigned_games]
        if not eligible:
            return []

        game_rng = self._rng_for(config=config, player_id=player.id, salt="game")
        grouped: dict[str, list[AssignmentCandidate]] = {}
        for candidate in eligible:
            grouped.setdefault(candidate.game_name, []).append(candidate)

        game_names = list(grouped)
        game_rng.shuffle(game_names)
        ordered: list[AssignmentCandidate] = []
        for game_name in game_names:
            candidates = list(grouped[game_name])
            selection_rng = self._rng_for(config=config, player_id=player.id, salt=f"combo:{game_name}")
            selection_rng.shuffle(candidates)
            ordered.extend(candidates)
        return ordered

    async def generate_remaining_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list:
        """Pre-generate remaining unique-game assignments for legacy tests."""
        existing_assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        if len(existing_assignments) >= self.max_assignments_per_player(config=config):
            return []

        created = []
        assigned_games = {assignment.game_name for assignment in existing_assignments}
        candidates = await self.list_candidate_assignments_async(provider=provider, config=config, player=player)
        for candidate in candidates:
            if len(existing_assignments) + len(created) >= self.max_assignments_per_player(config=config):
                break
            if candidate.game_name in assigned_games:
                continue
            assignment = await maybe_await(
                provider.create_assignment(
                    assignment_doc=self._assignment_doc_for_candidate(config=config, player=player, candidate=candidate),
                    allow_concurrent=True,
                )
            )
            if assignment is not None:
                assigned_games.add(candidate.game_name)
                created.append(assignment)
        return created

    def _rng_for(self, *, config, player_id: str, salt: str) -> random.Random:
        seed_value = config.assignment_strategy.seed or config.name
        return random.Random(f"{seed_value}:{player_id}:{salt}")
