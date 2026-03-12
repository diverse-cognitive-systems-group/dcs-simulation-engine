"""Tests for the SimGraph module."""

import pytest
from dcs_simulation_engine.core.simulation_graph import (
    SimulationGraph,
    SimulationGraphState,
)
from dcs_simulation_engine.core.simulation_graph.config import (
    ConditionalTo,
    Edge,
    ElseOnly,
    GraphConfig,
    IfThen,
    Node,
)
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from loguru import logger


# ---------- Helper: build common GraphConfig objects ----------

_SIMPLE_OUTPUT_FORMAT = (
    'Output Format: {"events": [{"type": "assistant", "content": "<your reply here>"}]}'
)


def _simple_graph_config() -> GraphConfig:
    """Simple 2-node linear graph."""
    return GraphConfig(
        name="simple-test-graph",
        nodes=[
            Node(
                name="agent1",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template=f"Reply with 'H' ONLY.\n{_SIMPLE_OUTPUT_FORMAT}",
            ),
            Node(
                name="agent2",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template=(
                    "What is the letter is in the agent_artifacts text field? "
                    f"Reply with the letter ONLY.\n{_SIMPLE_OUTPUT_FORMAT}"
                ),
            ),
        ],
        edges=[
            Edge(**{"from": "__START__", "to": "agent1"}),
            Edge(**{"from": "agent1", "to": "agent2"}),
            Edge(**{"from": "agent2", "to": "__END__"}),
        ],
    )


def _conditional_graph_config() -> GraphConfig:
    """Conditional graph routing based on len(messages)."""
    return GraphConfig(
        name="conditional-test-graph",
        nodes=[
            Node(
                name="agentA",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template=f"Reply with '37' ONLY.\n{_SIMPLE_OUTPUT_FORMAT}",
            ),
            Node(
                name="agentB",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template=f"Reply with '92' ONLY.\n{_SIMPLE_OUTPUT_FORMAT}",
            ),
        ],
        edges=[
            Edge(**{"from": "__START__", "to": ConditionalTo(conditional=[
                IfThen(**{"if": "len(messages) == 0", "then": "agentA"}),
                ElseOnly(**{"else": "agentB"}),
            ])}),
            Edge(**{"from": "agentA", "to": "__END__"}),
            Edge(**{"from": "agentB", "to": "__END__"}),
        ],
    )


# ---------- Validation tests ----------

@pytest.mark.unit
def test_compile_fails_on_missing_node() -> None:
    """Should throw LangGraph error when an edge references a node that doesn't exist.

    Note: This check ONLY LangGraph's built-in checks (no custom validation needed).
    """
    graph_config = GraphConfig(
        name="invalid-missing-node",
        nodes=[
            Node(
                name="agentA",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template="Reply with 'A' ONLY.",
            ),
        ],
        edges=[
            Edge(**{"from": "__START__", "to": "agentB"}),  # agentB doesn't exist
        ],
    )
    assert graph_config.name == "invalid-missing-node"

    with pytest.raises(ValueError):
        SimulationGraph.compile(graph_config)


@pytest.mark.skip(reason="TODO - fails because langgraph autopatches???")
def test_compile_fails_when_end_unreachable() -> None:
    """Custom validation: END must be reachable from START.

    Graph has a START edge but no path to __end__.
    """
    graph_config = GraphConfig(
        name="invalid-end-unreachable",
        nodes=[
            Node(
                name="agentA",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template="Reply with 'A' ONLY.",
            ),
        ],
        edges=[
            Edge(**{"from": "__START__", "to": "agentA"}),
            # (no edges to __END__)
        ],
    )
    assert graph_config.name == "invalid-end-unreachable"

    with pytest.raises(ValueError):
        SimulationGraph.compile(graph_config)


@pytest.mark.unit
def test_simple_graph() -> None:
    """Builds a simple 2-node linear graph and compiles."""
    graph_config = _simple_graph_config()
    logger.debug(f"graph_config: {graph_config}")
    graph = SimulationGraph.compile(graph_config)
    assert isinstance(graph.cgraph, CompiledStateGraph)

    g = graph.cgraph.get_graph()
    node_names = set(g.nodes.keys())
    assert node_names == {
        "__start__",
        "agent1",
        "agent2",
        "__end__",
        "__SIMULATION_SUBGRAPH__",
    }


@pytest.mark.slow
def test_invoke_simple() -> None:
    """Invokes the simple graph and verifies the output."""
    logger.warning(
        "NOTE: this makes a live call to a free model on OpenRouter \
                   so its flaky and slow you may have to run it a couple \
                   of times in the OR nodes are overloaded...doesn't mean \
                   something is wrong with the code"
    )

    graph_config = _simple_graph_config()
    graph = SimulationGraph.compile(graph_config)

    out = graph.cgraph.invoke({"messages": []})
    print("Final output state:", out)
    assert isinstance(out, dict)
    assert "messages" in out and isinstance(out["messages"], list)
    assert all(hasattr(m, "content") for m in out["messages"])
    assert [m.content for m in out["messages"]] == ["H"]


