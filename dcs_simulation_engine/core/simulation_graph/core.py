"""SimulationGraph module.

Usage:
    sgraph = SimulationGraph.compile(cfg)  # cfg: Optional[GraphConfig]
    print(sgraph.draw_ascii())
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable, Dict, Hashable, Iterator, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from loguru import logger

from dcs_simulation_engine.core.simulation_graph.constants import (
    LARGE_PROMPT_WARN_BYTES,
    LARGE_STATE_WARN_BYTES,
    LONG_MODEL_WARN_SECONDS,
    VALIDATOR_NAME,
)
from dcs_simulation_engine.core.simulation_graph.context import (
    ContextSchema,
    make_context,
)
from dcs_simulation_engine.core.simulation_graph.subgraph import (
    build_simulation_subgraph,
)
from dcs_simulation_engine.utils.misc import byte_size_json, byte_size_pickle

from . import builtins
from .conditions import predicate
from .config import ConditionalItem, ConditionalTo, ElseOnly, GraphConfig, IfThen, Node
from .state import (
    SimulationGraphState,
    display_state_snapshot,
    make_state,
)


class SimulationGraph:
    """Graph wrapper that holds a compiled LangGraph graph.

    Instances do **not** carry GraphConfig or any serde responsibilities.
    Construct via `SimulationGraph.compile(config)` which returns an instance.
    """

    def __init__(self, name: str, cgraph: CompiledStateGraph):
        """Create a SimulationGraph instance.

        Initialized this way a cgraph must be provided (no default).
        The main way to create an instance is via the `compile`
        classmethod which builds and compiles the graph from a config
        but this is useful for some testing scenarios.
        """
        self.name = name
        self.cgraph = cgraph  # runtime-only; not intended for serialization

    @classmethod
    def compile(cls, config: GraphConfig) -> "SimulationGraph":
        """Build and compile the graph from a GraphConfig (or default single-node).

        Returns a new SimulationGraph instance with `cgraph` set.
        """
        logger.info("Compiling simulation graph...")

        # TODO: make sure config contains a __SIMULATION_SUBGRAPH__ node

        builder = StateGraph(
            # defines the shared mutable state that all nodes in the graph can read
            # from or write to.
            state_schema=SimulationGraphState,
            # defines immutable runtime context (like configuration, environment, user
            # info, etc). Available for reference but not meant to change.
            context_schema=ContextSchema,
            # # defines what data can be passed into the graph (entry input)
            # input_schema=SimulationGraphState,
            # # defines what the graph returns when finished (final structured output)
            # output_schema=SimulationGraphState,
        )
        node_fns: Dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

        # compile the simulation subgraph
        simulation_subgraph = build_simulation_subgraph()

        # For each node in the config, create a node agent/function
        temp_state = make_state()
        temp_context = make_context()

        # Register the simulation subgraph as a node in this graph
        SIM_SUBGRAPH_NODE_NAME = "__SIMULATION_SUBGRAPH__"
        builder.add_node(SIM_SUBGRAPH_NODE_NAME, simulation_subgraph)
        for node in config.nodes:
            node_fns[node.name] = cls._make_node_fn(node, temp_state, temp_context)
            builder.add_node(node.name, node_fns[node.name])  # type: ignore

        def _norm(n: str) -> str:
            """Normalize special node names."""
            if n == "__SIMULATION_SUBGRAPH__":
                return SIM_SUBGRAPH_NODE_NAME
            return END if n == "__END__" else (START if n == "__START__" else n)

        for e in config.edges:
            if not e.from_ or not e.to:
                raise ValueError(f"Edge is missing 'from' or 'to': {e}")

            src = _norm(e.from_)
            dest = e.to

            # Plain edge
            if isinstance(dest, str):
                builder.add_edge(src, _norm(dest))
                continue

            # Conditional list: [{if: "...", then: node}, {else: node}]
            if isinstance(dest, ConditionalTo) and dest.conditional:
                clauses = dest.conditional
                if not isinstance(clauses, list) or not clauses:
                    raise ValueError(
                        f"'conditional' must be a non-empty list for "
                        f"edge from {e.from_}"
                    )
                router = cls._build_router_from_clauses(clauses)

                # TODO: update functionality to make lists ifs
                # fan out in parallel and if/elifs wire synchronously

                possible_keys: List[Hashable] = []
                for c in clauses:
                    if isinstance(c, IfThen):
                        possible_keys.append(c.then)
                    elif isinstance(c, ElseOnly):
                        possible_keys.append(c.else_)

                path_map: dict[Hashable, str] = {}
                for key in set(possible_keys):
                    if key == "__END__":
                        path_map["__END__"] = END
                    elif key == "__START__":
                        path_map["__START__"] = START
                    elif key == "__SIMULATION_SUBGRAPH__":
                        path_map["__SIMULATION_SUBGRAPH__"] = SIM_SUBGRAPH_NODE_NAME
                    else:
                        path_map[key] = key  # type: ignore[assignment]

                if "__END__" not in path_map:
                    path_map["__END__"] = END

                builder.add_conditional_edges(src, router, path_map)
                continue

            raise ValueError(f"Unsupported 'to' value for edge from {e.from_}: {dest}")
        # Compile the graph
        cgraph = builder.compile()
        inst = cls(
            name=getattr(config, "name", "sim-graph") or "sim-graph", cgraph=cgraph
        )
        cls._log_graph_debug(cgraph)
        return inst

    def stream(
        self,
        state: SimulationGraphState,
        context: ContextSchema,
        config: RunnableConfig,
        *,
        long_running: Optional[float] = None,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Custom wrapper around cgraph.stream that adds control features.

        Allows early stopping via:
        - validation failure (e.g., a validation_message with type == "error")
        - timeout (seconds)
        - external cancel_event (e.g. UI cancel button)

        Also logs when runs exceed the `long_running` threshold.
        """
        start = time.monotonic()

        # Make a mutable copy of the initial state so we can track the latest view
        # as updates arrive from the graph.
        if isinstance(state, dict):
            current_state: Dict[str, Any] = dict(state)
        else:
            # Fallback: let pydantic / adapter unpack later if needed
            current_state = dict(state)

        if not self.cgraph:
            raise RuntimeError("Cannot call SimulationGraph: no compiled graph.")

        try:
            logger.debug("Ressetting internal subgraph states before running graph...")
            state["simulator_output"] = None
            state["validator_response"] = None
            state["updater_response"] = None
            display_state_snapshot(state)
            logger.debug("Running SimulationGraph...")
            stream = self.cgraph.stream(
                input=state,
                context=context,
                config=config,
                # # Streams the updates to the state after each step of the graph.
                # # If multiple updates are made in the same step (e.g., multiple
                # #  nodes are run), those updates are streamed separately.
                stream_mode="updates",
                # print_mode = "updates",
                # output_keys = None,
                # # Pause streaming run before or after specific nodes
                # interrupt_before = None,
                # # Pause streaming run right before a specific node (or nodes)
                # interrupt_after = None,
                # durability = None,
                # NOTE:
                # We currently rely on subgraphs=True, which means cgraph.stream(...)
                # yields (path, node_updates_dict) tuples.
                # If you ever set subgraphs=False, the shape may change to just
                # node_updates_dict; the normalization below tries to handle both,
                # but this function should be revisited if that config changes.
                subgraphs=True,
                # debug = False
            )
            for raw_update in stream:
                now = time.monotonic()
                # logger.debug(f"SimulationGraph stream got raw update: {raw_update}")

                # Normalize the update shape:
                # - subgraphs=True  -> (path, node_updates_dict)
                # - subgraphs=False -> node_updates_dict (defensive handling)
                if isinstance(raw_update, tuple) and len(raw_update) == 2:
                    path, node_updates = raw_update
                else:
                    path, node_updates = None, raw_update

                if not isinstance(node_updates, dict):
                    logger.error(
                        f"Unexpected update type from cgraph.stream: {raw_update}"
                        f" (path={path})"
                    )
                    continue
                # Process each node update
                for node_name, node_update in node_updates.items():
                    logger.debug(
                        f"SimulationGraph stream update from node '{node_name}':"
                        f" {node_update}",
                    )
                    if isinstance(node_update, dict):
                        # If node_update is a partial state for this node, merge it
                        # into current_state
                        current_state.update(node_update)

                    # External cancel
                    if cancel_event is not None and cancel_event.is_set():
                        logger.info(
                            "SimulationGraph YIELDING cancel and STOPPING.",
                            self.name,
                        )
                        yield {
                            "type": "info",
                            "content": "Simulation cancelled by user.",
                        }
                        return  # stop whole stream

                    # Timeout
                    if timeout is not None and (now - start) > timeout:
                        logger.warning(
                            "SimulationGraph YIELDING timeout error"
                            " and STOPPING (after %.2fs)",
                            now - start,
                        )
                        yield {
                            "type": "error",
                            "content": f"Simulation timed out after "
                            f"{timeout:.1f} seconds.",
                        }
                        return  # stop whole stream

                    # Check events from validation nodes and stop graph run if error
                    validator_response = (
                        node_update.get("validator_response")
                        if isinstance(node_update, dict)
                        else None
                    )
                    is_validator_node = node_name.lower() == VALIDATOR_NAME.lower()
                    is_error = (
                        validator_response and validator_response.get("type") == "error"
                    )
                    if is_validator_node and is_error and validator_response:
                        current_state["validator_response"] = validator_response
                        # descrement user retry budget
                        if "user_retry_budget" not in current_state:
                            logger.error(
                                "Validator node cannot decrement user_retry_budget:"
                                " field missing from state."
                            )
                        else:
                            current_state["user_retry_budget"] -= 1
                        content = validator_response.get("content")
                        logger.info(
                            "SimulationGraph YIELDING validation" " error and STOPPING."
                        )
                        if current_state.get("user_retry_budget", 0) <= 0:
                            content += (
                                " User retry budget exhausted; "
                                "no further retries allowed."
                            )
                            current_state["exit_reason"] = "user retry budget exhausted"
                            current_state["lifecycle"] = "EXIT"
                        yield {
                            "type": "error",
                            "content": content + " Retries left: "
                            f"{current_state.get('user_retry_budget', 0)}",
                        }
                        return  # stop whole stream

                    # Check for any nodes that yield "simulator_output" messages
                    sim_output = (
                        node_update.get("simulator_output")
                        if isinstance(node_update, dict)
                        else None
                    )
                    # we already listen to all the nodes inside the subgraph,
                    # so can skip the whole subgraph output
                    if (
                        sim_output is not None
                        and node_name != "__SIMULATION_SUBGRAPH__"
                    ):
                        logger.debug(
                            f"SimulationGraph YIELDING update"
                            f" from node {node_name}"
                            # f"`type` field: {sim_output}",
                        )
                        yield {
                            "type": sim_output["type"],
                            "content": sim_output["content"],
                        }
                    else:
                        logger.debug(
                            f"SimulationGraph NOT YIELDING update"
                            f" from node {node_name}"
                            # f"`type` field: {node_updates}",
                        )
            # All durring run updates, yeilded above,
            # now we yeild the final output of the turn
            display_state_snapshot(current_state)

            user_input = current_state.get("user_input")
            if user_input is None:
                logger.warning("Final state has no 'user_input' to yield.")

            sim_output = current_state.get("simulator_output")
            if sim_output is None:
                logger.warning("Final state has no 'simulator_output' to yield.")
            # else: we already yielded all simulator_output messages during the run.
        finally:
            duration = time.monotonic() - start
            logger.debug("SimulationGraph run complete.")
            display_state_snapshot(current_state)
            yield {"type": "final_state", "state": current_state}

            if long_running is not None and duration > long_running:
                logger.warning(
                    "SimulationGraph '%s' runtime %.3fs exceeded long_running "
                    "threshold of %.3fs.",
                    self.name,
                    duration,
                    long_running,
                )

    def draw_ascii(self) -> str:
        """ASCII art representation of the compiled graph."""
        if not self.cgraph:
            return "<no graph compiled>"
        return self.cgraph.get_graph().draw_ascii()

    def to_dict(self) -> dict[str, Any]:
        """Tiny, optional serializer for observability/debug (cgraph not serialized)."""
        return {"name": self.name, "has_cgraph": self.cgraph is not None}

    @staticmethod
    def _make_node_fn(
        node: Node, temp_state: SimulationGraphState, temp_context: ContextSchema
    ) -> Callable[[SimulationGraphState], SimulationGraphState]:
        """Create a node runner.

        IMPORTANT!! temp_state is used to validate Jinja templates ONLY.
        ITS NOT USED AT RUNTIME. AT RUNTIME THE ACTUAL STATE IS USED.

        - Validates Jinja templates at build time (not first run).
        - Enforces the presence of an "Output Format: {}" in system_templates.
        - Returns a callable that accepts a full SimulationGraphState and
        returns an updated one.
        """
        # ----- Validate Jinja Fields  -----

        errors = []
        ORDERED_OBJS = [("node", node), ("node.config", getattr(node, "config", None))]

        # FIXME: fix this...doesn't seem to be catching template render errors
        # ...eg if SimulationGraphState doesn't have that field.

        for owner, obj in ORDERED_OBJS:
            if obj is None:
                continue
            for attr in dir(obj):
                if attr.startswith("_"):
                    continue
                try:
                    raw = getattr(obj, attr)
                except Exception:
                    continue
                if not isinstance(raw, str):
                    continue
                # try compile
                try:
                    tmpl = PromptTemplate.from_template(raw, template_format="jinja2")
                except Exception as ex:
                    errors.append(f"{owner}.{attr}: Jinja compile failed: {ex}")
                    continue
                # try render using temp_state
                try:
                    _ = tmpl.format(
                        **{
                            **temp_state,
                            "pc": temp_context["pc"],
                            "npc": temp_context["npc"],
                        }
                    )
                except Exception as ex:
                    errors.append(
                        f"{owner}.{attr}: render failed with temp_state: {ex}"
                    )

        if errors:
            raise ValueError(
                f"Node '{node.name}' has invalid template(s):\n  - "
                + "\n  - ".join(errors)
            )

        # ----- Enforce Output Format presence -----
        pattern = re.compile(
            r"output\s*format\s*:\s*\{.*?\}",
            flags=re.IGNORECASE | re.DOTALL,
        )

        sys_tmpl = node.system_template
        if not sys_tmpl and getattr(node, "config", None):
            sys_tmpl = getattr(node.kwargs, "system_template", None)

        if sys_tmpl and not pattern.search(sys_tmpl):
            raise ValueError(
                f"Node '{node.name}' must include an \"Output Format: {{...}}\" block "
                f"in system_template (on node or node.kwargs).\n"
                f"Template:\n{sys_tmpl!r}"
            )

        def node_fn(
            state: SimulationGraphState, runtime: Runtime[ContextSchema]
        ) -> dict[str, Any]:
            """Execute a single node.

            Each node takes a full SimulationGraphState and returns an updated one.
            """
            logger.debug(f"{node.name} IN")
            state_updates: dict[str, Any] = {}
            try:
                n = byte_size_pickle(state)
                if n > LARGE_STATE_WARN_BYTES:
                    logger.warning(
                        f"State size large: {n/1024:.1f} KB in node '{node.name}'"
                    )
            except Exception:
                logger.debug("State size check failed (non-serializable)")

            # ---- Build Builtin Node Function ----
            if isinstance(node.kind, str) and node.kind.startswith("builtin."):
                fn_name = node.kind.split(".", 1)[1]
                try:
                    builtin_fn = getattr(builtins, fn_name)
                except AttributeError:
                    raise ValueError(f"Unknown builtin node kind: {node.kind}")

                # Builtins take a config dict with all the function signature args
                # and sometimes also the current state
                args = node.kwargs if node.kwargs is not None else {}
                # call building with appropriate args
                logger.debug(
                    f"Calling builtin node function: {node.kind}"
                    f" with arguments keys: {args.keys()}"
                )
                state_updates = builtin_fn(state=state, context=runtime.context, **args)
            else:
                # ----- Build Custom Agent Node Function -----
                if node.additional_kwargs is None:
                    node.additional_kwargs = {}
                if node.provider == "openrouter":
                    llm: BaseChatModel = runtime.context["models"][node.model]
                elif node.provider == "huggingface":
                    raise NotImplementedError(
                        f"Provider not implemented yet: {node.provider}"
                    )
                elif node.provider == "local":
                    raise NotImplementedError(
                        f"Provider not implemented yet: {node.provider}"
                    )
                else:
                    raise NotImplementedError(
                        f"Provider not implemented yet: {node.provider}"
                    )

                # ----- Render system prompt safely -----
                msgs_for_model: List[dict[str, str]] = []
                if node.system_template is None:
                    raise ValueError(
                        f"Node '{node.name}' is missing required system_template."
                    )
                else:
                    compiled_tmpl = PromptTemplate.from_template(
                        node.system_template, template_format="jinja2"
                    )
                    try:
                        rendered_sys = compiled_tmpl.format(
                            **{
                                **state,
                                "pc": runtime.context["pc"],
                                "npc": runtime.context["npc"],
                            }
                        )
                    except Exception as ex:
                        raise ValueError(
                            f"Node '{node.name}' failed to render system_template \
                                with current state: {ex}"
                        ) from ex
                    msgs_for_model.append({"type": "system", "content": rendered_sys})
                    logger.debug(f"Node {node.name} called with:\n{rendered_sys}")

                # ----- Prompt size check -----
                try:
                    m = byte_size_json(msgs_for_model)
                    if m > LARGE_PROMPT_WARN_BYTES:
                        logger.warning(
                            f"Prompt size large: {m/1024:.1f} KB in node '{node.name}'"
                        )
                except Exception:
                    logger.debug("Prompt size check failed")

                # ----- Call LLM -----
                start = time.perf_counter()
                try:
                    response = llm.invoke(msgs_for_model)
                    elapsed = time.perf_counter() - start
                    if elapsed > LONG_MODEL_WARN_SECONDS:
                        logger.warning(
                            f"Node '{node.name}' running LLM ({node.model}) "
                            f"took {elapsed:.3f}s which is quite long."
                        )
                    else:
                        logger.debug(
                            f"Node '{node.name}' running LLM ({node.model})"
                            f" took {elapsed:.3f} seconds."
                        )
                except Exception as ex:
                    # TODO: add finer-grained error handling (rate limit, timeout,
                    # permissions, etc) eg. if rate limit, maybe default retries
                    # instead of crash the game.
                    raise RuntimeError(
                        f"Node '{node.name}' LLM invocation failed \
                            (rate limit/timeout/permissions?): {ex}"
                    ) from ex

                response_text = getattr(response, "content", None)
                if response_text is None:
                    response_text = str(response)

                # ----- Try to extract and merge JSON output -----
                # Heuristic: grab the first top level {...} block (tolerate extra prose)
                try:
                    match = re.search(r"\{.*\}", response_text, flags=re.DOTALL)
                    if match:
                        state_updates = json.loads(match.group(0))
                except Exception as ex:
                    logger.warning(
                        f"Node '{node.name}' returned non-JSON or unparsable JSON;"
                        f" preserving raw text. Error: {ex}",
                    )
                # TODO: BEFORE MERGING/PATCHING, MAKE SURE MODEL ONLY
                # RETURNED WHAT INSTRUCTIONS TOLD IT TO IN OUTPUT_FORMAT
                # node functions updates are correctly as instructed in
                # system prompt...ie that it didn't inject or delete required
                # fields from "Output Format: {...}"

            logger.info(f"{node.name.upper()} response => {state_updates}")
            logger.debug(f"{node.name} OUT")
            return state_updates

        return node_fn

    @classmethod
    def _build_router_from_clauses(
        cls, clauses: List[ConditionalItem]
    ) -> Callable[[SimulationGraphState], str]:
        """Build a router function from conditional clauses."""

        def router(state: SimulationGraphState) -> str:
            for c in clauses:
                if isinstance(c, IfThen):
                    if predicate(c.if_, state):
                        return c.then
                elif isinstance(c, ElseOnly):
                    return c.else_
            return "__end__"

        return router

    @staticmethod
    def _log_graph_debug(compiled: CompiledStateGraph) -> None:
        try:
            g = compiled.get_graph()
            logger.debug("Graph built: {}", g)
            logger.debug("Graph ascii:\n{}", g.draw_ascii())
        except Exception as ex:
            logger.debug("Graph visualization failed: {}", ex)
