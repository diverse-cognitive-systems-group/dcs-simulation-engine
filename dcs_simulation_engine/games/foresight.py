"""Foresight game class."""

from dcs_simulation_engine.core.simulation_graph.config import (
    ConditionalTo,
    Edge,
    ElseOnly,
    GraphConfig,
    IfThen,
    Node,
)
from dcs_simulation_engine.games.const import Foresight as C


class ForesightGame:
    additional_validator_rules: str = C.ADDITIONAL_VALIDATOR_RULES
    additional_updater_rules: str = C.ADDITIONAL_UPDATER_RULES

    def build_graph_config(self) -> GraphConfig:
        return GraphConfig(
            name="foresight_graph",
            description="A PC engages with a NPC in as many scenes and actions as desired. When the PC feels confident, it uses the '/predict' command to submit a prediction about the NPCs next action.",
            state_overrides={
                "forms": {
                    "completion_form": {
                        "questions": [
                            {
                                "key": "additional_notes",
                                "text": "Do you have any additional notes or other feedback? Any predictions you made that were particularly interesting or challenging? Please describe in a few sentences.",
                                "answer": "",
                            },
                        ]
                    }
                }
            },
            nodes=[
                Node(
                    name="command_filter",
                    kind="builtin.command_filter",
                    kwargs={
                        "command_handlers": {
                            "help": {"simulator_output": {"type": "info", "content": C.HELP_CONTENT}},
                            "complete": {"lifecycle": "COMPLETE"},
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
                    name="completion_form",
                    kind="builtin.form",
                    kwargs={"form_name": "completion_form"},
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
                                IfThen(**{"if": "state['lifecycle'] == 'COMPLETE'", "then": "completion_form"}),
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
                                IfThen(**{"if": "state['lifecycle'] == 'COMPLETE'", "then": "completion_form"}),
                                ElseOnly(**{"else": "__SIMULATION_SUBGRAPH__"}),
                            ]
                        ),
                    }
                ),
                Edge(
                    **{
                        "from": "completion_form",
                        "to": ConditionalTo(
                            conditional=[
                                IfThen(**{"if": "state['lifecycle'] == 'EXIT'", "then": "exit_message"}),
                                ElseOnly(**{"else": "__END__"}),
                            ]
                        ),
                    }
                ),
            ],
        )
