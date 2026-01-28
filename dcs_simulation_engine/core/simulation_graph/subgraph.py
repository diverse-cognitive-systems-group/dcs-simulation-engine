"""Simulation subgraph module.

Responsible for validating user input and generating responses that are in character.

Graph Structure:
- Two worker nodes (`validate_input` and `respond`) are executed in parallel
  to reduce latency.
- A `finalize` node aggregates results from both workers and determines the
  final output.

The parent `SimulationGraph` class uses this subgraph as a node within its
higher-level simulation graph. It exposes a `.stream(...)` wrapper that enables:

- early stopping when validation fails (even if `respond` is still running)
- timeout-based cancellation
- external cancellation (e.g., a UI cancel button)
- graceful handling of long-running operations (yielding messages)

The wrapper observes validation response via streaming and can terminate
execution early without waiting for update to finish. If finalize does not
run before termination, the wrapper ensures a well-formed `"error"` message is
returned.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, List, Optional

from jinja2.sandbox import SandboxedEnvironment
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from loguru import logger

from dcs_simulation_engine.core.simulation_graph.constants import (
    FINALIZER_NAME,
    LARGE_PROMPT_WARN_BYTES,
    LARGE_STATE_WARN_BYTES,
    LONG_MODEL_WARN_SECONDS,
    MAX_USER_INPUT_LENGTH,
    UPDATER_NAME,
    UPDATER_SYSTEM_TEMPLATE,
    VALIDATOR_NAME,
    VALIDATOR_SYSTEM_TEMPLATE,
)
from dcs_simulation_engine.core.simulation_graph.context import ContextSchema
from dcs_simulation_engine.core.simulation_graph.state import (
    SimulationGraphState,
    SimulationMessage,
)
from dcs_simulation_engine.utils.chat import ChatOpenRouter
from dcs_simulation_engine.utils.misc import byte_size_json, byte_size_pickle

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Use standard SandboxedEnvironment which allows dict attribute access (e.g., pc.hid)
# unlike LangChain's _RestrictedSandboxedEnvironment which blocks it
_jinja_env = SandboxedEnvironment()


def _warn_if_large_state(state: SimulationGraphState, node_name: str) -> None:
    """Log a warning if the pickled state is large."""
    try:
        n = byte_size_pickle(state)
        if n > LARGE_STATE_WARN_BYTES:
            logger.warning(f"State size large: {n/1024:.1f} KB in node '{node_name}'")
    except Exception:
        logger.debug("State size check failed (non-serializable)")


def _llm_node(
    *,
    node_name: str,
    system_template: str,
    model_key: str,
    state_key: str,
    state: SimulationGraphState,
    runtime: Runtime[ContextSchema],
    extra_template_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Shared LLM pipeline for validator/updater-like nodes.

    Handles:
    - state size logging
    - system prompt rendering (jinja2)
    - prompt size logging
    - LLM invocation + latency logging
    - JSON-block extraction

    Returns a dict of `{state_key: SimulationMessage | dict}` suitable for
    merging into the SimulationGraphState.
    """
    _warn_if_large_state(state, node_name)

    extra_template_kwargs = extra_template_kwargs or {}

    # ----- Render system prompt safely -----
    compiled_tmpl = _jinja_env.from_string(system_template)
    try:
        rendered_sys = compiled_tmpl.render(
            **{
                **state,
                "pc": runtime.context["pc"],
                "npc": runtime.context["npc"],
                "additional_validator_rules": runtime.context[
                    "additional_validator_rules"
                ],
                "additional_updater_rules": runtime.context["additional_updater_rules"],
                **extra_template_kwargs,
            }
        )
    except Exception as ex:
        raise ValueError(
            f"Node '{node_name}' failed to render system_template "
            f"with current state: {ex}"
        ) from ex

    msgs_for_model: List[dict[str, str]] = [{"type": "system", "content": rendered_sys}]
    logger.debug(f"Node '{node_name}' called with:\n{rendered_sys}")

    # ----- Prompt size check -----
    try:
        m = byte_size_json(msgs_for_model)
        if m > LARGE_PROMPT_WARN_BYTES:
            logger.warning(f"Prompt size large: {m/1024:.1f} KB in node '{node_name}'")
    except Exception:
        logger.debug("Prompt size check failed")

    # ----- Call LLM -----
    start = time.perf_counter()
    try:
        llm = runtime.context["models"][model_key]
        # keep the explicit kwarg style to match typical LC usage
        response = llm.invoke(input=msgs_for_model)
        elapsed = time.perf_counter() - start
        if elapsed > LONG_MODEL_WARN_SECONDS:
            logger.warning(
                f"Node '{node_name}' LLM call"
                f"took {elapsed:.3f}s which is quite long."
            )
        else:
            logger.debug(f"Node '{node_name}' LLM call" f" took {elapsed:.3f} seconds.")
    except Exception as ex:
        # TODO: add finer-grained error handling (rate limit, timeout,
        # permissions, etc) eg. if rate limit, maybe default retries
        # instead of crash the game.
        raise RuntimeError(
            f"Node '{node_name}' LLM invocation failed "
            f"(rate limit/timeout/permissions?): {ex}"
        ) from ex

    # ----- Try to extract and merge JSON output -----
    response_text = getattr(response, "content", None)
    if response_text is None:
        response_text = str(response)

    # Heuristic: grab the first top level {...} block (tolerate extra prose)
    try:
        match = re.search(r"\{.*\}", response_text, flags=re.DOTALL)
        if match:
            return {state_key: json.loads(match.group(0))}
    except Exception as ex:
        logger.warning(
            f"Node '{node_name}' returned non-JSON or unparsable JSON; "
            f"preserving raw text. Error: {ex}",
        )

    # Fallback: preserve raw text as an error SimulationMessage
    return {
        state_key: SimulationMessage(
            type="error",
            content=response_text,
        )
    }


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def validator(
    state: SimulationGraphState, runtime: Runtime[ContextSchema]
) -> Dict[str, Any]:
    """Validate the user input and return a uniform message payload."""
    logger.debug(f"{VALIDATOR_NAME} IN")
    user_input = state["user_input"]
    user_input_content = user_input.get("content", "") if user_input else ""

    # Fast paths that don't need the LLM
    if user_input is None:
        state_updates: Dict[str, Any] = {
            "validator_response": SimulationMessage(
                type="info", content="User input is None. Marking validation as passed."
            ),
        }
    elif not user_input_content.strip():
        state_updates = {
            "validator_response": SimulationMessage(
                type="info",
                content=(
                    "User input is empty. "
                    "No validation needed. Marking validation as passed."
                ),
            )
        }
    elif len(user_input_content) > MAX_USER_INPUT_LENGTH:
        state_updates = {
            "validator_response": SimulationMessage(
                type="error",
                content=(
                    f"User input exceeds maximum length of "
                    f"{MAX_USER_INPUT_LENGTH} characters."
                ),
            )
        }
    else:
        # Shared LLM pipeline
        state_updates = _llm_node(
            node_name=VALIDATOR_NAME,
            system_template=VALIDATOR_SYSTEM_TEMPLATE,
            model_key=VALIDATOR_NAME,  # models[VALIDATOR_NAME] in context
            state_key="validator_response",
            state=state,
            runtime=runtime,
            extra_template_kwargs={},
        )

    logger.info(f"{VALIDATOR_NAME.upper()} response => {state_updates}")
    logger.debug(f"{VALIDATOR_NAME} OUT")
    return state_updates


