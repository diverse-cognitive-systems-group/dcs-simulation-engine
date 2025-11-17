"""Tests for the SimGraph module."""

import textwrap
from pathlib import Path
from typing import Callable

import pytest
from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from dcs_simulation_engine.core.simulation_graph import (
    GraphConfig,
    SimulationGraph,
    SimulationGraphState,
)

# @pytest.mark.unit
# def test_schema_fields_sync() -> None:
#     """Ensure SimulationGraphState and NodeOutputSchema have the same fields."""
#     state_fields = set(SimulationGraphState.__annotations__.keys())
#     node_output_fields = set(SimulationGraph.NodeOutputSchema.__annotations__.keys())
#     assert state_fields == node_output_fields


@pytest.mark.unit
def test_compile_fails_on_missing_node(write_yaml: Callable[[str, str], Path]) -> None:
    """Should throw LangGraph error when an edge references a node that doesn't exist.

    Note: This check ONLY LangGraph's built-in checks (no custom validation needed).
    """
    yml = """
    name: invalid-missing-node
    nodes:
      - name: agentA
        kind: custom
        provider: openrouter
        model: openai/gpt-oss-20b:free
        additional_kwargs: {}
        system_template: |
          Reply with 'A' ONLY.
          Output Format: {
              "events": [
                {
                  "type": "assistant",
                  "content": "<your reply here>"
                }
              ]
            }
    edges:
      - from: __START__
        to: agentB   # <-- missing node on purpose
    """
    p = write_yaml("invalid-missing-node.yml", yml)
    graph_config = GraphConfig.from_yaml(p)
    # make sure graph_config is loaded correctly
    assert graph_config.name == "invalid-missing-node"

    with pytest.raises(ValueError):
        SimulationGraph.compile(graph_config)


@pytest.mark.skip(reason="TODO - fails because langgraph autopatches???")
def test_compile_fails_when_end_unreachable(
    write_yaml: Callable[[str, str], Path],
) -> None:
    """Custom validation: END must be reachable from START.

    YAML has a START edge but no path to __end__.
    """
    yml = """
    name: invalid-end-unreachable
    nodes:
      - name: agentA
        provider: openrouter
        model: openai/gpt-oss-20b:free
        additional_kwargs: {}
        system_prompt_template: "Reply with 'A' ONLY."
    edges:
      - from: __start__
        to: agentA
      # (no edges to __end__)
    """
    p = write_yaml("invalid-end-unreachable.yml", yml)
    graph_config = GraphConfig.from_yaml(p)
    assert graph_config.name == "invalid-end-unreachable"

    with pytest.raises(ValueError):
        SimulationGraph.compile(graph_config)


# ---------- Simple graph ----------


def _write_simple_yaml(path: Path) -> None:
    """Simple 2-node linear graph using the new schema."""
    cfg = textwrap.dedent(
        """
        name: simple-test-graph
        nodes:
          - name: agent1
            kind: custom
            provider: openrouter
            model: openai/gpt-oss-20b:free
            additional_kwargs: {}
            system_template: |
              Reply with 'H' ONLY.
              Output Format: {
                "events": [
                  {
                    "type": "assistant",
                    "content": "<your reply here>"
                  }
                ]
              }
          - name: agent2
            kind: custom
            provider: openrouter
            model: openai/gpt-oss-20b:free
            additional_kwargs: {}
            system_template: |
              What is the letter is in the agent_artifacts text field? 
              Reply with the letter ONLY.
              Output Format: {
                "events": [
                  {
                    "type": "assistant",
                    "content": "<your reply here>"
                  }
                ]
              }
        edges:
          - from: __START__
            to: agent1
          - from: agent1
            to: agent2
          - from: agent2
            to: __END__
        """
    ).strip()
    path.write_text(cfg, encoding="utf-8")


@pytest.mark.unit
def test_simple_graph(tmp_path: Path) -> None:
    """Builds a simple 2-node linear graph (new schema) and compiles.

    It and outputs the correct letter "I"
    """
    path = tmp_path / "graph-simple.yml"
    _write_simple_yaml(path)

    graph_config = GraphConfig.from_yaml(path)
    logger.debug(f"graph_config: {graph_config}")
    graph = SimulationGraph.compile(graph_config)
    assert isinstance(graph.cgraph, CompiledStateGraph)

    g = graph.cgraph.get_graph()
    node_names = set(g.nodes.keys())
    assert node_names == {"__start__", "agent1", "agent2", "__end__"}


@pytest.mark.slow
def test_invoke_simple(tmp_path: Path) -> None:
    """Invokes the simple graph and verifies the output."""
    logger.warning(
        "NOTE: this makes a live call to a free model on OpenRouter \
                   so its flaky and slow you may have to run it a couple \
                   of times in the OR nodes are overloaded...doesn't mean \
                   something is wrong with the code"
    )

    path = tmp_path / "graph-simple.yml"
    _write_simple_yaml(path)
    graph_config = GraphConfig.from_yaml(path)
    graph = SimulationGraph.compile(graph_config)

    out = graph.cgraph.invoke({"messages": []})
    print("Final output state:", out)
    assert isinstance(out, dict)
    assert "messages" in out and isinstance(out["messages"], list)
    assert all(hasattr(m, "content") for m in out["messages"])
    assert [m.content for m in out["messages"]] == ["H"]


# ---------- Conditional graph ----------


