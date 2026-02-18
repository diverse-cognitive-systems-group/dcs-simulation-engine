"""Shared services for the Gradio widget and API.

This module provides shared services accessible to both the widget UI handlers
and the programmatic API functions.
"""

from __future__ import annotations

from typing import Dict, Optional

from dcs_simulation_engine.core.run_manager import RunManager


class RunRegistry:
    """In-memory registry of RunManager instances.

    Provides storage and retrieval of live RunManager objects keyed by run ID.
    The registry is shared between UI handlers and API functions.

    Notes:
        - Not persistent. A process restart clears the registry.
        - Not multiprocess-safe. Replace with a DB or shared cache if needed.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._store: Dict[str, RunManager] = {}

    def add(self, run_id: str, run: RunManager) -> None:
        """Add a RunManager to the registry.

        Args:
            run_id: Identifier for the run.
            run: The RunManager instance to store.
        """
        self._store[run_id] = run

    def get(self, run_id: str) -> Optional[RunManager]:
        """Retrieve a RunManager by ID.

        Args:
            run_id: Identifier assigned at creation.

        Returns:
            The found manager or None if not found.
        """
        return self._store.get(run_id)

    def remove(self, run_id: str) -> None:
        """Remove a RunManager by ID.

        Args:
            run_id: Identifier assigned at creation.
        """
        self._store.pop(run_id, None)

    def list_runs(self) -> list[str]:
        """List all run IDs in the registry.

        Returns:
            List of run IDs.
        """
        return list(self._store.keys())


# Global singleton instance
_registry = RunRegistry()


def get_registry() -> RunRegistry:
    """Get the global RunRegistry singleton.

    Returns:
        The singleton registry instance.
    """
    return _registry
