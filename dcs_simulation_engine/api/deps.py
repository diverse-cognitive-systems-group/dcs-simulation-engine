"""Dependency utilities for route handlers.

Provides reusable dependency functions for resolving shared services
and objects (e.g., looking up a SimulationManager by ID).
"""

from fastapi import Depends, HTTPException

from dcs_simulation_engine.api.services.registry import RunRegistry, get_registry
from dcs_simulation_engine.core.run_manager import RunManager


def get_manager(
    run_id: str, registry: RunRegistry = Depends(get_registry)
) -> RunManager:
    """Resolve a RunManager from the registry.

    Args:
        run_id (str): Identifier of a run in the registry.
        registry (RunRegistry): The in-memory registry (injected).

    Returns:
        RunManager: The RunManager instance associated with the given ID.

    Raises:
        HTTPException: If the run ID is not found in the registry.
    """
    mgr = registry.get(run_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return mgr
