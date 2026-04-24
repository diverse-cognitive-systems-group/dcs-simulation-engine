"""Expertise-matched choice assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class ExpertiseMatchedCharacterChoiceAssignmentStrategy(CandidateAssignmentStrategy):
    """Prioritize NPCs whose labels match the player's expertise."""

    name = "expertise_matched_character_choice"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return candidates ordered so expertise-matching NPCs appear first."""
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        characters_by_hid = await self._character_map(provider=provider)
        matched_npc_hids = self._expertise_match_hids(player=player, characters_by_hid=characters_by_hid)
        game_order = {game_name: index for index, game_name in enumerate(config.games)}
        return self._sort_with_expertise_priority(
            candidates=candidates,
            matched_npc_hids=matched_npc_hids,
            game_order=game_order,
        )
