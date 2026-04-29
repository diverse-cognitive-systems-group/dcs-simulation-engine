"""Expertise-matched next assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class ExpertiseMatchedCharacterNextAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include allowed triplets ordered with expertise-matching NPCs first."""

    name = "expertise_matched_character_next"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return allowed triplets ordered with expertise-matching NPCs first."""
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        characters_by_hid = await self._character_map(provider=provider)
        matched_npc_hids = await self._expertise_match_hids(
            provider=provider,
            config=config,
            player=player,
            characters_by_hid=characters_by_hid,
        )
        game_order = {game_name: index for index, game_name in enumerate(config.game_names)}
        return self._sort_with_expertise_priority(
            candidates=candidates,
            matched_npc_hids=matched_npc_hids,
            game_order=game_order,
        )
