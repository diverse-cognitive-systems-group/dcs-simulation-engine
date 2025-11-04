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

from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.widget.state import AppState
from dcs_simulation_engine.widget.ui.landing import LandingUI
from dcs_simulation_engine.widget.ui.consent import ConsentUI

# Messages are "events" in the simulator
Event = Dict[str, str]

def _format_special(msg: dict[str, str]) -> str:
    """Format a special user message from the simulation engine for nice gradio display."""
    t = (msg.get("type") or "info").lower()
    c = msg.get("content") or ""
    if t == "warning":
        return f"⚠️ {c}"
    if t == "error":
        return f"❌ {c}"
    return f"----\n{c}\n----"

def _make_input_provider(state: AppState) -> Callable[[], str]:
    """Create a blocking input provider that feeds user messages from a Queue.

    The returned callable mirrors your CLI `input_provider`: it blocks until a
    user message is available, then returns that message to `RunManager.play()`.

    Args:
        state: App state containing the active simulation and the message queue.

    Returns:
        Callable that takes no arguments and returns the next user message.

    Raises:
        ValueError: If the simulation state was not initialized properly.
    """
    q: Queue[str] = state["queue"]
    run: RunManager = state["run"]

    def input_provider() -> str:
        """A blocking input provider for the simulation's play loop.

        It just reads from the queue.
        """
        if run.state is None:
            raise ValueError("Simulation state was not initialized properly.")
        events = run.state.get("events", [])
        logger.debug(f"input_provider sees {len(events)} events: {events}")
        return q.get() # return an item (event) from the queue

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

    logger.debug("Starting simulation play loop in background thread.")
    run: RunManager = state["run"]
    ip = _make_input_provider(state)

    thread = Thread(target=lambda: run.play(input_provider=ip), daemon=True)
    thread.start()
    state["_play_thread"] = thread

def on_play(state: AppState, token_value: Optional[str] = None) -> Tuple[AppState, dict[str, Any], dict[str, Any]]:
    """Handle clicking the Play button on the landing page.

    - tries calling RunManager.create and updates state with run or permission error
    """
    logger.debug(f"on_play called with token: {token_value}")
    if state["access_gated"] and not token_value:
        return state, gr.update(visible=True, value="Access token required")
    
    try:
        run = RunManager.create(
            game=state["game_name"],
            source="widget",
            access_key=token_value
            )
        state["run"] = run
        state["queue"] = Queue()
        state["last_seen"] = 0  # for polling new events
        state["last_special_seen"] = None
        _ensure_play_running(state)
        updated_chat_container = gr.update(visible=True)
        updated_landing_container = gr.update(visible=False)
        # if using a token, also update token box
        if token_value:
            updated_token_error_box = gr.update(visible=False, value="")
            updated_token_box = gr.update(value="")
            return state, updated_token_box, updated_token_error_box, updated_landing_container, updated_chat_container
        return state, updated_landing_container, updated_chat_container
    except PermissionError as e:
        logger.warning(f"PermissionError in on_play: {e}")
        if state["access_gated"]:
            state["permission_error"] = str(e)
            token_error_box_update = gr.update(visible=True)
            token_box_update = gr.update(value="")
            return state, token_box_update, token_error_box_update
        else:
            raise
    except Exception as e:
        logger.error(f"Error while handling on_play: {e}", exc_info=True)
        raise
    
def on_generate_token(state: AppState):
    """Handle clicking the Generate New Access Token button on the landing page.

    Takes landing container and consent container and sets visibility to show consent form and not landing.
    """
    logger.debug("on_generate_token called")
    updated_landing = gr.update(visible=False)
    updated_consent = gr.update(visible=True)
    return state, updated_landing, updated_consent

def on_consent_back(state: AppState):
    """Handle clicking the Back button on the consent page.

    Takes landing container and consent container and sets visibility to show landing and not consent form.
    """
    logger.debug("on_consent_back called")
    updated_landing = gr.update(visible=True)
    updated_consent = gr.update(visible=False)
    return state, updated_landing, updated_consent

