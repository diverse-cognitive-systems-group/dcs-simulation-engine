"""Goal Horizon game class."""

from dcs_simulation_engine.core.simulation_graph.config import Edge, GraphConfig


class GoalHorizonGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = ""

    def build_graph_config(self) -> GraphConfig:
        return GraphConfig(
            name="goal_horizon_graph",
            description="A graph for interacting with a character to understand a characters goals over multiple interactions.",
            nodes=[],
            edges=[Edge(**{"from": "__START__", "to": "__END__"})],
        )
