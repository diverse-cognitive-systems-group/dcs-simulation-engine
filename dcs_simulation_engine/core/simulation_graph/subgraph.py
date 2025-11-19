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

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
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
    UPDATER_MODEL,
    UPDATER_NAME,
    UPDATER_SYSTEM_TEMPLATE,
    VALIDATOR_MODEL,
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


def validate_input(
    state: SimulationGraphState, runtime: Runtime[ContextSchema]
) -> Dict[str, Any]:
    """Validate the user input and return a uniform message payload."""
    logger.debug(f"{VALIDATOR_NAME} IN")
    state_updates: Dict[str, SimulationMessage]
    user_input = state["user_input"]
    user_input_content = user_input.get("content", "") if user_input else ""
    if user_input is None:
        logger.warning(f"{VALIDATOR_NAME} called with no user_input in state")
        state_updates = {
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
        # Check state size for logging purposes
        try:
            n = byte_size_pickle(state)
            if n > LARGE_STATE_WARN_BYTES:
                logger.warning(
                    f"State size large: {n/1024:.1f} KB in node '{VALIDATOR_NAME}'"
                )
        except Exception:
            logger.debug("State size check failed (non-serializable)")

        # ----- Render system prompt safely -----
        msgs_for_model: List[dict[str, str]] = []
        compiled_tmpl = PromptTemplate.from_template(
            VALIDATOR_SYSTEM_TEMPLATE, template_format="jinja2"
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
                f"Node '{VALIDATOR_NAME}' failed to render system_template \
                    with current state: {ex}"
            ) from ex
        msgs_for_model.append({"type": "system", "content": rendered_sys})
        logger.debug(f"Node '{VALIDATOR_NAME}' called with:\n{rendered_sys}")
        # ----- Prompt size check -----
        try:
            m = byte_size_json(msgs_for_model)
            if m > LARGE_PROMPT_WARN_BYTES:
                logger.warning(
                    f"Prompt size large: {m/1024:.1f} KB in node '{VALIDATOR_NAME}'"
                )
        except Exception:
            logger.debug("Prompt size check failed")

        # ----- Call LLM -----
        start = time.perf_counter()
        try:
            context = runtime.context
            llm = context["models"]["subgraph_validator"]
            response = llm.invoke(input=msgs_for_model)
            elapsed = time.perf_counter() - start
            if elapsed > LONG_MODEL_WARN_SECONDS:
                logger.warning(
                    f"Node '{VALIDATOR_NAME}' running LLM ({VALIDATOR_MODEL}) "
                    f"took {elapsed:.3f}s which is quite long."
                )
            else:
                logger.debug(
                    f"Node '{VALIDATOR_NAME}' running LLM ({VALIDATOR_MODEL})"
                    f" took {elapsed:.3f} seconds."
                )
        except Exception as ex:
            # TODO: add finer-grained error handling (rate limit, timeout,
            # permissions, etc) eg. if rate limit, maybe default retries
            # instead of crash the game.
            raise RuntimeError(
                f"Node 'subgraph_validator' LLM invocation failed \
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
                state_updates = {"validator_response": json.loads(match.group(0))}
        except Exception as ex:
            logger.warning(
                f"Node '{VALIDATOR_NAME}' returned non-JSON or unparsable JSON;"
                f" preserving raw text. Error: {ex}",
            )
        # TODO: BEFORE MERGING/PATCHING, MAKE SURE MODEL ONLY
        # RETURNED WHAT INSTRUCTIONS TOLD IT TO IN OUTPUT_FORMAT
        # node functions updates are correctly as instructed in
        # system prompt...ie that it didn't inject or delete required
        # fields from "Output Format: {...}"
    logger.info(f"{VALIDATOR_NAME.upper()} response => {state_updates}")
    logger.debug(f"{VALIDATOR_NAME} OUT")
    return state_updates


def update_world(
    state: SimulationGraphState, runtime: Runtime[ContextSchema]
) -> Dict[str, Any]:
    """Generate an in-character response to the user input.

    This runs in parallel with validation, so it should not assume that
    validation has already completed. The parent / finalize node is
    responsible for deciding whether to use this response.
    """
    logger.debug(f"{UPDATER_NAME} IN")
    state_updates: Dict[str, SimulationMessage]
    user_input = state["user_input"]
    user_input_content = user_input.get("content", "") if user_input else ""
    # Check state size for logging purposes
    try:
        n = byte_size_pickle(state)
        if n > LARGE_STATE_WARN_BYTES:
            logger.warning(
                f"State size large: {n/1024:.1f} KB in node '{VALIDATOR_NAME}'"
            )
    except Exception:
        logger.debug("State size check failed (non-serializable)")

    # ----- Render system prompt safely -----
    msgs_for_model: List[dict[str, str]] = []
    compiled_tmpl = PromptTemplate.from_template(
        UPDATER_SYSTEM_TEMPLATE, template_format="jinja2"
    )
    try:
        rendered_sys = compiled_tmpl.format(
            **{
                **state,
                "user_input_content": user_input_content,
                "pc": runtime.context["pc"],
                "npc": runtime.context["npc"],
            }
        )
    except Exception as ex:
        raise ValueError(
            f"Node '{UPDATER_NAME}' failed to render system_template \
                with current state: {ex}"
        ) from ex
    msgs_for_model.append({"type": "system", "content": rendered_sys})
    logger.debug(f"Node '{UPDATER_NAME}' called with:\n{rendered_sys}")
    # ----- Prompt size check -----
    try:
        m = byte_size_json(msgs_for_model)
        if m > LARGE_PROMPT_WARN_BYTES:
            logger.warning(
                f"Prompt size large: {m/1024:.1f} KB in node '{UPDATER_NAME}'"
            )
    except Exception:
        logger.debug("Prompt size check failed")

    # ----- Call LLM -----
    start = time.perf_counter()
    try:
        context = runtime.context
        llm = context["models"][UPDATER_NAME]
        response = llm.invoke(msgs_for_model)
        elapsed = time.perf_counter() - start
        if elapsed > LONG_MODEL_WARN_SECONDS:
            logger.warning(
                f"Node '{UPDATER_NAME}' running LLM ({UPDATER_MODEL}) "
                f"took {elapsed:.3f}s which is quite long."
            )
        else:
            logger.debug(
                f"Node '{UPDATER_NAME}' running LLM ({UPDATER_MODEL})"
                f" took {elapsed:.3f} seconds."
            )
    except Exception as ex:
        # TODO: add finer-grained error handling (rate limit, timeout,
        # permissions, etc) eg. if rate limit, maybe default retries
        # instead of crash the game.
        raise RuntimeError(
            f"Node '{UPDATER_NAME}' LLM invocation failed \
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
            state_updates = {"updater_response": json.loads(match.group(0))}
    except Exception as ex:
        logger.warning(
            f"Node '{UPDATER_NAME}' returned non-JSON or unparsable JSON;"
            f" preserving raw text. Error: {ex}",
        )
    # TODO: BEFORE MERGING/PATCHING, MAKE SURE MODEL ONLY
    # RETURNED WHAT INSTRUCTIONS TOLD IT TO IN OUTPUT_FORMAT
    # node functions updates are correctly as instructed in
    # system prompt...ie that it didn't inject or delete required
    # fields from "Output Format: {...}"
    logger.info(f"{UPDATER_NAME.upper()} response => {state_updates}")
    logger.debug(f"{UPDATER_NAME} OUT")
    return state_updates


def finalize(state: SimulationGraphState) -> Dict[str, SimulationMessage]:
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
            "finalize: validation passed but no updater_response present in state"
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
    builder.add_node(VALIDATOR_NAME, validate_input)
    builder.add_node(UPDATER_NAME, update_world)
    builder.add_node("finalize", finalize)

    # Fan-out from START to both worker nodes in parallel
    builder.add_edge(START, VALIDATOR_NAME)
    builder.add_edge(START, UPDATER_NAME)

    # Both workers feed into the aggregate node
    builder.add_edge(VALIDATOR_NAME, "finalize")
    builder.add_edge(UPDATER_NAME, "finalize")
    # Finalize ends the subgraph
    builder.add_edge("finalize", END)

    return builder.compile()


def init_subgraph_context() -> Dict[str, Any]:
    """Initialize subgraph context.

    Static things like llm instances, etc.
    """
    models: Dict[str, Any] = {}
    models[VALIDATOR_NAME] = ChatOpenRouter(
        model=VALIDATOR_MODEL,
        timeout=5,  # or httpx.Timeout for more control
        max_retries=2,  # provider level retries
    )
    models[UPDATER_NAME] = ChatOpenRouter(
        model=UPDATER_MODEL,
        timeout=5,  # or httpx.Timeout for more control
        max_retries=2,  # provider level retries
    )
    return models
