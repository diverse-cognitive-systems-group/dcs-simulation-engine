"""SimulationGraph module.

Usage:
    sgraph = SimulationGraph.compile(cfg)  # cfg: Optional[GraphConfig]
    print(sgraph.draw_ascii())
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Callable, Dict, Hashable, List

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from loguru import logger
from pydantic import ValidationError

from dcs_simulation_engine.core.simulation_graph.context import (
    ContextSchema,
    make_context,
)
from dcs_simulation_engine.utils.misc import byte_size_json, byte_size_pickle

from . import builtins
from .conditions import predicate
from .config import ConditionalItem, ConditionalTo, ElseOnly, GraphConfig, IfThen, Node
from .state import (
    StateAdapter,
    StateSchema,
    make_state,
)

# tune as needed to log runtime warnings for large states/prompts/long runs
LARGE_STATE_WARN_BYTES = 100_000
LARGE_PROMPT_WARN_BYTES = 50_000
LONG_INVOKE_WARN_SECONDS = 25.0
LONG_MODEL_WARN_SECONDS = 15.0


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

    def stream(
        self,
        user_input: str,
        long_running,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
    ):
        """Custom wrapper around cgraph.stream that adds control features.

        Allow early stopping via:
        - validation failure (is_valid == False)
        - timeout (seconds)
        - external cancel_event (e.g. UI cancel button)
        - (and warns if long_running is True)
        """
        # TODO: write me & add typedefs
        pass

    def invoke(
        self,
        state: StateSchema,
        context: ContextSchema,
        config: RunnableConfig,
    ) -> StateSchema:
        """Custom wrapper around cgraph.invoke.

        All simulation graphs use the same StateSchema input/output shape.
        All take new inputs as message_draft and return updated StateSchema.

        - Validates input and output types.
        - Helps enforce custom simulation invocation semantics.
        """
        if not self.cgraph:
            raise RuntimeError("Cannot invoke SimulationGraph: no compiled graph.")

        try:
            # TODO: consider there a langgraph safe way to set max runtime for the whole
            #  graph run? and exit if exceeded? As a failsafe against runaway costs.
            start = time.perf_counter()

            # Before running, reset fields that should not persist between invocations
            logger.debug("Resetting fields before invoking graph: special_user_message")
            state["special_user_message"] = None

            logger.debug("Invoking SimulationGraph...")
            logger.debug("Input keys: {}", state.keys())
            # if invoke required internal retries, warn
            system_retries_pre_invoke = state["retries"]["ai"]
            new_state = self.cgraph.invoke(input=state, context=context, config=config)
            elapsed = time.perf_counter() - start
            if new_state["retries"]["ai"] > system_retries_pre_invoke:
                logger.warning(
                    """SimulationGraph.invoke required system retries during execution. 
                    This may indicate that internal nodes could use prompt improvements 
                    to reduce errors and improve clarity. Internal retries slow down 
                    execution significantly and increase costs."""
                )
            # TODO: Reset retries??

            if elapsed > LONG_INVOKE_WARN_SECONDS:
                logger.warning(
                    f"SimulationGraph.invoke took {elapsed:.3f}s which is quite long."
                )
            else:
                logger.debug(f"SimulationGraph.invoke took {elapsed:.3f}s")

        except Exception as e:
            logger.error(f"Error occurred while invoking SimulationGraph: {e}")
            raise

        # After running, clear message_draft and invalid_reason, used internally only
        logger.debug(
            "Resetting fields before returning result: message_draft, invalid_reason"
        )
        new_state["message_draft"] = None
        new_state["invalid_reason"] = None

        # Validate output state
        try:
            new_state = StateAdapter.validate_python(new_state)
        except ValidationError as e:
            logger.error(
                f"Invalid output StateSchema from SimulationGraph: {new_state}\n"
                f"Error: {e}"
            )
            raise

        return new_state

    def draw_ascii(self) -> str:
        """ASCII art representation of the compiled graph."""
        if not self.cgraph:
            return "<no graph compiled>"
        return self.cgraph.get_graph().draw_ascii()

    def to_dict(self) -> dict[str, Any]:
        """Tiny, optional serializer for observability/debug (cgraph not serialized)."""
        return {"name": self.name, "has_cgraph": self.cgraph is not None}

    # ----- Build / compile -----
    @classmethod
    def compile(cls, config: GraphConfig) -> "SimulationGraph":
        """Build and compile the graph from a GraphConfig (or default single-node).

        Returns a new SimulationGraph instance with `cgraph` set.
        """
        logger.info("Compiling simulation graph...")

        # TODO: make sure any user configured nodes (parent graph) include subgraph call somewhere. start, end and subgraph are all required.

        builder = StateGraph(
            # defines the shared mutable state that all nodes in the graph can read
            # from or write to.
            state_schema=StateSchema,
            # defines immutable runtime context (like configuration, environment, user
            # info, etc). Available for reference but not meant to change.
            context_schema=ContextSchema,
            # # defines what data can be passed into the graph (entry input)
            # input_schema=StateSchema,
            # # defines what the graph returns when finished (final structured output)
            # output_schema=StateSchema,
        )
        node_fns: Dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

        # For each node in the config, create a node agent/function
        temp_state = make_state()
        temp_context = make_context()
        for node in config.nodes:
            node_fns[node.name] = cls._make_node_fn(node, temp_state, temp_context)
            builder.add_node(node.name, node_fns[node.name])  # type: ignore

        def _norm(n: str) -> str:
            """Normalize special node names."""
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

    @staticmethod
    def _make_node_fn(
        node: Node, temp_state: StateSchema, temp_context: ContextSchema
    ) -> Callable[[StateSchema], StateSchema]:
        """Create a node runner.

        IMPORTANT!! temp_state is used to validate Jinja templates ONLY.
        ITS NOT USED AT RUNTIME. AT RUNTIME THE ACTUAL STATE IS USED.

        - Validates Jinja templates at build time (not first run).
        - Enforces the presence of an "Output Format: {}" in system_templates.
        - Returns a callable that accepts a full StateSchema and returns an updated one.
        """
        # ----- Validate Jinja Fields  -----

        errors = []
        ORDERED_OBJS = [("node", node), ("node.config", getattr(node, "config", None))]

        # FIXME: fix this...doesn't seem to be catching template render errors
        # ...eg if StateSchema doesn't have that field.

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
            state: StateSchema, runtime: Runtime[ContextSchema]
        ) -> dict[str, Any]:
            """Execute a single node.

            Each node takes a full StateSchema and returns an updated one.
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
    ) -> Callable[[StateSchema], str]:
        """Build a router function from conditional clauses."""

        def router(state: StateSchema) -> str:
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
