"""Character filter: hyposensitive characters."""

from typing import Any

from dcs_simulation_engine.dal.base import CharacterRecord

_HYPOSENSITIVE_LABELS = frozenset(
    {
        "ADHD",
        "attention regulation divergence",
    }
)


class HyposensitiveFilter:
    """Returns characters with sensory hyposensitivity profiles.

    Matches any character whose common_labels overlap with the
    hyposensitive label set (e.g. KAT).
    """

    name = "hyposensitive"

    def get_characters(self, *, provider: Any) -> list[CharacterRecord]:
        """Return characters whose labels match the hyposensitive set."""
        return [r for r in provider.get_characters() if _HYPOSENSITIVE_LABELS & set(r.data.get("common_labels", []))]
