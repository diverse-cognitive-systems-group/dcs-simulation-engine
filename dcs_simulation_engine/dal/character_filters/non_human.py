"""Character filter: non-human characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


class NonHumanFilter:
    """Returns only non-human characters."""

    name = "non-human"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters whose is_human flag is falsy."""
        return [r for r in provider.get_characters() if not r.data.get("is_human", False)]
