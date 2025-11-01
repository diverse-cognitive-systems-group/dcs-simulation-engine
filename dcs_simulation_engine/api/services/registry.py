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

from loguru import logger

from dcs_simulation_engine.core.run_manager import RunManager


class SimRegistry:
    """In-memory registry of SimulationManager instances.

    Attributes:
        _store (Dict[str, SimulationManager]): Internal map of id -> manager.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._store: Dict[str, RunManager] = {}

    def create_from_yaml(self, path: str) -> tuple[str, RunManager]:
        """Create and store a RunManager from a YAML file.

        Args:
            path (str): Filesystem path to the simulation YAML.

        Returns:
            tuple[str, SimulationManager]: The generated sim ID and the instance.
        """
        logger.debug(f"Loading simulation from {path}")
        sim: RunManager = RunManager.from_yaml(path)
        sim_id = uuid4().hex
        self._store[sim_id] = sim
        return sim_id, sim

    def get(self, sim_id: str) -> Optional[RunManager]:
        """Retrieve a RunManager by ID.

        Args:
            sim_id (str): Identifier assigned at creation.

        Returns:
            Optional[SimulationManager]: The found manager or None.
        """
        return self._store.get(sim_id)

    def remove(self, sim_id: str) -> None:
        """Remove a SimulationManager by ID.

        Args:
            sim_id (str): Identifier assigned at creation.
        """
        self._store.pop(sim_id, None)


# Notes:
# - Single global registry instance for simplicity; swap for DI container if needed.
_registry = SimRegistry()


def get_registry() -> SimRegistry:
    """FastAPI dependency provider for the global registry.

    Returns:
        SimRegistry: The singleton registry instance.
    """
    return _registry
