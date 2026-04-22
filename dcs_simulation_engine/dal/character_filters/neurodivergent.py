"""Character filter: characters with neuro-style HSN divergence."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters._hsn_helpers import section_has_non_normative_assumption


class NeurodivergentFilter:
    """Returns characters with non-normative cognitive or communication HSN divergence."""

    name = "neurodivergent"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters with non-normative cognitive/perceptual or neurotypical-communication divergence."""
        results: list[CharacterRecord] = []
        for record in provider.get_characters():
            divergence = record.data.get("hsn_divergence")
            if not isinstance(divergence, dict):
                continue
            if section_has_non_normative_assumption(divergence.get("cognitive_and_perceptual_assumptions")):
                results.append(record)
                continue
            social_section = divergence.get("social_and_communicative_assumptions")
            if not isinstance(social_section, dict):
                continue
            communication = social_section.get("neurotypical_communication")
            if isinstance(communication, dict):
                value = communication.get("value")
                if value is not None and value != "normative":
                    results.append(record)
        return results
