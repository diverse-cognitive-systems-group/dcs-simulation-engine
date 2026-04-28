"""Unplayed-combination assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class UnplayedCombinationChoiceAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include allowed triplets ordered with never-played triplets first."""

    name = "unplayed_combination_choice"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return allowed triplets ordered by ascending player completion count for the exact triplet."""
        game_order = {game_name: index for index, game_name in enumerate(config.game_names)}
        assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        triple_counts = self._completed_triple_counts(assignments=assignments)
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        return sorted(
            candidates,
            key=lambda candidate: (
                triple_counts[(candidate.game_name, candidate.pc_hid, candidate.npc_hid)],
                game_order[candidate.game_name],
                candidate.pc_hid,
                candidate.npc_hid,
            ),
        )
