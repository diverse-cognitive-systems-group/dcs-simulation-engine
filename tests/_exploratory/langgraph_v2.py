# flake8: noqa
# type: ignore
"""LangGraph demo with:
- Parallel validate_input + draft_reply
- finalize node
- External control via stream():
    - Early stop on invalid input
    - Timeout stop
    - External cancel event (e.g. a UI cancel button)
"""

import threading
import time
from typing import Any, Dict, Optional, TypedDict

from langgraph.graph import END, START, StateGraph

# 1. Graph state -----------------------------------------------------------


class AppState(TypedDict, total=False):
    user_input: str
    is_valid: bool
    error: Optional[str]
    reply: Optional[str]
    final_output: str


def ts() -> str:
    """Simple timestamp for logging."""
    return time.strftime("%H:%M:%S")


# 2. Nodes -----------------------------------------------------------------


def validate_input(state: AppState) -> AppState:
    print(f"[{ts()}] [NODE] validate_input (input={state['user_input']!r})")
    # Simulate some work
    time.sleep(1.0)

    text = state["user_input"]

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
    print(f"[{ts()}] [NODE] draft_reply (keys={list(state.keys())})")
    # Simulate slower work
    time.sleep(4.0)

    text = state["user_input"]
    reply = f"Thanks for your message: {text!r}"
    print(f"[{ts()}] [NODE] draft_reply -> reply={reply!r}")
    return {"reply": reply}


def finalize(state: AppState) -> AppState:
    print(f"[{ts()}] [NODE] finalize (keys={list(state.keys())})")

    # If invalid, finalize with error
    if state.get("is_valid") is False:
        msg = f"Validation failed: {state.get('error', 'Unknown error')}"
        print(f"[{ts()}] [NODE] finalize -> FINAL (invalid) -> {msg!r}")
        return {"final_output": msg}

    # If still no validation, wait (in a real graph, this might get called again)
    if "is_valid" not in state:
        print(f"[{ts()}] [NODE] finalize -> WAITING (no validation yet)")
        return {}

    # Valid, ensure we have a reply
    if "reply" not in state:
        print(f"[{ts()}] [NODE] finalize -> WAITING (no reply yet)")
        return {}

    reply = state["reply"]
    print(f"[{ts()}] [NODE] finalize -> FINAL (valid) -> {reply!r}")
    return {"final_output": reply}


# 3. Build graph -----------------------------------------------------------


def build_graph():
    builder = StateGraph(AppState)

    builder.add_node("validate_input", validate_input)
    builder.add_node("draft_reply", draft_reply)
    builder.add_node("finalize", finalize)

    # Fan out from START to validation and reply in parallel
    builder.add_edge(START, "validate_input")
    builder.add_edge(START, "draft_reply")

    # Both feed into finalize
    builder.add_edge("validate_input", "finalize")
    builder.add_edge("draft_reply", "finalize")

    builder.add_edge("finalize", END)

    return builder.compile()


# 4. Wrapper around stream() with external control ------------------------


def run_with_control(
    app,
    user_input: str,
    timeout: Optional[float] = None,
    cancel_event: Optional[threading.Event] = None,
) -> Dict[str, Any]:
    """Run the graph using stream() and allow early stopping via:
    - validation failure (is_valid == False)
    - timeout (seconds)
    - external cancel_event (e.g. UI cancel button)
    """
    print(f"\n[{ts()}] [CONTROL] Starting run_with_control(user_input={user_input!r})")
    start = time.monotonic()

    # We'll maintain our own view of state as events come in
    state: Dict[str, Any] = {"user_input": user_input}

    stream = app.stream({"user_input": user_input})

    for event in stream:
        now = time.monotonic()
        print(f"[{ts()}] [STREAM] event = {event}")

        # Merge updates into our local state view
        for node_name, node_update in event.items():
            if isinstance(node_update, dict):
                state.update(node_update)

        # 1) Early stop if validation says input is invalid
        if state.get("is_valid") is False:
            print(
                f"[{ts()}] [CONTROL] Detected invalid input -> stopping stream early."
            )
            break

        # 2) Stop if final_output is ready (normal completion)
        if "final_output" in state:
            print(f"[{ts()}] [CONTROL] final_output is ready -> stopping stream.")
            break

        # 3) Timeout check
        if timeout is not None and (now - start) > timeout:
            print(f"[{ts()}] [CONTROL] Timeout {timeout}s exceeded -> stopping stream.")
            break

        # 4) External cancel event (e.g. UI cancel button)
        if cancel_event is not None and cancel_event.is_set():
            print(f"[{ts()}] [CONTROL] Cancel event set -> stopping stream.")
            break

    else:
        # Only hit if the loop exhausted naturally (no break)
        print(f"[{ts()}] [CONTROL] Stream completed naturally.")

    duration = time.monotonic() - start
    print(f"[{ts()}] [CONTROL] Observed runtime: {duration:.3f}s")

    # If we stopped early on invalid input and finalize hasn't run yet,
    # synthesize a final_output so callers always get something.
    if state.get("is_valid") is False and "final_output" not in state:
        error = state.get("error", "Unknown error")
        state["final_output"] = f"Validation failed: {error}"

    return state


# 5. Small CLI demo --------------------------------------------------------

if __name__ == "__main__":
    app = build_graph()

    graph = app.get_graph()
    print("=== GRAPH TOPOLOGY ===")
    print(graph.draw_ascii())

    # A) Valid input: will take ~max(1s, 3s) unless timeout cancels earlier
    print("\n=== VALID INPUT EXAMPLE (no timeout) ===")
    result = run_with_control(app, "Hello, LangGraph!", timeout=10.0)
    print("Final output:", result.get("final_output"))

    # B) Invalid input: we expect early stop as soon as validation returns
    print("\n=== INVALID INPUT EXAMPLE (early stop on validation) ===")
    result = run_with_control(app, "   ", timeout=10.0)
    print("Final output:", result.get("final_output"))

    # C) Long-running reply cancelled via timeout (simulate user giving up)
    print("\n=== VALID INPUT EXAMPLE (short timeout) ===")
    result = run_with_control(app, "Hello, but don't wait forever", timeout=2.0)
    print("Final output:", result.get("final_output"))

    # D) Simulated external cancel button (thread sets event after 2s)
    print("\n=== VALID INPUT EXAMPLE (external cancel event) ===")
    cancel_btn = threading.Event()

    def cancel_after_delay():
        time.sleep(2.0)
        print(f"[{ts()}] [CANCEL THREAD] Setting cancel event.")
        cancel_btn.set()

    t = threading.Thread(target=cancel_after_delay, daemon=True)
    t.start()

    result = run_with_control(
        app, "Hello with external cancel", timeout=10.0, cancel_event=cancel_btn
    )
    print("Final output:", result.get("final_output"))
