"""Demo LangGraph with parallel validation + reply and a single finalizer node.

Flow:
    START
      ├── validate_input
      └── draft_reply
    validate_input ─┐
    draft_reply ────┼─> finalize -> END

- validate_input: checks input, sets is_valid / error.
- draft_reply: creates reply text.
- finalize: decides final_output based on is_valid + reply.
"""

import time
from typing import Optional, TypedDict

from langgraph.graph import END, START, StateGraph

# 1. Graph state -----------------------------------------------------------


class AppState(TypedDict, total=False):
    user_input: str
    is_valid: bool
    error: Optional[str]
    reply: Optional[str]
    final_output: str


def ts() -> str:
    """Current time as HH:MM:SS for logging."""
    return time.strftime("%H:%M:%S")


# 2. Nodes -----------------------------------------------------------------


def validate_input(state: AppState) -> AppState:
    print(f"[{ts()}] [NODE] validate_input (input={state['user_input']!r})")
    text = state["user_input"]
    time.sleep(1)  # Simulate processing delay

    if not text.strip():
        error = "Input is empty. Please provide some text."
        print(f"[{ts()}] [NODE] validate_input -> INVALID: {error}")
        return {"is_valid": False, "error": error}

    if len(text) > 200:
        error = "Input is too long (max 200 chars)."
        print(f"[{ts()}] [NODE] validate_input -> INVALID: {error}")
        return {"is_valid": False, "error": error}

    print(f"[{ts()}] [NODE] validate_input -> VALID")
    return {"is_valid": True}


def draft_reply(state: AppState) -> AppState:
    print(f"[{ts()}] [NODE] draft_reply (current keys={list(state.keys())})")
    time.sleep(3)  # Simulate processing delay
    text = state["user_input"]
    reply = f"Thanks for your message: {text!r}"

    print(f"[{ts()}] [NODE] draft_reply -> reply={reply!r}")
    return {"reply": reply}


def finalize(state: AppState) -> AppState:
    """Single finalizer: decides final_output once, based on validation + reply."""
    print(f"[{ts()}] [NODE] finalize (keys={list(state.keys())})")

    # If we've already finalized, don't touch it again.
    if "final_output" in state:
        print(f"[{ts()}] [NODE] finalize -> SKIP (final_output already set)")
        return {}

    # Need validation result first.
    if "is_valid" not in state:
        print(f"[{ts()}] [NODE] finalize -> WAITING (no validation yet)")
        return {}

    # If invalid, finalize with error immediately.
    if state.get("is_valid") is False:
        msg = f"Validation failed: {state.get('error', 'Unknown error')}"
        print(f"[{ts()}] [NODE] finalize -> FINAL (invalid) -> {msg!r}")
        return {"final_output": msg}

    # Valid, but reply might not be ready yet.
    if "reply" not in state:
        print(f"[{ts()}] [NODE] finalize -> WAITING (no reply yet)")
        return {}

    # Valid and reply present -> finalize with reply.
    reply = state["reply"]
    print(f"[{ts()}] [NODE] finalize -> FINAL (valid) -> {reply!r}")
    return {"final_output": reply}


# 3. Build graph -----------------------------------------------------------


def build_graph():
    builder = StateGraph(AppState)

    builder.add_node("validate_input", validate_input)
    builder.add_node("draft_reply", draft_reply)
    builder.add_node("finalize", finalize)

    # Fan out from START
    builder.add_edge(START, "validate_input")
    builder.add_edge(START, "draft_reply")

    # Both branches feed the finalizer
    builder.add_edge("validate_input", "finalize")
    builder.add_edge("draft_reply", "finalize")

    # Finalizer ends the graph
    builder.add_edge("finalize", END)

    return builder.compile()


# 4. Small CLI demo --------------------------------------------------------

if __name__ == "__main__":
    app = build_graph()

    graph = app.get_graph()
    print("=== GRAPH TOPOLOGY ===")
    print(graph.draw_ascii())

    print("\n=== VALID INPUT EXAMPLE ===")
    start = time.time()
    result = app.invoke({"user_input": "Hello, LangGraph!"})
    end = time.time()
    print("Final output:", result["final_output"])
    print(f"Total runtime: {end - start:.6f} seconds")

    print("\n=== INVALID INPUT EXAMPLE (empty) ===")
    start = time.time()
    result = app.invoke({"user_input": "   "})
    end = time.time()
    print("Final output:", result["final_output"])
    print(f"Total runtime: {end - start:.6f} seconds")
