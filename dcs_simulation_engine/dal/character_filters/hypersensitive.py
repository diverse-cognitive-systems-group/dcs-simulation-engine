"""Character filter: hypersensitive characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord

_HYPERSENSITIVE_LABELS = frozenset({
    "highly sensitive person (hsp)",
    "autistic",
    "sensory divergence",
    "anxiety",
    "hypervigilance",
})


class HypersensitiveFilter:
    """Returns characters with sensory hypersensitivity profiles.

    Matches any character whose common_labels overlap with the
    hypersensitive label set (e.g. DS, JW, JAB, WS).
    """

    name = "hypersensitive"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        return [
            r
            for r in provider.get_characters()
            if _HYPERSENSITIVE_LABELS & set(r.data.get("common_labels", []))
        ]
