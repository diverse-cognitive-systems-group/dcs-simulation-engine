"""Goal Horizon game class."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import SimulationGraphState


class GoalHorizonGame:
    """Game class for the Goal Horizon game."""

    additional_validator_rules: str = ""
    additional_updater_rules: str = ""
    state_overrides: dict = {}

    def build_graph(self, subgraph: CompiledStateGraph) -> CompiledStateGraph:
        """Build the outer LangGraph for the Goal Horizon game, wrapping the simulation subgraph."""
        builder = StateGraph(SimulationGraphState, context_schema=ContextSchema)
        builder.add_edge(START, END)
        return builder.compile()
