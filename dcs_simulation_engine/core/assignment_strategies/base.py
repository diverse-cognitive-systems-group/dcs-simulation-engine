"""Assignment strategy protocol for experiment workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from dcs_simulation_engine.core.experiment_config import ExperimentConfig
    from dcs_simulation_engine.dal.base import AssignmentRecord, PlayerRecord


class AssignmentStrategy(Protocol):
    """Behavior contract for experiment assignment strategies."""

    name: str

    def validate_config(self, *, config: "ExperimentConfig") -> None:
        """Validate strategy-specific config constraints."""

    def max_assignments_per_player(self, *, config: "ExperimentConfig") -> int:
        """Return the maximum number of assignments one player may complete."""

    async def compute_progress_async(self, *, provider: Any, config: "ExperimentConfig") -> dict[str, Any]:
        """Return experiment progress payload for the public API."""

    async def compute_status_async(self, *, provider: Any, config: "ExperimentConfig") -> dict[str, Any]:
        """Return experiment status payload for the public API."""

    async def get_or_create_assignment_async(
        self,
        *,
        provider: Any,
        config: "ExperimentConfig",
        player: "PlayerRecord",
    ) -> "AssignmentRecord | None":
        """Return the current assignment for a player or create one."""