def _write_conditional_yaml(path: Path) -> None:
    """Conditional graph using the new schema. Routing is based on len(messages)."""
    cfg = textwrap.dedent(
        """
        name: conditional-test-graph
        nodes:
          - name: agentA
            kind: custom
            provider: openrouter
            model: openai/gpt-oss-20b:free
            additional_kwargs: {}
            system_template: |
              Reply with '37' ONLY.
              Output Format: {
                "events": [
                  {
                    "type": "assistant",
                    "content": "<your reply here>"
                  }
                ]
              }
          - name: agentB
            kind: custom
            provider: openrouter
            model: openai/gpt-oss-20b:free
            additional_kwargs: {}
            system_template: |
              Reply with '92' ONLY.
              Output Format: {
                "events": [
                  {
                    "type": "assistant",
                    "content": "<your reply here>"
                  }
                ]
              }
        edges:
          - from: __START__
            to:
              conditional:
                - if: "len(messages) == 0"
                  then: agentA
                - else: agentB

          # Keep end routing simple (no custom functions required)
          - from: agentA
            to: __END__
          - from: agentB
            to: __END__
        """
    ).strip()
    path.write_text(cfg, encoding="utf-8")


@pytest.mark.unit
def test_conditional_graph(tmp_path: Path) -> None:
    """Compiles a graph with conditional edges (new schema) and verifies topology."""
    path = tmp_path / "graph-conditional.yml"
    _write_conditional_yaml(path)

    graph_config = GraphConfig.from_yaml(path)
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
    }


@pytest.mark.slow
def test_invoke_conditional(tmp_path: Path) -> None:
    """Invokes the conditional graph through correct branches."""
    path = tmp_path / "graph-conditional.yml"
    _write_conditional_yaml(path)
    graph_config = GraphConfig.from_yaml(path)

    graph = SimulationGraph.compile(graph_config)

    # Branch: len(messages) == 0 -> agentA -> __end__
    assert graph.cgraph is not None
    out_empty = graph.cgraph.invoke({"messages": []})
    assert isinstance(out_empty, dict)
    assert "messages" in out_empty and isinstance(out_empty["messages"], list)
    assert all(hasattr(m, "content") for m in out_empty["messages"])
    # make sure 37 is in the messages
    assert any("37" in m.content for m in out_empty["messages"])

    # Branch: len(messages) > 0 -> agentB -> __end__
    out_nonempty = graph.cgraph.invoke(
        {"messages": [HumanMessage(content="Here is a test message")]}
    )
    assert isinstance(out_nonempty, dict)
    assert "messages" in out_nonempty and isinstance(out_nonempty["messages"], list)
    assert all(hasattr(m, "content") for m in out_nonempty["messages"])
    # make sure 92 is in the messages
    assert any("92" in m.content for m in out_nonempty["messages"])


@pytest.mark.slow
def test_jinja_populates(write_yaml: Callable[[str, str], Path]) -> None:
    """Verifies system_prompt_template with JINJA variables are rendered from state.

    Example: Reply with '{{ pc.name }}' ONLY. -> 'MW'
    """
    logger.warning(
        "This test makes a live call to OpenRouter free model, so may be flaky. "
        "If the test fails, try running it again....doesn't necessarily mean "
        "something is wrong with the code."
    )
    yml = """
    name: jinja-test-graph
    nodes:
      - name: echoChar
        provider: openrouter
        model: openai/gpt-oss-20b:free
        additional_kwargs: {}
        state_permissions:
          read: ["messages", "pc"]
          write: ["messages"]
        system_prompt_template: |
          Reply with '{{ pc.name }}' ONLY.
    edges:
      - from: __start__
        to: echoChar
      - from: echoChar
        to: __end__
    """
    p = write_yaml("graph-jinja.yml", yml)
    graph_config = GraphConfig.from_yaml(p)

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
    # Ensure the rendered value appears in the final messages
    assert any("JANIE" in m.content for m in out["messages"])


# TODO: test jinja population failures are easy to diagnose


@pytest.mark.slow
def test_jinja_works_with_dynamic_input(write_yaml: Callable[[str, str], Path]) -> None:
    """Verifies system_prompt_template with JINJA variables are rendered from state.

    Example: Reply with '{{ pc.name }}' ONLY. -> 'MW'
    """
    logger.warning(
        "This test makes a live call to OpenRouter free model, so may be flaky. "
        "If the test fails, try running it again....doesn't necessarily mean "
        "something is wrong with the code."
    )
    yml = """
    name: jinja-test-graph
    nodes:
      - name: echoChar
        provider: openrouter
        model: openai/gpt-oss-20b:free
        additional_kwargs: {}
        state_permissions:
          read: ["messages", "pc", "extras"]
          write: ["messages"]
        system_prompt_template: |
          Reply with
          {% if extras.conditional_flag %}
          'TRUE' ONLY.
          {% else %}
          'FALSE' ONLY.
          {% endif %}
    edges:
      - from: __start__
        to: echoChar
      - from: echoChar
        to: __end__
    """
    p = write_yaml("graph-jinja.yml", yml)
    graph_config = GraphConfig.from_yaml(p)

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
    # Ensure the rendered value appears in the final messages
    assert any("FALSE" in m.content for m in out["messages"])
    state["extras"]["conditional_flag"] = True
    out = graph.cgraph.invoke(state)
    assert any("TRUE" in m.content for m in out["messages"])
