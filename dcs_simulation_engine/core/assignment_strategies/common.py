"""Shared helpers for candidate-based assignment strategies."""

import re
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentCandidate
from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.mongo.const import MongoColumns
from dcs_simulation_engine.utils.async_utils import maybe_await
from dcs_simulation_engine.utils.divergence import compute_divergence_score

if TYPE_CHECKING:
    from dcs_simulation_engine.core.run_config import RunConfig
    from dcs_simulation_engine.dal.base import AssignmentRecord, PlayerRecord


def _tokenize(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", text.lower()) if token}


def candidate_to_dict(candidate: AssignmentCandidate) -> dict[str, str]:
    """Serialize one candidate for API responses."""
    return {
        "game_name": candidate.game_name,
        "pc_hid": candidate.pc_hid,
        "npc_hid": candidate.npc_hid,
    }


class CandidateAssignmentStrategy:
    """Shared implementation for strategies that emit candidate assignments."""

    name = ""

    def validate_config(self, *, config: "RunConfig") -> None:
        """Validate strategy config shared across candidate-based strategies."""
        if not config.game_names:
            raise ValueError(f"{self.name} requires run config games")
        if config.assignment_strategy.quota_per_game is not None and config.assignment_strategy.quota_per_game <= 0:
            raise ValueError(f"{self.name} requires a positive quota_per_game")

        max_assignments = config.assignment_strategy.max_assignments_per_player
        if max_assignments is not None and max_assignments <= 0:
            raise ValueError(f"{self.name} requires max_assignments_per_player to be positive")

    def max_assignments_per_player(self, *, config: "RunConfig") -> int:
        """Return the configured per-player assignment cap for this strategy."""
        configured = config.assignment_strategy.max_assignments_per_player
        if configured is None:
            return len(config.game_names)
        return max(0, int(configured))

    async def compute_progress_async(self, *, provider: Any, config: "RunConfig") -> dict[str, Any]:
        """Compute quota-based experiment progress for the configured games."""
        quota = config.assignment_strategy.quota_per_game
        completed_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["completed"],
        )
        counted_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress", "completed"],
        )
        completed_total = sum(len(players) for players in completed_players_by_game.values())
        if quota is None:
            return {
                "total": completed_total,
                "completed": completed_total,
                "is_complete": False,
            }
        quota_count = int(quota)
        return {
            "total": quota_count * len(config.game_names),
            "completed": completed_total,
            "is_complete": all(len(counted_players_by_game.get(game_name, set())) >= quota_count for game_name in config.game_names),
        }

    async def compute_status_async(self, *, provider: Any, config: "RunConfig") -> dict[str, Any]:
        """Compute per-game status counts and overall experiment openness."""
        quota = config.assignment_strategy.quota_per_game
        completed_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["completed"],
        )
        in_progress_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress"],
        )
        counted_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress", "completed"],
        )

        per_game: dict[str, dict[str, int]] = {}
        quota_count = int(quota) if quota is not None else 0
        for game_name in config.game_names:
            per_game[game_name] = {
                "total": quota_count,
                "completed": len(completed_players_by_game.get(game_name, set())),
                "in_progress": len(in_progress_players_by_game.get(game_name, set())),
            }

        if quota is None:
            return {
                "is_open": True,
                "total": sum(item["completed"] for item in per_game.values()),
                "completed": sum(item["completed"] for item in per_game.values()),
                "per_game": per_game,
            }
        return {
            "is_open": any(len(counted_players_by_game.get(game_name, set())) < quota_count for game_name in config.game_names),
            "total": quota_count * len(config.game_names),
            "completed": sum(item["completed"] for item in per_game.values()),
            "per_game": per_game,
        }

    async def list_candidate_assignments_async(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        player: "PlayerRecord",
    ) -> list[AssignmentCandidate]:
        """Return ordered candidate assignments for the player."""
        raise NotImplementedError

    async def get_eligible_options_async(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        player: "PlayerRecord",
    ) -> list[dict[str, str]]:
        """Return serialized candidate assignment options."""
        candidates = await self.list_candidate_assignments_async(provider=provider, config=config, player=player)
        return [candidate_to_dict(candidate) for candidate in candidates]

    async def get_or_create_assignment_async(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        player: "PlayerRecord",
    ) -> "AssignmentRecord | None":
        """Return an existing assignment or create one from this strategy's candidates."""
        reusable_assignment = await self._reusable_assignment_or_none(provider=provider, config=config, player=player)
        if reusable_assignment is not None:
            return reusable_assignment

        player_assignments = await self._list_player_assignments(provider=provider, config=config, player=player)
        completed_count = sum(1 for item in player_assignments if item.status == "completed")
        if completed_count >= self.max_assignments_per_player(config=config):
            return None

        candidates = await self.list_candidate_assignments_async(provider=provider, config=config, player=player)
        if not candidates:
            return None

        selected = candidates[0]
        return await maybe_await(
            provider.create_assignment(
                assignment_doc=self._assignment_doc_for_candidate(config=config, player=player, candidate=selected),
                allow_concurrent=not config.assignment_strategy.require_completion,
            )
        )

    async def _reusable_assignment_or_none(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        player: "PlayerRecord",
    ) -> "AssignmentRecord | None":
        active_assignment = await maybe_await(provider.get_active_assignment(experiment_name=config.name, player_id=player.id))
        if active_assignment is None:
            return None
        if config.assignment_strategy.require_completion:
            return active_assignment
        if active_assignment.status in {"assigned", "in_progress"}:
            return active_assignment
        return None

    def _assignment_doc_for_candidate(
        self,
        *,
        config: "RunConfig",
        player: "PlayerRecord",
        candidate: AssignmentCandidate,
    ) -> dict[str, Any]:
        assignment_doc: dict[str, Any] = {
            MongoColumns.EXPERIMENT_NAME: config.name,
            MongoColumns.PLAYER_ID: player.id,
            MongoColumns.GAME_NAME: candidate.game_name,
            MongoColumns.PC_HID: candidate.pc_hid,
            MongoColumns.NPC_HID: candidate.npc_hid,
            MongoColumns.STATUS: "assigned",
            MongoColumns.FORM_RESPONSES: {},
        }
        if candidate.metadata:
            assignment_doc.update(candidate.metadata)
        return assignment_doc

    async def _build_candidate_pool(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        player: "PlayerRecord",
    ) -> list[AssignmentCandidate]:
        counted_players_by_game = await self._players_by_game(
            provider=provider,
            experiment_name=config.name,
            statuses=["in_progress", "completed"],
        )
        quota = config.assignment_strategy.quota_per_game
        pc_eligible_only = bool(config.assignment_strategy.pc_eligible_only)
        candidates: list[AssignmentCandidate] = []

        for game_name in config.game_names:
            if quota is not None and len(counted_players_by_game.get(game_name, set())) >= int(quota):
                continue
            game_config = SessionManager.get_game_config_cached(game_name)
            get_valid = getattr(game_config, "get_valid_characters_async", None)
            if get_valid is None:
                valid_pcs, valid_npcs = await maybe_await(
                    game_config.get_valid_characters(
                        player_id=player.id,
                        provider=provider,
                        pc_eligible_only=pc_eligible_only,
                    )
                )
            else:
                valid_pcs, valid_npcs = await maybe_await(
                    get_valid(
                        player_id=player.id,
                        provider=provider,
                        pc_eligible_only=pc_eligible_only,
                    )
                )
            for _, pc_hid in valid_pcs:
                for _, npc_hid in valid_npcs:
                    candidates.append(AssignmentCandidate(game_name=game_name, pc_hid=pc_hid, npc_hid=npc_hid))
        return candidates

    async def _list_player_assignments(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        player: "PlayerRecord",
    ) -> list["AssignmentRecord"]:
        return await maybe_await(provider.list_assignments(experiment_name=config.name, player_id=player.id))

    async def _players_by_game(
        self,
        *,
        provider: Any,
        experiment_name: str,
        statuses: list[str],
    ) -> dict[str, set[str]]:
        assignments = await maybe_await(provider.list_assignments(experiment_name=experiment_name, statuses=statuses))
        players_by_game: dict[str, set[str]] = defaultdict(set)
        for assignment in assignments:
            players_by_game[assignment.game_name].add(assignment.player_id)
        return players_by_game

    async def _assignments_by_group(
        self,
        *,
        provider: Any,
        config: "RunConfig",
        statuses: list[str],
    ) -> dict[tuple[str, str], int]:
        assignments = await maybe_await(provider.list_assignments(experiment_name=config.name, statuses=statuses))
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for assignment in assignments:
            counts[(assignment.game_name, assignment.npc_hid)] += 1
        return counts

    async def _character_map(self, *, provider: Any) -> dict[str, CharacterRecord]:
        characters = await maybe_await(provider.get_characters())
        return {record.hid: record for record in characters}

    def _completed_triple_counts(self, *, assignments: list["AssignmentRecord"]) -> dict[tuple[str, str, str], int]:
        counts: dict[tuple[str, str, str], int] = defaultdict(int)
        for assignment in assignments:
            if assignment.status == "completed":
                counts[(assignment.game_name, assignment.pc_hid, assignment.npc_hid)] += 1
        return counts

    def _completed_group_keys(self, *, assignments: list["AssignmentRecord"]) -> set[tuple[str, str]]:
        return {
            (assignment.game_name, assignment.npc_hid)
            for assignment in assignments
            if assignment.status == "completed"
        }

    def _latest_completed_assignment(self, *, assignments: list["AssignmentRecord"]) -> "AssignmentRecord | None":
        completed = [assignment for assignment in assignments if assignment.status == "completed"]
        if not completed:
            return None
        return completed[-1]

    def _expertise_match_hids(
        self,
        *,
        player: "PlayerRecord",
        characters_by_hid: dict[str, CharacterRecord],
    ) -> set[str]:
        expertise = str(player.data.get("expertise") or "").strip()
        if not expertise:
            return set()
        expertise_tokens = _tokenize(expertise)
        if not expertise_tokens:
            return set()
        matched_hids: set[str] = set()
        for hid, character in characters_by_hid.items():
            labels = character.data.get("common_labels", [])
            label_tokens: set[str] = set()
            for label in labels if isinstance(labels, list) else []:
                label_tokens.update(_tokenize(str(label)))
            if expertise_tokens & label_tokens:
                matched_hids.add(hid)
        return matched_hids

    def _sort_with_expertise_priority(
        self,
        *,
        candidates: list[AssignmentCandidate],
        matched_npc_hids: set[str],
        game_order: dict[str, int],
    ) -> list[AssignmentCandidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                0 if candidate.npc_hid in matched_npc_hids else 1,
                game_order[candidate.game_name],
                candidate.pc_hid,
                candidate.npc_hid,
            ),
        )

    def _sort_by_descending_divergence(
        self,
        *,
        candidates: list[AssignmentCandidate],
        reference_npc: CharacterRecord,
        characters_by_hid: dict[str, CharacterRecord],
        fallback_counts: dict[tuple[str, str], int] | None = None,
        game_order: dict[str, int],
    ) -> list[AssignmentCandidate]:
        group_scores: dict[tuple[str, str], float] = {}
        for candidate in candidates:
            key = (candidate.game_name, candidate.npc_hid)
            if key in group_scores:
                continue
            npc = characters_by_hid.get(candidate.npc_hid)
            group_scores[key] = compute_divergence_score(reference_npc, npc) if npc is not None else 0.0
        return sorted(
            candidates,
            key=lambda candidate: (
                -group_scores[(candidate.game_name, candidate.npc_hid)],
                (fallback_counts or {}).get((candidate.game_name, candidate.npc_hid), 0),
                game_order[candidate.game_name],
                candidate.npc_hid,
                candidate.pc_hid,
            ),
        )

    def _sort_by_descending_contrast(
        self,
        *,
        candidates: list[AssignmentCandidate],
        characters_by_hid: dict[str, CharacterRecord],
        game_order: dict[str, int],
    ) -> list[AssignmentCandidate]:
        def _score(candidate: AssignmentCandidate) -> float:
            pc = characters_by_hid.get(candidate.pc_hid)
            npc = characters_by_hid.get(candidate.npc_hid)
            if pc is None or npc is None:
                return 0.0
            return compute_divergence_score(pc, npc)

        return sorted(
            candidates,
            key=lambda candidate: (
                -_score(candidate),
                game_order[candidate.game_name],
                candidate.pc_hid,
                candidate.npc_hid,
            ),
        )
