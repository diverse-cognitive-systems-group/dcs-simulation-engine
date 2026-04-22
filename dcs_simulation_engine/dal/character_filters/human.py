"""Character filter: human characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


class HumanFilter:
    """Returns only human characters."""

    name = "human"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters whose is_human flag is truthy."""
        return [r for r in provider.get_characters() if r.data.get("is_human", False)]
