"""Explore game class."""

from dcs_simulation_engine.core.simulation_graph.config import (
    ConditionalTo,
    Edge,
    ElseOnly,
    GraphConfig,
    IfThen,
    Node,
)
from dcs_simulation_engine.games.const import Explore as C


class ExploreGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = ""

    def build_graph_config(self) -> GraphConfig:
        return GraphConfig(
            name="explore-game-graph",
            description="A game flow graph that sets up and continues a scene including abilities checkpoints for character actions.",
            state_overrides={"user_retry_budget": 10},
            nodes=[
                Node(
                    name="command_filter",
                    kind="builtin.command_filter",
                    kwargs={
                        "command_handlers": {
                            "help": {"simulator_output": {"type": "info", "content": C.HELP_CONTENT}},
                            "abilities": {"simulator_output": {"type": "info", "content": C.ABILITIES_CONTENT}},
                        }
                    },
                ),
                Node(
                    name="enter_message",
                    kind="builtin.update_state",
                    kwargs={
                        "state_updates": {
                            "simulator_output": {"type": "info", "content": C.ENTER_CONTENT},
                            "lifecycle": "UPDATE",
                        }
                    },
                ),
                Node(
                    name="exit_message",
                    kind="builtin.update_state",
                    kwargs={"state_updates": {"simulator_output": {"type": "info", "content": C.EXIT_CONTENT}}},
                ),
                Node(
                    name="complete_message",
                    kind="builtin.update_state",
                    kwargs={"state_updates": {"simulator_output": {"type": "info", "content": C.COMPLETE_CONTENT}}},
                ),
                Node(
                    name="error_in_lifecycle",
                    kind="builtin.raise_error",
                    kwargs={"message": C.ERROR_IN_LIFECYCLE},
                ),
            ],
            edges=[
                Edge(
                    **{
                        "from": "__START__",
                        "to": ConditionalTo(
                            conditional=[
                                IfThen(**{"if": "state['simulator_output']", "then": "__END__"}),
                                IfThen(**{"if": "state['lifecycle'] == 'ENTER'", "then": "enter_message"}),
                                IfThen(**{"if": "state['lifecycle'] == 'EXIT'", "then": "exit_message"}),
                                IfThen(**{"if": "state['lifecycle'] == 'UPDATE'", "then": "command_filter"}),
                                ElseOnly(**{"else": "error_in_lifecycle"}),
                            ]
                        ),
                    }
                ),
                Edge(**{"from": "enter_message", "to": "__SIMULATION_SUBGRAPH__"}),
                Edge(**{"from": "exit_message", "to": "__END__"}),
                Edge(
                    **{
                        "from": "command_filter",
                        "to": ConditionalTo(
                            conditional=[
                                IfThen(**{"if": "state['simulator_output']", "then": "__END__"}),
                                ElseOnly(**{"else": "__SIMULATION_SUBGRAPH__"}),
                            ]
                        ),
                    }
                ),
                Edge(**{"from": "__SIMULATION_SUBGRAPH__", "to": "__END__"}),
            ],
        )
