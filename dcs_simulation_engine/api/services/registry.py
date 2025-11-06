"""Simple in-memory registry for SimulationManager instances.

This module encapsulates a minimal service layer for storing and
retrieving live `SimulationManager` objects keyed by a generated ID.

Notes/Assumptions:
    - This is *not* persistent. A process restart clears the registry.
    - Not multiprocess-safe. Replace with a DB or shared cache if needed.
    - IDs are random UUID4 hex strings.
"""

from __future__ import annotations

from typing import Dict, Optional
from uuid import uuid4

from dcs_simulation_engine.core.run_manager import RunManager


class RunRegistry:
    """In-memory registry of RunManager instances.

    Attributes:
        _store (Dict[str, RunManager]): Internal map of id -> manager.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._store: Dict[str, RunManager] = {}

    def create(self) -> tuple[str, RunManager]:
        """Create and store a new RunManager instance.

        Returns:
            tuple[str, RunManager]: The generated run ID and the instance.
        """
        run = RunManager.create(
            game=game,
            source="api",
            pc_choice=payload.pc_choice,
            npc_choice=payload.npc_choice,
            access_key=payload.access_key,
            player_id=payload.player_id,
        )
        run_id = uuid4().hex
        self._store[run_id] = run
        return run_id, run

    def get(self, run_id: str) -> Optional[RunManager]:
        """Retrieve a RunManager by ID.

        Args:
            run_id (str): Identifier assigned at creation.

        Returns:
            Optional[RunManager]: The found manager or None.
        """
        return self._store.get(run_id)

    def remove(self, run_id: str) -> None:
        """Remove a RunManager by ID.

        Args:
            run_id (str): Identifier assigned at creation.
        """
        self._store.pop(run_id, None)


# Notes:
# - Single global registry instance for simplicity; swap for DI container if needed.
_registry = RunRegistry()


def get_registry() -> RunRegistry:
    """FastAPI dependency provider for the global registry.

    Returns:
        RunRegistry: The singleton registry instance.
    """
    return _registry
