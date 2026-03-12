"""Infer Intent game class."""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from dcs_simulation_engine.core.simulation_graph.builtins import (
    command_filter,
    form,
    llm_eval,
    raise_error,
    update_state,
)
from dcs_simulation_engine.core.simulation_graph.conditions import predicate
from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import SimulationGraphState
from dcs_simulation_engine.games.const import InferIntent as C

_SUBGRAPH_NODE = "__SIMULATION_SUBGRAPH__"

_COMMAND_HANDLERS = {
    "help": {"simulator_output": {"type": "info", "content": C.HELP_CONTENT}},
    "abilities": {"simulator_output": {"type": "info", "content": C.ABILITIES_CONTENT}},
    "guess": {"lifecycle": "COMPLETE"},
}

_STATE_OVERRIDES = {
    "user_retry_budget": 3,
    "forms": {
        "completion_form": {
            "questions": [
                {
                    "key": "user_goal_inference",
                    "text": (
                        "What do you think the NPC's goal or intention was during this interaction?"
                        " Please describe in a few sentences."
                    ),
                    "answer": "",
                },
                {
                    "key": "other_feedback",
                    "text": "Do you have any other feedback about this experience?",
                    "answer": "",
                },
            ]
        }
    },
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


def _node_completion_form(state: SimulationGraphState, runtime: Runtime[ContextSchema]):
    return form(state=state, context=runtime.context, form_name="completion_form")


def _node_score_inference(state: SimulationGraphState, runtime: Runtime[ContextSchema]):
    return llm_eval(
        state=state,
        context=runtime.context,
        template_name="inference_scorer",
        model_key="llm_eval",
        guess_form="completion_form",
        guess_key="user_goal_inference",
        result_key="evaluation",
        display_result=False,
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
    if predicate("state['lifecycle'] == 'COMPLETE'", state):
        return "completion_form"
    if predicate("state['lifecycle'] == 'UPDATE'", state):
        return "command_filter"
    return "error_in_lifecycle"


def _route_command_filter(state: SimulationGraphState) -> str:
    if predicate("state['simulator_output']", state):
        return "__END__"
    if predicate("state['lifecycle'] == 'COMPLETE'", state):
        return "completion_form"
    return _SUBGRAPH_NODE


def _route_completion_form(state: SimulationGraphState) -> str:
    if predicate("state['lifecycle'] == 'EXIT'", state):
        return "score_inference"
    return "__END__"


class InferIntentGame:
    """Game class for the Infer Intent game."""

    additional_validator_rules: str = ""
    additional_updater_rules: str = C.ADDITIONAL_UPDATER_RULES
    state_overrides: dict = _STATE_OVERRIDES

    def build_graph(self, subgraph: CompiledStateGraph) -> CompiledStateGraph:
        """Build the outer LangGraph for the Infer Intent game, wrapping the simulation subgraph."""
        builder = StateGraph(SimulationGraphState, context_schema=ContextSchema)

        builder.add_node("command_filter", _node_command_filter)
        builder.add_node("enter_message", _node_enter_message)
        builder.add_node("exit_message", _node_exit_message)
        builder.add_node("completion_form", _node_completion_form)
        builder.add_node("score_inference", _node_score_inference)
        builder.add_node("error_in_lifecycle", _node_error_in_lifecycle)
        builder.add_node(_SUBGRAPH_NODE, subgraph)

        builder.add_conditional_edges(
            START,
            _route_start,
            {
                "__END__": END,
                "enter_message": "enter_message",
                "exit_message": "exit_message",
                "completion_form": "completion_form",
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
                "completion_form": "completion_form",
                _SUBGRAPH_NODE: _SUBGRAPH_NODE,
            },
        )
        builder.add_conditional_edges(
            "completion_form",
            _route_completion_form,
            {
                "score_inference": "score_inference",
                "__END__": END,
            },
        )
        builder.add_edge("score_inference", "exit_message")

        return builder.compile()
