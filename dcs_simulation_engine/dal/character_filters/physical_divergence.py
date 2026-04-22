"""Character filter: characters with physical-ability HSN divergence."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters._hsn_helpers import section_has_non_normative_assumption


class PhysicalDivergenceFilter:
    """Returns characters with non-normative physical-ability HSN divergence."""

    name = "physical-divergence"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters with non-normative physical-ability divergence."""
        return [
            r
            for r in provider.get_characters()
            if isinstance(r.data.get("hsn_divergence"), dict)
            and section_has_non_normative_assumption(r.data["hsn_divergence"].get("physical_ability_assumptions"))
        ]
