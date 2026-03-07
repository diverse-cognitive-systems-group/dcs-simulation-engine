"""Infer Intent game class."""

from dcs_simulation_engine.core.simulation_graph.config import (
    ConditionalTo,
    Edge,
    ElseOnly,
    GraphConfig,
    IfThen,
    Node,
)
from dcs_simulation_engine.games.const import InferIntent as C


class InferIntentGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = C.ADDITIONAL_UPDATER_RULES

    def build_graph_config(self) -> GraphConfig:
        return GraphConfig(
            name="infer-intent-graph",
            description="A game flow graph that sets up and continues a scene where the system character is using their abilities to communicate a goal/intention.",
            state_overrides={
                "user_retry_budget": 3,
                "forms": {
                    "completion_form": {
                        "questions": [
                            {
                                "key": "user_goal_inference",
                                "text": "What do you think the NPC's goal or intention was during this interaction? Please describe in a few sentences.",
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
            },
            nodes=[
                Node(
                    name="command_filter",
                    kind="builtin.command_filter",
                    kwargs={
                        "command_handlers": {
                            "help": {"simulator_output": {"type": "info", "content": C.HELP_CONTENT}},
                            "abilities": {"simulator_output": {"type": "info", "content": C.ABILITIES_CONTENT}},
                            "guess": {"lifecycle": "COMPLETE"},
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
                    name="score_inference",
                    kind="builtin.llm_eval",
                    kwargs={
                        "template_name": "inference_scorer",
                        "model_key": "llm_eval",
                        "guess_form": "completion_form",
                        "guess_key": "user_goal_inference",
                        "result_key": "evaluation",
                        "display_result": False,
                    },
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
                                IfThen(**{"if": "state['lifecycle'] == 'EXIT'", "then": "score_inference"}),
                                ElseOnly(**{"else": "__END__"}),
                            ]
                        ),
                    }
                ),
                Edge(**{"from": "score_inference", "to": "exit_message"}),
            ],
        )