def updater(
    state: SimulationGraphState, runtime: Runtime[ContextSchema]
) -> Dict[str, Any]:
    """Generate an in-character response to the user input.

    This runs in parallel with validation, so it should not assume that
    validation has already completed. The parent / finalize node is
    responsible for deciding whether to use this response.
    """
    logger.debug(f"{UPDATER_NAME} IN")
    user_input = state["user_input"]
    user_input_content = user_input.get("content", "") if user_input else ""

    state_updates = _llm_node(
        node_name=UPDATER_NAME,
        system_template=UPDATER_SYSTEM_TEMPLATE,
        model_key=UPDATER_NAME,  # models[UPDATER_NAME] in context
        state_key="updater_response",
        state=state,
        runtime=runtime,
        extra_template_kwargs={"user_input_content": user_input_content},
    )

    logger.info(f"{UPDATER_NAME.upper()} response => {state_updates}")
    logger.debug(f"{UPDATER_NAME} OUT")
    return state_updates


def finalizer(state: SimulationGraphState) -> Dict[str, SimulationMessage]:
    """Aggregate validation and response messages to produce a final message.

    Rules:
    - If validation_message.type == "error":
        -> final_message is that error.
    - Else, if validation_message.type == "info" and response_message exists:
        -> final_message is the assistant's response.
    - Else:
        -> final_message is a generic error indicating incomplete state.
           (In practice, the parent wrapper may stop early and synthesize its
           own error; this is just a safety net.)
    """
    logger.debug(f"{FINALIZER_NAME} IN")
    state_updates: Dict[str, Any] = {}
    validator_response: Optional[SimulationMessage] = state.get("validator_response")
    updater_response: Optional[SimulationMessage] = state.get("updater_response")
    user_message = state["user_input"]

    # No validation message at all: this should not normally happen if the graph
    # is wired correctly, but we guard defensively.
    if validator_response is None:
        state_updates = {
            "simulator_output": SimulationMessage(
                type="error", content="Validation did not run or produced no result."
            )
        }
    elif validator_response["type"] == "error":
        # Prefer the validation error as the final outcome.
        state_updates = {"final_response": validator_response}
    # At this point, validation succeeded (type == "info").
    elif updater_response is not None:
        # Use the ai's response as the final message.
        history_updates: list[BaseMessage] = []
        if user_message is not None:
            history_updates.append(HumanMessage(content=user_message["content"]))
        history_updates.append(AIMessage(content=updater_response["content"]))
        state_updates = {
            "simulator_output": updater_response,
            "history": history_updates,
        }
    else:
        # Validation passed but we have no response yet.
        logger.warning(
            "finalizer: validation passed but no updater_response present in state"
        )
        state_updates = {
            "simulator_output": SimulationMessage(
                type="error",
                content="Validation passed, but no response was generated.",
            )
        }
    logger.info(f"{FINALIZER_NAME.upper()} response => {state_updates}")
    logger.debug(f"{FINALIZER_NAME} OUT")
    return state_updates


