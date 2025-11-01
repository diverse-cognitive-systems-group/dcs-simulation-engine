"""Web handlers for Gradio interface to the DCS Simulation Engine.

Send → enqueue → sim.play consumes → timer polls state → new messages appear.

"""

from __future__ import annotations

from queue import Queue
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Tuple

import gradio as gr
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

from dcs_simulation_engine.core.run_manager import SimulationManager
from dcs_simulation_engine.widget.state import AppState

Message = Dict[str, str]


def _make_input_provider(state: AppState) -> Callable[[], str]:
    """Create a blocking input provider that feeds user messages from a Queue.

    The returned callable mirrors your CLI `input_provider`: it blocks until a
    user message is available, then returns that message to `SimulationManager.play()`.

    Args:
        state: App state containing the active simulation and the message queue.

    Returns:
        Callable that takes no arguments and returns the next user message.

    Raises:
        ValueError: If the simulation state was not initialized properly.
    """
    q: Queue[str] = state["queue"]
    sim: SimulationManager = state["sim"]

    def input_provider() -> str:
        """A blocking input provider for the simulation's play loop.

        It just reads from the queue.
        """
        if sim.state is None:
            raise ValueError("Simulation state was not initialized properly.")
        msgs = sim.state.get("messages", [])
        logger.debug(f"input_provider sees {len(msgs)} messages: {msgs}")
        return q.get()

    return input_provider


def _ensure_play_running(state: AppState) -> None:
    """Start the simulation's play loop in a background daemon thread if needed.

    Spawns a single thread that calls `sim.play(input_provider=...)`. The play loop
    will block on the input provider until `on_send` pushes messages into the queue.

    Args:
        state: App state. Must contain "sim" and "queue". On success, adds
            "_play_thread" to the state if it didn't exist or had stopped.
    """
    existing: Optional[Thread] = state.get("_play_thread")
    if existing and existing.is_alive():
        return

    sim: SimulationManager = state["sim"]
    ip = _make_input_provider(state)

    thread = Thread(target=lambda: sim.play(input_provider=ip), daemon=True)
    thread.start()
    state["_play_thread"] = thread


# ---------- Gradio Handlers ----------


def on_load(state: Dict[str, Any]) -> Tuple[str, str, AppState, List[Message]]:
    """Load the uploaded YAML and return setup, instructions, opening + state."""
    # Prepare/normalize app state
    app_state: AppState = AppState(**state) if isinstance(state, dict) else AppState()
    logger.debug(f"on_load called with state: {app_state}")

    if app_state.get("mode") == "demo":
        sim: SimulationManager = SimulationManager.create(
            mode="demo", user_type="human-norm", character_type="human-nonverbal"
        )
    else:
        raise NotImplementedError("Only demo mode is supported in this version.")

    app_state["sim"] = sim
    app_state["queue"] = Queue()
    app_state["last_seen"] = 0

    opening_scene: str = ""
    try:
        sim.graph.compile()
        sim.step()
        # Seed the chatbot with the opening AI message/scene
        initial_history: List[Message] = (
            [{"role": "assistant", "content": opening_scene}] if opening_scene else []
        )
        # move the cursor past all current messages so first send won’t re-read them
        app_state["last_seen"] = len(sim.state.get("messages", []))
        if not sim.state:
            raise ValueError("No state was generated after stepping the simulation.")
        opening_scene = sim.state.get("opening_scene", "")
        if not sim.state.get("opening_scene"):
            raise ValueError(
                f"No messages were generated for the opening \
                    scene: {sim.state.get('messages', [])}"
            )
    except Exception:
        logger.error("Failed to initialize simulation state in on_load.", exc_info=True)
        raise

    # Safely pull character/graph info similar to your CLI code
    try:
        user_obj = sim.characters[0] if getattr(sim, "characters", None) else None
        user_short = getattr(user_obj, "short_description", "") if user_obj else ""
        user_abilities = (
            getattr(user_obj, "abilities", "Unknown") if user_obj else "Unknown"
        )
    except Exception:
        user_short, user_abilities = "", ""
        logger.error("Failed to extract character/graph info.", exc_info=True)
        raise

    # Instructions (like CLI show_instructions)
    instructions_md: str = (
        f"""
## Instructions

You are: {user_short}

**Your task** is to interact with **UCS** (another cognitive agent) using any combination of your abilities to figure out how to communicate with **UCS** and discover what he/she/it cares about, what he/she/it's goals are, intentions, etc.

You may choose any interaction method available to you. For example:

    - If you have the ability to speak English or normal human motor abilities, try:  
    `softly say "hello"` or `wave my left hand in greeting`.
    - If you can use touch and have limbs, try:  
    `tap on UCS's shoulder`.

Observe **UCS**’s response, adapt your approach, and gradually learn how to communicate effectively and uncover what **UCS** cares about.
""".strip()
    )  # noqa: E501

    # opening_md: str = f"## Opening Scene\n\n{opening_scene}"
    opening_md: str = ""

    # Kick off the play loop once; it will block on input_provider until user sends
    _ensure_play_running(app_state)

    return instructions_md, opening_md, app_state, initial_history


