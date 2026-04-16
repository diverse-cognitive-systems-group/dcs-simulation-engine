"""Character filter: neurotypical characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord


class NeurotypicalFilter:
    """Returns characters labelled neurotypical (human or non-human).

    Matches any character where 'neurotypical' appears in common_labels
    (e.g. NA, NB).
    """

    name = "neurotypical"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        return [
            r
            for r in provider.get_characters()
            if "neurotypical" in r.data.get("common_labels", [])
        ]
