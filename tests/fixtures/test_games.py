"""Test-only game class fixtures used in conftest.py."""

from dcs_simulation_engine.core.simulation_graph.config import (
    ConditionalTo,
    Edge,
    ElseOnly,
    GraphConfig,
    IfThen,
    Node,
)

_OUTPUT_FORMAT = (
    'Output Format: {"events": [{"type": "assistant", "content": "<your reply here>"}]}'
)


class MinimalTestGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = ""

    def build_graph_config(self) -> GraphConfig:
        return GraphConfig(
            name="minimal-test-graph",
            nodes=[
                Node(
                    name="echoNode",
                    kind="custom",
                    provider="openrouter",
                    model="openai/gpt-oss-20b:free",
                    additional_kwargs={},
                    system_template=f"Echo back any input message.\n{_OUTPUT_FORMAT}",
                )
            ],
            edges=[
                Edge(**{"from": "__START__", "to": "echoNode"}),
                Edge(**{"from": "echoNode", "to": "__END__"}),
            ],
        )


class BranchingTestGame:
    additional_validator_rules: str = ""
    additional_updater_rules: str = ""

    def build_graph_config(self) -> GraphConfig:
        return GraphConfig(
            name="simple-test-graph",
            nodes=[
                Node(
                    name="scene_setup_agent",
                    kind="custom",
                    provider="openrouter",
                    model="openai/gpt-oss-20b:free",
                    additional_kwargs={},
                    system_template=f"Reply with 'SETUP_SCENE' ONLY.\n{_OUTPUT_FORMAT}",
                ),
                Node(
                    name="scene_continuation_agent",
                    kind="custom",
                    provider="openrouter",
                    model="openai/gpt-oss-20b:free",
                    additional_kwargs={},
                    system_template=f"Reply with 'CONTINUE_SCENE' ONLY.\n{_OUTPUT_FORMAT}",
                ),
            ],
            edges=[
                Edge(**{"from": "__START__", "to": ConditionalTo(conditional=[
                    IfThen(**{"if": "len(messages) == 0", "then": "scene_setup_agent"}),
                    ElseOnly(**{"else": "scene_continuation_agent"}),
                ])}),
                Edge(**{"from": "scene_setup_agent", "to": "__END__"}),
                Edge(**{"from": "scene_continuation_agent", "to": "__END__"}),
            ],
        )
