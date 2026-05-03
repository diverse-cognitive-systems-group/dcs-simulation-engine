"""Next-incomplete-combination assignment strategy."""

from collections import defaultdict
from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class NextIncompleteCombinationAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include triplets for the first incomplete game + npc group in config order."""

    name = "next_incomplete_combination"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return triplets for the first incomplete game + npc group in config order."""
        assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        completed_groups = self._completed_group_keys(assignments=assignments)
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        grouped: dict[tuple[str, str], list[AssignmentCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.game_name, candidate.npc_hid)].append(candidate)

        for game_name in config.game_names:
            matching_groups = sorted(key for key in grouped if key[0] == game_name)
            for key in matching_groups:
                if key not in completed_groups:
                    return grouped[key]
        return []
