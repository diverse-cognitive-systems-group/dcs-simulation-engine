"""Character filter protocol."""

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from dcs_simulation_engine.dal.base import CharacterRecord


class CharacterFilter(Protocol):
    """Contract for character filter implementations."""

    name: str

    def get_characters(self, *, provider: Any) -> "list[CharacterRecord]":
        """Return all characters from provider that match this filter."""
