"""Full-character-access assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class FullCharacterAccessAssignmentStrategy(CandidateAssignmentStrategy):
    """Allow the player to choose from any permitted PC/NPC combination."""

    name = "full_character_access"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return every allowed game, PC, and NPC combination for the player."""
        return await self._build_candidate_pool(provider=provider, config=config, player=player)