def build_simulation_subgraph() -> CompiledStateGraph:
    """Build and compile the simulation subgraph.

    Can be used as a node in the parent SimulationGraph
    we use the same SimulationGraphState type.
    parent = StateGraph(State)
    parent.add_node("p", parent_step)
    parent.add_node("sg", subgraph)
    parent.add_edge(START, "p")
    parent.add_edge("p", "sg")
    parent_graph = parent.compile()

    Returns a compiled LangGraph app that:
    - takes a SimulationGraphState-like dict as input
    - runs validate_input and respond in parallel
    - merges results via finalize

    """
    builder = StateGraph(SimulationGraphState)

    # Register nodes
    builder.add_node(VALIDATOR_NAME, validator)
    builder.add_node(UPDATER_NAME, updater)
    builder.add_node(FINALIZER_NAME, finalizer)

    # Fan-out from START to both worker nodes in parallel
    builder.add_edge(START, VALIDATOR_NAME)
    builder.add_edge(START, UPDATER_NAME)

    # Both workers feed into the aggregate node
    builder.add_edge(VALIDATOR_NAME, FINALIZER_NAME)
    builder.add_edge(UPDATER_NAME, FINALIZER_NAME)
    # Finalize ends the subgraph
    builder.add_edge(FINALIZER_NAME, END)

    return builder.compile()


def init_subgraph_context() -> Dict[str, Any]:
    """Initialize subgraph context.

    Static things like llm instances, etc.
    """
    models: Dict[str, Any] = {}
    models[VALIDATOR_NAME] = ChatOpenRouter(
        model="openai/gpt-5-mini",
        timeout=5,  # or httpx.Timeout for more control
        max_retries=2,  # provider level retries
    )
    models[UPDATER_NAME] = ChatOpenRouter(
        model="openai/gpt-5-mini",
        timeout=5,  # or httpx.Timeout for more control
        max_retries=2,  # provider level retries
    )
    return models
