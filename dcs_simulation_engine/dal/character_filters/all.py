"""Character filter: all characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


class AllCharactersFilter:
    """Returns every character from the database with no filtering."""

    name = "all"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return all characters from the provider without filtering."""
        return list(provider.get_characters())
