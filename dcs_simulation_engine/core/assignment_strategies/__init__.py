"""Assignment strategy registry."""

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentStrategy
from dcs_simulation_engine.core.assignment_strategies.expertise_matched_character_batch import (
    ExpertiseMatchedCharacterBatchAssignmentStrategy,
)
from dcs_simulation_engine.core.assignment_strategies.expertise_matched_character_choice import (
    ExpertiseMatchedCharacterChoiceAssignmentStrategy,
)
from dcs_simulation_engine.core.assignment_strategies.expertise_matched_character_next import (
    ExpertiseMatchedCharacterNextAssignmentStrategy,
)
from dcs_simulation_engine.core.assignment_strategies.full_character_access import FullCharacterAccessAssignmentStrategy
from dcs_simulation_engine.core.assignment_strategies.least_played_combination_next import (
    LeastPlayedCombinationNextAssignmentStrategy,
)
from dcs_simulation_engine.core.assignment_strategies.max_contrast_pairing import MaxContrastPairingAssignmentStrategy
from dcs_simulation_engine.core.assignment_strategies.next_incomplete_combination import (
    NextIncompleteCombinationAssignmentStrategy,
)
from dcs_simulation_engine.core.assignment_strategies.progressive_divergence_assignment import (
    ProgressiveDivergenceAssignmentStrategy,
)
from dcs_simulation_engine.core.assignment_strategies.random_unique import RandomUniqueGameAssignmentStrategy
from dcs_simulation_engine.core.assignment_strategies.unplayed_combination_choice import (
    UnplayedCombinationChoiceAssignmentStrategy,
)

_STRATEGIES: dict[str, AssignmentStrategy] = {
    "full_character_access": FullCharacterAccessAssignmentStrategy(),
    "unplayed_combination_choice": UnplayedCombinationChoiceAssignmentStrategy(),
    "expertise_matched_character_choice": ExpertiseMatchedCharacterChoiceAssignmentStrategy(),
    "next_incomplete_combination": NextIncompleteCombinationAssignmentStrategy(),
    "least_played_combination_next": LeastPlayedCombinationNextAssignmentStrategy(),
    "progressive_divergence_assignment": ProgressiveDivergenceAssignmentStrategy(),
    "max_contrast_pairing": MaxContrastPairingAssignmentStrategy(),
    "expertise_matched_character_next": ExpertiseMatchedCharacterNextAssignmentStrategy(),
    "expertise_matched_character_batch": ExpertiseMatchedCharacterBatchAssignmentStrategy(),
    "random_unique_game": RandomUniqueGameAssignmentStrategy(),
    "random_unique": RandomUniqueGameAssignmentStrategy(),
}


def get_assignment_strategy(strategy_name: str) -> AssignmentStrategy:
    """Resolve one registered assignment strategy by name."""
    normalized = strategy_name.strip().lower()
    try:
        return _STRATEGIES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown assignment strategy: {strategy_name}") from exc
