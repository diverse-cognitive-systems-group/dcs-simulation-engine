"""Max-contrast pairing assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class MaxContrastPairingAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include allowed triplets ordered by descending pc-to-npc divergence."""

    name = "max_contrast_pairing"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return allowed triplets ordered by descending pc-to-npc divergence."""
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        characters_by_hid = await self._character_map(provider=provider)
        game_order = {game_name: index for index, game_name in enumerate(config.game_names)}
        return self._sort_by_descending_contrast(
            candidates=candidates,
            characters_by_hid=characters_by_hid,
            game_order=game_order,
        )
