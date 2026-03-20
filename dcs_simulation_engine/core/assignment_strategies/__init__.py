"""Assignment strategy registry."""

from dcs_simulation_engine.core.assignment_strategies.base import AssignmentStrategy
from dcs_simulation_engine.core.assignment_strategies.random_unique import RandomUniqueAssignmentStrategy

_STRATEGIES: dict[str, AssignmentStrategy] = {
    "random_unique": RandomUniqueAssignmentStrategy(),
}


def get_assignment_strategy(strategy_name: str) -> AssignmentStrategy:
    """Resolve one registered assignment strategy by name."""
    normalized = strategy_name.strip().lower()
    try:
        return _STRATEGIES[normalized]
    except KeyError as exc:
        raise ValueError(f"Unknown assignment strategy: {strategy_name}") from exc
