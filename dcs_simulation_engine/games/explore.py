"""Explore game class."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from dcs_simulation_engine.core.simulation_graph.builtins import (
    command_filter,
    raise_error,
    update_state,
)
from dcs_simulation_engine.core.simulation_graph.conditions import predicate
from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import SimulationGraphState
from dcs_simulation_engine.games.const import Explore as C

_SUBGRAPH_NODE = "__SIMULATION_SUBGRAPH__"

_COMMAND_HANDLERS = {
    "help": {"simulator_output": {"type": "info", "content": C.HELP_CONTENT}},
    "abilities": {"simulator_output": {"type": "info", "content": C.ABILITIES_CONTENT}},
}


def _node_command_filter(state: SimulationGraphState, runtime: Runtime[ContextSchema]):
    return command_filter(state=state, context=runtime.context, command_handlers=_COMMAND_HANDLERS)


def _node_enter_message(state: SimulationGraphState, runtime: Runtime[ContextSchema]):
    return update_state(
        state=state,
        context=runtime.context,
        state_updates={
            "simulator_output": {"type": "info", "content": C.ENTER_CONTENT},
            "lifecycle": "UPDATE",
        },
    )


def _node_exit_message(state: SimulationGraphState, runtime: Runtime[ContextSchema]):
    return update_state(
        state=state,
        context=runtime.context,
        state_updates={"simulator_output": {"type": "info", "content": C.EXIT_CONTENT}},
    )


def _node_error_in_lifecycle(state: SimulationGraphState, runtime: Runtime[ContextSchema]):
    return raise_error(state=state, context=runtime.context, message=C.ERROR_IN_LIFECYCLE)


def _route_start(state: SimulationGraphState) -> str:
    if predicate("state['simulator_output']", state):
        return "__END__"
    if predicate("state['lifecycle'] == 'ENTER'", state):
        return "enter_message"
    if predicate("state['lifecycle'] == 'EXIT'", state):
        return "exit_message"
    if predicate("state['lifecycle'] == 'UPDATE'", state):
        return "command_filter"
    return "error_in_lifecycle"


def _route_command_filter(state: SimulationGraphState) -> str:
    if predicate("state['simulator_output']", state):
        return "__END__"
    return _SUBGRAPH_NODE


class ExploreGame:
    """Game class for the Explore game."""

    additional_validator_rules: str = ""
    additional_updater_rules: str = ""
    state_overrides: dict = {"user_retry_budget": 10}

    def build_graph(self, subgraph: CompiledStateGraph) -> CompiledStateGraph:
        """Build the outer LangGraph for the Explore game, wrapping the simulation subgraph."""
        builder = StateGraph(SimulationGraphState, context_schema=ContextSchema)

        builder.add_node("command_filter", _node_command_filter)
        builder.add_node("enter_message", _node_enter_message)
        builder.add_node("exit_message", _node_exit_message)
        builder.add_node("error_in_lifecycle", _node_error_in_lifecycle)
        builder.add_node(_SUBGRAPH_NODE, subgraph)

        builder.add_conditional_edges(
            START,
            _route_start,
            {
                "__END__": END,
                "enter_message": "enter_message",
                "exit_message": "exit_message",
                "command_filter": "command_filter",
                "error_in_lifecycle": "error_in_lifecycle",
            },
        )
        builder.add_edge("enter_message", _SUBGRAPH_NODE)
        builder.add_edge("exit_message", END)
        builder.add_conditional_edges(
            "command_filter",
            _route_command_filter,
            {
                "__END__": END,
                _SUBGRAPH_NODE: _SUBGRAPH_NODE,
            },
        )
        builder.add_edge(_SUBGRAPH_NODE, END)

        return builder.compile()
