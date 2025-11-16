"""Simulation subgraph module.

Responsible for validating user input and generating responses that are in character.

Graph Structure:
- Two worker nodes (`validate_input` and `respond`) are executed in parallel
  to reduce latency.
- A `finalize` node aggregates results from both workers and determines the
  final output.

All nodes write their output messages in a uniform structure so that
callers and tooling can consume them consistently:
{
    "type": "info" | "error" | "assistant" | "user",
    "content": str
}

Conventions
-----------
- `validate_input`:
    - On failure:
        - returns a message:
            {
                "type": "error",
                "content": "Validation failed: <reason>"
            }
    - On success:
        - returns a message:
            {
                "type": "info",
                "content": "Validation passed."
            }

- `respond`:
    - Executes in parallel with validation.
    - Assumes the user input *might* be valid (validation may or may not finish first).
    - Returns a message:
        {
            "type": "assistant",
            "content": <roleplayed or simulated character output>
        }

- `finalize`:
    - Is the *only* node that determines the final output returned to the parent graph.
    - Behavior:
        - If the validation message has type `"error"`:
            - the final output is that error message.
        - If validation succeeded (type `"info"`) *and* a response message exists:
            - the final output is the assistant’s response message.
        - If the graph is stopped early (e.g., timeout/cancel) before finalize runs:
            - the wrapper synthesizes an `"error"` message and returns it.

Parent Integration
------------------
The parent `SimulationGraph` class uses this subgraph as a node within its
higher-level simulation graph. It exposes a `.stream(...)` wrapper that enables:

- early stopping when validation fails (even if `respond` is still running)
- timeout-based cancellation
- external cancellation (e.g., a UI cancel button)
- graceful handling of long-running operations (yielding messages)

The wrapper observes `validate_input` events via streaming and can terminate
execution early without waiting for `respond` to finish. If finalize does not
run before termination, the wrapper ensures a well-formed `"error"` message is
returned.
"""

from __future__ import annotations

from typing import Dict, Literal, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


MessageType = Literal["info", "error", "assistant", "user"]


class SimulationMessage(TypedDict):
    type: MessageType
    content: str


class SimulationState(TypedDict, total=False):
    # Input
    user_input: str

    # Per-node messages
    validation_message: SimulationMessage
    response_message: SimulationMessage

    # Final output message (the only thing the parent really cares about)
    final_message: SimulationMessage


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def validate_input(state: SimulationState) -> Dict[str, SimulationMessage]:
    """Validate the user input and return a uniform message payload."""
    text = state.get("user_input", "")

    # Very simple validation rules for now; can be extended later.
    if not text.strip():
        msg: SimulationMessage = {
            "type": "error",
            "content": "Validation failed: Input is empty.",
        }
        return {"validation_message": msg}

    # TODO: question: should we call llm.invoke or llm.stream here?
    if len(text) > 2000:
        msg = {
            "type": "error",
            "content": "Validation failed: Input is too long.",
        }
        return {"validation_message": msg}

    msg = {
        "type": "info",
        "content": "Validation passed.",
    }
    return {"validation_message": msg}


def respond(state: SimulationState) -> Dict[str, SimulationMessage]:
    """Generate an in-character response to the user input.

    This runs in parallel with validation, so it should not assume that
    validation has already completed. The parent / finalize node is
    responsible for deciding whether to use this response.
    """
    text = state.get("user_input", "")

    # Very simple "roleplay" for now; parent can swap this implementation later.
    content = f"In-character reply to: {text!r}"

    msg: SimulationMessage = {
        "type": "assistant",
        "content": content,
    }
    return {"response_message": msg}


def finalize(state: SimulationState) -> Dict[str, SimulationMessage]:
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
    validation_msg: Optional[SimulationMessage] = state.get("validation_message")
    response_msg: Optional[SimulationMessage] = state.get("response_message")

    # No validation message at all: this should not normally happen if the graph
    # is wired correctly, but we guard defensively.
    if validation_msg is None:
        msg: SimulationMessage = {
            "type": "error",
            "content": "Validation did not run or produced no result.",
        }
        return {"final_message": msg}

    if validation_msg["type"] == "error":
        # Prefer the validation error as the final outcome.
        return {"final_message": validation_msg}

    # At this point, validation succeeded (type == "info").
    if response_msg is not None:
        # Use the assistant's response as the final message.
        return {"final_message": response_msg}

    # Validation passed but we have no response yet.
    msg = {
        "type": "error",
        "content": "Validation passed, but no response was generated.",
    }
    return {"final_message": msg}


# ---------------------------------------------------------------------------
# Graph factory
# ---------------------------------------------------------------------------


def build_simulation_subgraph():
    """Build and compile the simulation subgraph.

    Returns a compiled LangGraph app that:
    - takes a SimulationState-like dict as input
    - runs validate_input and respond in parallel
    - merges results via finalize
    """
    builder = StateGraph(SimulationState)

    # Register nodes
    builder.add_node("validate_input", validate_input)
    builder.add_node("respond", respond)
    builder.add_node("finalize", finalize)

    # Fan-out from START to both worker nodes in parallel
    builder.add_edge(START, "validate_input")
    builder.add_edge(START, "respond")

    # Both workers feed into the aggregate node
    builder.add_edge("validate_input", "finalize")
    builder.add_edge("respond", "finalize")

    # Finalize ends the subgraph
    builder.add_edge("finalize", END)

    return builder.compile()


__all__ = [
    "MessageType",
    "SimulationMessage",
    "SimulationState",
    "validate_input",
    "respond",
    "finalize",
    "build_simulation_subgraph",
]
