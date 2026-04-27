"""Progressive-divergence assignment strategy."""

from collections import defaultdict
from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy
from dcs_simulation_engine.core.assignment_strategies.least_played_combination_next import (
    LeastPlayedCombinationNextAssignmentStrategy,
)


class ProgressiveDivergenceAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include triplets ordered by descending divergence from the last completed NPC."""

    name = "progressive_divergence_assignment"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return triplets ordered by descending divergence from the player's last completed NPC."""
        assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        latest_completed = self._latest_completed_assignment(assignments=assignments)
        if latest_completed is None:
            fallback = LeastPlayedCombinationNextAssignmentStrategy()
            return await fallback.list_candidate_assignments_async(provider=provider, config=config, player=player)

        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        if not candidates:
            return []

        characters_by_hid = await self._character_map(provider=provider)
        reference_npc = characters_by_hid.get(latest_completed.npc_hid)
        if reference_npc is None:
            fallback = LeastPlayedCombinationNextAssignmentStrategy()
            return await fallback.list_candidate_assignments_async(provider=provider, config=config, player=player)

        counts = await self._assignments_by_group(
            provider=provider,
            config=config,
            statuses=["in_progress", "completed"],
        )
        game_order = {game_name: index for index, game_name in enumerate(config.games)}
        ranked = self._sort_by_descending_divergence(
            candidates=candidates,
            reference_npc=reference_npc,
            characters_by_hid=characters_by_hid,
            fallback_counts=counts,
            game_order=game_order,
        )
        grouped: dict[tuple[str, str], list[AssignmentCandidate]] = defaultdict(list)
        for candidate in ranked:
            grouped[(candidate.game_name, candidate.npc_hid)].append(candidate)
        top = ranked[0]
        return grouped[(top.game_name, top.npc_hid)]
