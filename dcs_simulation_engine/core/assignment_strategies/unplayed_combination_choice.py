"""Unplayed-combination assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class UnplayedCombinationChoiceAssignmentStrategy(CandidateAssignmentStrategy):
    """Prioritize combinations the player has not completed yet."""

    name = "unplayed_combination_choice"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Order candidates by how often the player has completed the exact triple."""
        game_order = {game_name: index for index, game_name in enumerate(config.games)}
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
