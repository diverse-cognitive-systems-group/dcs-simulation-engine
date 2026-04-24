"""Least-played-combination assignment strategy."""

from collections import defaultdict
from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class LeastPlayedCombinationNextAssignmentStrategy(CandidateAssignmentStrategy):
    """Prefer the globally least-played game/NPC group."""

    name = "least_played_combination_next"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return candidates for the globally least-played game/NPC group."""
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        if not candidates:
            return []

        game_order = {game_name: index for index, game_name in enumerate(config.games)}
        counts = await self._assignments_by_group(
            provider=provider,
            config=config,
            statuses=["in_progress", "completed"],
        )
        grouped: dict[tuple[str, str], list[AssignmentCandidate]] = defaultdict(list)
        for candidate in candidates:
            grouped[(candidate.game_name, candidate.npc_hid)].append(candidate)

        selected_key = min(
            grouped,
            key=lambda key: (
                counts.get(key, 0),
                game_order[key[0]],
                key[1],
            ),
        )
        return grouped[selected_key]