def poll_fn(
    chat: List[Message], state: Dict[str, Any]
) -> Tuple[List[Message], Dict[str, Any]]:
    """Poll for new messages from the simulation engine to update the chat history."""
    sim: Optional[SimulationManager] = state.get("sim")
    if sim is None or sim.state is None or "last_seen" not in state:
        return chat, state, gr.update()
    if sim.stopped:
        # don't poll for new messages if the sim is stopped
        # TODO - display results from sim run data
        return (
            chat
            + [
                {
                    "role": "assistant",
                    "content": "The simulation has ended.",
                }
            ],
            state,
            gr.update(active=False, interactive=False),
        )
    msgs = sim.state.get("messages", [])
    # logger.debug(f"poll_fn sees {len(msgs)} messages, last_seen={state['last_seen']}")
    for m in msgs[state.get("last_seen") :]:
        logger.debug(f"poll_fn appending message: {m} to chat: {chat}")
        if isinstance(m, AIMessage):
            role = "assistant"
        elif isinstance(m, HumanMessage):
            role = "user"
        else:
            role = "assistant"  # fallback

        chat.append({"role": role, "content": m.content})

    state["last_seen"] = len(msgs)
    return chat, state, gr.update()  # keep ticking


def on_send(
    msg: str, chat: List[Message], state: Dict[str, Any]
) -> Tuple[List[Message], str]:
    """Handle a user message: enqueue it and return the latest engine reply.

    Behavior mirrors the CLI:
    1) Puts the user message into the queue consumed by the input provider.
    2) Waits for the engine to append a new message to `sim.state["messages"]`.
    3) Appends the (user, assistant) pair to the Gradio Chatbot history.

    Args:
        msg: The user's input text from the textbox.
        chat: Current Chatbot history.
        state: gr.State dictionary containing the active simulation and queue.

    Returns:
        Tuple[List[Message], str]: Updated Chatbot history and an empty string
        to clear the input textbox.

    Notes:
        Includes a safety timeout (120s) to avoid indefinite waiting.
    """
    app_state: AppState = AppState(**state) if isinstance(state, dict) else AppState()
    sim: Optional[SimulationManager] = app_state.get("sim")
    if not sim:
        # TODO: fix - this isn't displayed anywhere...
        return ([{"role": "assistant", "content": "Load a simulation first."}], "")

    if sim.stopped:
        # don't accept new messages if the sim is stopped
        return (
            chat
            + [
                {
                    "role": "assistant",
                    "content": "The simulation has ended.",
                }
            ],
            "",
        )

    # Ensure the play loop is alive (idempotent)
    _ensure_play_running(app_state)

    # Enqueue user message for the input provider
    if "queue" not in app_state:
        raise ValueError("App state is missing the message queue.")
    logger.debug(f"on_send enqueuing message: {msg}")
    app_state["queue"].put(msg)

    return chat, ""


def display_results():
    """Display the results of the simulation run."""
    # TODO - implement displaying results from sim run data
    pass
