"""Character filter: human-normative characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


class HumanNormativeFilter:
    """Returns human characters with a neurotypical/normative profile.

    Matches characters where is_human=True and 'neurotypical' appears in
    common_labels (e.g. NA, NB).
    """

    name = "human-normative"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return human characters labelled as neurotypical."""
        return [r for r in provider.get_characters() if r.data.get("is_human", False) and "neurotypical" in r.data.get("common_labels", [])]
