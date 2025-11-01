"""Dependency utilities for route handlers.

Provides reusable dependency functions for resolving shared services
and objects (e.g., looking up a SimulationManager by ID).
"""

from fastapi import Depends, HTTPException

from dcs_simulation_engine.api.services.registry import SimRegistry, get_registry
from dcs_simulation_engine.core.run_manager import RunManager


def get_manager(sim_id: str, registry: SimRegistry = Depends(get_registry)) -> "RunManager":
    """Resolve a RunManager from the registry.

    Args:
        sim_id (str): Identifier of a simulation in the registry.
        registry (SimRegistry): The in-memory registry (injected).

    Returns:
        RunManager: The RunManager instance associated with the given ID.

    Raises:
        HTTPException: If the simulation ID is not found in the registry.
    """
    mgr = registry.get(sim_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return mgr
