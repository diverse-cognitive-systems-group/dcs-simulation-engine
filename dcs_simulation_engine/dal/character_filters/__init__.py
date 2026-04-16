"""Character filter registry."""

from dcs_simulation_engine.dal.character_filters.all import AllCharactersFilter
from dcs_simulation_engine.dal.character_filters.base import CharacterFilter
from dcs_simulation_engine.dal.character_filters.human_normative import HumanNormativeFilter
from dcs_simulation_engine.dal.character_filters.hypersensitive import HypersensitiveFilter
from dcs_simulation_engine.dal.character_filters.hyposensitive import HyposensitiveFilter
from dcs_simulation_engine.dal.character_filters.neurotypical import NeurotypicalFilter

_FILTERS: dict[str, CharacterFilter] = {
    f.name: f  # type: ignore[misc]
    for f in [
        AllCharactersFilter(),
        HumanNormativeFilter(),
        NeurotypicalFilter(),
        HypersensitiveFilter(),
        HyposensitiveFilter(),
    ]
}


def get_character_filter(name: str) -> CharacterFilter:
    """Resolve a registered character filter by name."""
    try:
        return _FILTERS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown character filter: {name!r}. Valid: {sorted(_FILTERS)}") from exc