def on_consent_submit(state: AppState, field_names: List[str], *field_values: List[Any]):
    """Handle clicking the I Agree & Continue button on the consent page.

    - creates player with consent data, issues access token
    - takes landing container and consent container and sets visibility to show landing and not consent form.
    """
    # TODO: validate consent fields and if not valid return error message text below
    consent_data = dict(zip(field_names, field_values))
    logger.debug(f"on_consent_submit called with field_values: {consent_data}")
    # create player with consent data, issue access token
    from dcs_simulation_engine.helpers import database_helpers as dbh
    try:
        player_id, access_key = dbh.create_player(
            player_data=consent_data,
            issue_access_key=True
        )
        logger.debug(f"Created player {player_id} with access key.")
        updated_form_group = gr.update(visible=False)
        updated_token_group = gr.update(visible=True)
        updated_token_text = gr.update(placeholder=access_key)
        return state, updated_form_group, updated_token_group, updated_token_text
    except Exception as e:
        logger.error(f"Error creating player in on_consent_submit: {e}", exc_info=True)
        raise

def on_token_continue(state: AppState):
    """Handle clicking the Continue button on the token display page.

    Takes landing container and consent container and sets visibility to show landing and not consent form.
    """
    logger.debug("on_token_continue called")
    updated_landing = gr.update(visible=True)
    updated_token_group = gr.update(visible=False)
    # IMPORTANT: clear token display
    updated_token_text = gr.update(placeholder="")  # clear placeholder
    logger.debug("Cleared token display on continue.")
    updated_consent = gr.update(visible=False)
    return state, updated_landing, updated_token_group, updated_consent, updated_token_text

def poll_fn(
    chat: List[Event], state: Dict[str, Any]
) -> Tuple[List[Event], Dict[str, Any]]:
    """Poll for new events (messages are called events in the simulator) from the simulation engine to update the chat history."""
    run: Optional[RunManager] = state.get("run")
    if run is None or run.state is None or "last_seen" not in state:
        return chat, state, gr.update()
    if run.exited:
        # don't poll for new events if the run is stopped
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
    
    # append any new special user message if exists
    special = run.state["special_user_message"]
    if isinstance(special, dict):
        key = (str(special.get("type") or "info").lower(), str(special.get("content") or ""))
        if key[1] and key != state.get("last_special_seen"):  # non-empty content and not yet shown
            chat.append({"role": "assistant", "content": _format_special(special)})
            state["last_special_seen"] = key

    # append new events since last seen
    events = run.state.get("events", [])
    # logger.debug(f"poll_fn sees {len(msgs)} messages, last_seen={state['last_seen']}")
    for e in events[state.get("last_seen") :]:
        logger.debug(f"poll_fn appending event: {e} to chat: {chat}")
        if isinstance(e, AIMessage):
            role = "assistant"
        elif isinstance(e, HumanMessage):
            role = "user"
        else:
            role = "assistant"  # fallback

        chat.append({"role": role, "content": e.content})

    state["last_seen"] = len(events)
    updated_timer = gr.update() # keep ticking
    return chat, state, updated_timer

def on_send(
    event: str, events: List[Event], state: Dict[str, Any]
) -> Tuple[List[Event], str]:
    """Handle a user event/message: enqueue it and return the latest engine reply.

    Behavior mirrors the CLI:
    1) Puts the user message into the queue consumed by the input provider.
    2) Waits for the engine to append a new message to `run.state["events"]`.
    3) Appends the (user, ai) pair to the Gradio Chatbot history.

    Args:
        event: The user's input text from the textbox.
        chat: Current Chatbot history.
        state: gr.State dictionary containing the active simulation and queue.

    Returns:
        Tuple[List[Message], str]: Updated Chatbot history and an empty string
        to clear the input textbox.

    Notes:
        Includes a safety timeout (120s) to avoid indefinite waiting.
    """
    
    logger.debug(f"on_send called with event: {event}")
    
    app_state: AppState = AppState(**state) if isinstance(state, dict) else AppState()
    run: RunManager = app_state.get("run")

    if run.exited:
        logger.debug(f"on_send found run.exited True; not enqueuing event: {event}")
        return (
            events
            + [
                {
                    "role": "assistant",
                    "content": f"The simulation has ended. Reason: {run.exit_reason}",
                }
            ],
            "",
        )

    # Ensure the play loop is alive (idempotent)
    _ensure_play_running(app_state)

    # Enqueue user message for the input provider
    if "queue" not in app_state:
        raise ValueError("App state is missing the event queue.")
    
    logger.debug(f"Enqueuing event: {event}")
    app_state["queue"].put(event)

    # Show user message immediately    
    events = events + [{"role": "user", "content": event}]

    return events, ""