# ---------- Conditional graph ----------


@pytest.mark.unit
def test_conditional_graph() -> None:
    """Compiles a graph with conditional edges and verifies topology."""
    graph_config = _conditional_graph_config()
    assert graph_config.name == "conditional-test-graph"

    graph = SimulationGraph.compile(graph_config)
    assert isinstance(graph.cgraph, CompiledStateGraph)

    g = graph.cgraph.get_graph()
    node_names = set(g.nodes.keys())
    assert node_names == {
        "__start__",
        "agentA",
        "agentB",
        "__end__",
        "__SIMULATION_SUBGRAPH__",
    }


@pytest.mark.slow
def test_invoke_conditional() -> None:
    """Invokes the conditional graph through correct branches."""
    graph_config = _conditional_graph_config()
    graph = SimulationGraph.compile(graph_config)

    # Branch: len(messages) == 0 -> agentA -> __end__
    assert graph.cgraph is not None
    out_empty = graph.cgraph.invoke({"messages": []})
    assert isinstance(out_empty, dict)
    assert "messages" in out_empty and isinstance(out_empty["messages"], list)
    assert all(hasattr(m, "content") for m in out_empty["messages"])
    assert any("37" in m.content for m in out_empty["messages"])

    # Branch: len(messages) > 0 -> agentB -> __end__
    out_nonempty = graph.cgraph.invoke(
        {"messages": [HumanMessage(content="Here is a test message")]}
    )
    assert isinstance(out_nonempty, dict)
    assert "messages" in out_nonempty and isinstance(out_nonempty["messages"], list)
    assert all(hasattr(m, "content") for m in out_nonempty["messages"])
    assert any("92" in m.content for m in out_nonempty["messages"])


# ---------- Jinja tests (slow, live LLM calls) ----------

@pytest.mark.slow
def test_jinja_populates() -> None:
    """Verifies system_template with Jinja variables are rendered from state."""
    logger.warning(
        "This test makes a live call to OpenRouter free model, so may be flaky. "
        "If the test fails, try running it again....doesn't necessarily mean "
        "something is wrong with the code."
    )
    graph_config = GraphConfig(
        name="jinja-test-graph",
        nodes=[
            Node(
                name="echoChar",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template="Reply with '{{ pc.name }}' ONLY.\n" + _SIMPLE_OUTPUT_FORMAT,
            ),
        ],
        edges=[
            Edge(**{"from": "__START__", "to": "echoChar"}),
            Edge(**{"from": "echoChar", "to": "__END__"}),
        ],
    )

    graph = SimulationGraph.compile(graph_config)
    assert isinstance(graph.cgraph, CompiledStateGraph)

    state: SimulationGraphState = {
        "messages": [],
        "agent_artifacts": {},
        "pc": {"name": "JANIE"},
        "npc": {"name": "JACOB"},
    }
    print(f"SimState before invoke: {state}")

    out = graph.cgraph.invoke(state)
    assert isinstance(out, dict)
    assert "messages" in out and isinstance(out["messages"], list)
    assert all(hasattr(m, "content") for m in out["messages"])
    assert any("JANIE" in m.content for m in out["messages"])


# TODO: test jinja population failures are easy to diagnose


@pytest.mark.slow
def test_jinja_works_with_dynamic_input() -> None:
    """Verifies system_template with Jinja conditionals render correctly."""
    logger.warning(
        "This test makes a live call to OpenRouter free model, so may be flaky. "
        "If the test fails, try running it again....doesn't necessarily mean "
        "something is wrong with the code."
    )
    graph_config = GraphConfig(
        name="jinja-test-graph",
        nodes=[
            Node(
                name="echoChar",
                kind="custom",
                provider="openrouter",
                model="openai/gpt-oss-20b:free",
                additional_kwargs={},
                system_template=(
                    "Reply with\n"
                    "{% if extras.conditional_flag %}\n"
                    "'TRUE' ONLY.\n"
                    "{% else %}\n"
                    "'FALSE' ONLY.\n"
                    "{% endif %}\n"
                    + _SIMPLE_OUTPUT_FORMAT
                ),
            ),
        ],
        edges=[
            Edge(**{"from": "__START__", "to": "echoChar"}),
            Edge(**{"from": "echoChar", "to": "__END__"}),
        ],
    )

    graph = SimulationGraph.compile(graph_config)
    assert isinstance(graph.cgraph, CompiledStateGraph)

    state: SimulationGraphState = {
        "messages": [],
        "agent_artifacts": {},
        "pc": {"name": "JANIE"},
        "npc": {"name": "JACOB"},
        "extras": {
            "conditional_flag": False,
        },
    }
    print(f"SimState before invoke: {state}")

    out = graph.cgraph.invoke(state)
    assert isinstance(out, dict)
    assert "messages" in out and isinstance(out["messages"], list)
    assert all(hasattr(m, "content") for m in out["messages"])
    assert any("FALSE" in m.content for m in out["messages"])
    state["extras"]["conditional_flag"] = True
    out = graph.cgraph.invoke(state)
    assert any("TRUE" in m.content for m in out["messages"])
