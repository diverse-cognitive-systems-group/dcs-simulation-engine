"""Character filter registry."""

from dcs_simulation_engine.dal.character_filters.all import AllCharactersFilter
from dcs_simulation_engine.dal.character_filters.base import CharacterFilter
from dcs_simulation_engine.dal.character_filters.divergent import DivergentFilter
from dcs_simulation_engine.dal.character_filters.human import HumanFilter
from dcs_simulation_engine.dal.character_filters.human_normative import HumanNormativeFilter
from dcs_simulation_engine.dal.character_filters.hypersensitive import HypersensitiveFilter
from dcs_simulation_engine.dal.character_filters.hyposensitive import HyposensitiveFilter
from dcs_simulation_engine.dal.character_filters.neurodivergent import NeurodivergentFilter
from dcs_simulation_engine.dal.character_filters.neurotypical import NeurotypicalFilter
from dcs_simulation_engine.dal.character_filters.non_human import NonHumanFilter
from dcs_simulation_engine.dal.character_filters.pc_eligible import PcEligibleFilter
from dcs_simulation_engine.dal.character_filters.physical_divergence import PhysicalDivergenceFilter

_FILTERS: dict[str, CharacterFilter] = {
    f.name: f  # type: ignore[misc]
    for f in [
        AllCharactersFilter(),
        PcEligibleFilter(),
        HumanFilter(),
        NonHumanFilter(),
        HumanNormativeFilter(),
        NeurotypicalFilter(),
        DivergentFilter(),
        NeurodivergentFilter(),
        PhysicalDivergenceFilter(),
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


def list_character_filter_names() -> tuple[str, ...]:
    """Return all registered character filter names in a stable order."""
    return tuple(sorted(_FILTERS))
