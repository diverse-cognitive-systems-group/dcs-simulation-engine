"""Character filter: PC-eligible characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


class PcEligibleFilter:
    """Returns characters that are eligible to be used as PCs."""

    name = "pc-eligible"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters whose pc_eligible flag is truthy."""
        return [r for r in provider.get_characters() if r.data.get("pc_eligible", False)]
