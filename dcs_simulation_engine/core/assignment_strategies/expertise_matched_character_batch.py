"""Expertise-matched batch assignment strategy."""

from typing import Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.assignment_strategies.common import CandidateAssignmentStrategy


class ExpertiseMatchedCharacterBatchAssignmentStrategy(CandidateAssignmentStrategy):
    """Candidate assignments include triplets for the current NPC batch until its games are completed."""

    name = "expertise_matched_character_batch"

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config,
        player,
    ) -> list[AssignmentCandidate]:
        """Return triplets for the current NPC batch until its configured games are completed."""
        candidates = await self._build_candidate_pool(provider=provider, config=config, player=player)
        if not candidates:
            return []

        player_assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        completed_games_by_npc: dict[str, set[str]] = {}
        for assignment in player_assignments:
            if assignment.status != "completed":
                continue
            completed_games_by_npc.setdefault(assignment.npc_hid, set()).add(assignment.game_name)

        active_batch_npc = self._active_batch_npc(config=config, assignments=player_assignments)
        characters_by_hid = await self._character_map(provider=provider)
        matched_npc_hids = self._expertise_match_hids(player=player, characters_by_hid=characters_by_hid)
        game_order = {game_name: index for index, game_name in enumerate(config.games)}
        npc_order = self._ordered_npcs(
            candidates=candidates,
            matched_npc_hids=matched_npc_hids,
            game_order=game_order,
        )

        target_npc = active_batch_npc
        if target_npc is None:
            for npc_hid in npc_order:
                completed_games = completed_games_by_npc.get(npc_hid, set())
                if len(completed_games) < len(config.games):
                    target_npc = npc_hid
                    break
        if target_npc is None:
            return []

        remaining_games = [
            game_name
            for game_name in config.games
            if game_name not in completed_games_by_npc.get(target_npc, set())
        ]
        if not remaining_games:
            return []

        next_game = remaining_games[0]
        batch_id = f"{config.name}:{player.id}:{target_npc}"
        return [
            AssignmentCandidate(
                game_name=candidate.game_name,
                pc_hid=candidate.pc_hid,
                npc_hid=candidate.npc_hid,
                metadata={"batch_id": batch_id, "batch_npc_hid": target_npc},
            )
            for candidate in candidates
            if candidate.game_name == next_game and candidate.npc_hid == target_npc
        ]

    def _active_batch_npc(self, *, config, assignments) -> str | None:
        for assignment in reversed(assignments):
            batch_npc_hid = str(assignment.data.get("batch_npc_hid") or "").strip()
            if not batch_npc_hid:
                continue
            completed_games = {
                item.game_name
                for item in assignments
                if item.status == "completed" and str(item.data.get("batch_npc_hid") or "") == batch_npc_hid
            }
            if len(completed_games) < len(config.games):
                return batch_npc_hid
        return None

    def _ordered_npcs(
        self,
        *,
        candidates: list[AssignmentCandidate],
        matched_npc_hids: set[str],
        game_order: dict[str, int],
    ) -> list[str]:
        seen: set[str] = set()
        ordered_npcs: list[str] = []
        for candidate in sorted(
            candidates,
            key=lambda item: (
                0 if item.npc_hid in matched_npc_hids else 1,
                game_order[item.game_name],
                item.npc_hid,
                item.pc_hid,
            ),
        ):
            if candidate.npc_hid in seen:
                continue
            seen.add(candidate.npc_hid)
            ordered_npcs.append(candidate.npc_hid)
        return ordered_npcs
