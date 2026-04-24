"""Character filter: characters with any non-normative HSN divergence."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord
from dcs_simulation_engine.dal.character_filters._hsn_helpers import has_any_non_normative_hsn_divergence


class DivergentFilter:
    """Returns characters with at least one non-normative HSN divergence value."""

    name = "divergent"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters with any non-normative HSN divergence."""
        return [r for r in provider.get_characters() if has_any_non_normative_hsn_divergence(r.data.get("hsn_divergence"))]
