"""Test-only game class fixtures used in conftest.py."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from dcs_simulation_engine.core.simulation_graph.conditions import predicate
from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import SimulationGraphState

_SUBGRAPH_NODE = "__SIMULATION_SUBGRAPH__"


class MinimalTestGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = ""
    state_overrides: dict = {}

    def build_graph(self, subgraph: CompiledStateGraph) -> CompiledStateGraph:
        builder = StateGraph(SimulationGraphState, context_schema=ContextSchema)
        builder.add_node(_SUBGRAPH_NODE, subgraph)
        builder.add_edge(START, _SUBGRAPH_NODE)
        builder.add_edge(_SUBGRAPH_NODE, END)
        return builder.compile()


class BranchingTestGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = ""
    state_overrides: dict = {}

    def build_graph(self, subgraph: CompiledStateGraph) -> CompiledStateGraph:
        builder = StateGraph(SimulationGraphState, context_schema=ContextSchema)
        builder.add_node(_SUBGRAPH_NODE, subgraph)

        def _route(state: SimulationGraphState) -> str:
            if predicate("state['lifecycle'] == 'ENTER'", state):
                return _SUBGRAPH_NODE
            return "__END__"

        builder.add_conditional_edges(START, _route, {
            _SUBGRAPH_NODE: _SUBGRAPH_NODE,
            "__END__": END,
        })
        builder.add_edge(_SUBGRAPH_NODE, END)
        return builder.compile()
