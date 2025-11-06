"""Web handlers for Gradio interface to the DCS Simulation Engine.

Send → enqueue → sim.play consumes → timer polls state → new messages appear.

"""

from __future__ import annotations

from queue import Queue
from threading import Thread
from typing import Any, Callable, Dict, List, Optional, Tuple

import gradio as gr
from langchain_core.messages import HumanMessage
from loguru import logger

from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.core.simulation_graph.state import SpecialUserMessage
from dcs_simulation_engine.widget.session_state import SessionState

# Messages are "events" in the simulator
Event = Dict[str, str]


def _create_run(state: SessionState, token_value: Optional[str] = None) -> RunManager:
    """Create a new RunManager and return it."""
    if "game_name" not in state:
        raise ValueError("App state is missing game_name required to create run.")
    run = RunManager.create(
        game=state["game_name"], source="widget", access_key=token_value
    )
    return run


def _format_special(msg: SpecialUserMessage) -> str:
    """Format a special user message for gradio."""
    t = (msg.get("type") or "info").lower()
    c = msg.get("content") or ""
    if t == "warning":
        return f"⚠️ {c}"
    if t == "error":
        return f"❌ {c}"
    return f"----<br>{c}<br>----"


def _make_input_provider(state: SessionState) -> Callable[[], str]:
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
    if "queue" not in state:
        raise ValueError("App state is missing the event queue.")
    if "run" not in state:
        raise ValueError("App state is missing the active simulation run.")
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
        return q.get()  # return an item (event) from the queue

    return input_provider


def _ensure_play_running(state: SessionState) -> None:
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
    run = state.get("run", None)
    if not run:
        raise ValueError("Cannot start play loop: no active simulation run found.")

    ip = _make_input_provider(state)

    thread = Thread(target=lambda: run.play(input_provider=ip), daemon=True)
    thread.start()
    state["_play_thread"] = thread


def on_play_ungated(
    state: SessionState,
) -> Tuple[
    SessionState,
    Dict[str, Any],  # landing container update
    Dict[str, Any],  # chat container update
    Dict[str, Any],  # user input box update
    Dict[str, Any],  # send button update
    Dict[str, Any],  # loader update
]:
    """Handle clicking the Play button on the ungated landing page.

    - tries calling RunManager.create and updates state with run
    """
    logger.debug("on_play_ungated called")
    try:
        run = _create_run(state)
        state["run"] = run
        state["queue"] = Queue()
        _ensure_play_running(state)
        updated_landing_container = gr.update(visible=False)
        updated_chat_container = gr.update(visible=True)
        updated_user_box = gr.update(interactive=False)
        updated_send_btn = gr.update(interactive=False)
        updated_loader = gr.update(
            visible=True,
            value="""⏳ *Setting up simulation and loading 
            opening scene (this may take a moment)...*""",
        )
        return (
            state,
            updated_landing_container,
            updated_chat_container,
            updated_user_box,
            updated_send_btn,
            updated_loader,
        )
    except Exception as e:
        logger.error(f"Error while handling on_play_ungated: {e}", exc_info=True)
        raise


def on_play_gated(state: SessionState, token_value: str) -> Tuple[
    SessionState,
    Dict[str, Any],  # landing container update
    Dict[str, Any],  # chat container update
    Dict[str, Any],  # user input box update
    Dict[str, Any],  # send button update
    Dict[str, Any],  # loader update
    Dict[str, Any],  # token box update
    Dict[str, Any],  # token error box update
]:
    """Handle clicking the Play button on the landing page."""
    logger.debug("on_play_gated called with token")
    if "access_gated" not in state:
        raise ValueError("on_play called without access_gated being set in state.")
    if state["access_gated"] is False:
        raise ValueError("on_play_gated called but access_gated is False in state.")

    updated_landing_container = gr.update()
    updated_chat_container = gr.update()
    updated_user_box = gr.update()
    updated_send_btn = gr.update()
    updated_loader = gr.update()
    updated_token_box = gr.update()

    if not token_value:  # empty token "" or None
        logger.debug(
            "Access gated but no token provided; returning token validation error."
        )
        updated_token_error_box = gr.update(visible=True, value="Access token required")
    else:
        logger.debug("Proceeding to create simulation run.")
        try:
            run = _create_run(state, token_value=token_value)
            state["run"] = run
            state["queue"] = Queue()
            _ensure_play_running(state)
            updated_landing_container = gr.update(visible=False)
            updated_chat_container = gr.update(visible=True)
            updated_user_box = gr.update(interactive=False)
            updated_send_btn = gr.update(interactive=False)
            updated_loader = gr.update(
                visible=True,
                value="""⏳ *Setting up simulation and loading 
                opening scene (this may take a moment)...*""",
            )
            updated_token_error_box = gr.update(visible=False, value="")
            updated_token_box = gr.update(value="")
        except PermissionError as e:
            logger.warning(f"PermissionError in on_play_gated: {e}")
            updated_token_error_box = gr.update(
                visible=True, value="Invalid access token"
            )
        except Exception as e:
            logger.error(f"Error while handling on_play_gated: {e}", exc_info=True)
            raise
    return (
        state,
        updated_landing_container,
        updated_chat_container,
        updated_user_box,
        updated_send_btn,
        updated_loader,
        updated_token_box,
        updated_token_error_box,
    )


def on_generate_token(
    state: SessionState,
) -> Tuple[SessionState, Dict[str, Any], Dict[str, Any]]:
    """Handle clicking the Generate New Access Token button on the landing page.

    Takes landing container and consent container and sets
    visibility to show consent form and not landing.
    """
    logger.debug("on_generate_token called")
    updated_landing = gr.update(visible=False)
    updated_consent = gr.update(visible=True)
    return state, updated_landing, updated_consent


def on_consent_back(
    state: SessionState,
) -> Tuple[SessionState, Dict[str, Any], Dict[str, Any]]:
    """Handle clicking the Back button on the consent page.

    Takes landing container and consent container and sets visibility to show landing and not consent form.
    """
    logger.debug("on_consent_back called")
    updated_landing = gr.update(visible=True)
    updated_consent = gr.update(visible=False)
    return state, updated_landing, updated_consent


def on_consent_submit(
    state: SessionState, field_names: List[str], *field_values: List[Any]
) -> Tuple[
    SessionState, Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]
]:
    """Handle clicking the I Agree & Continue button on the consent page.

    - creates player with consent data, issues access token
    - takes landing container and consent container and sets visibility to show landing and not consent form.
    """
    # TODO: validate consent fields and if not valid return error message text below
    user_data = {
        "consent_signed": True,
        "consent_form_data": dict(zip(field_names, field_values)),
    }
    # create player with consent data, issue access token
    from dcs_simulation_engine.helpers import database_helpers as dbh

    try:
        player_id, access_key = dbh.create_player(
            player_data=user_data, issue_access_key=True
        )
        logger.debug(f"Created player {player_id} with access key.")
        updated_form_group = gr.update(visible=False)
        updated_token_group = gr.update(visible=True)
        updated_token_text = gr.update(value=access_key)
        updated_token_error_box = gr.update(visible=False, value="")
        return (
            state,
            updated_form_group,
            updated_token_group,
            updated_token_text,
            updated_token_error_box,
        )
    except Exception as e:
        logger.error(f"Error creating player in on_consent_submit: {e}", exc_info=True)
        raise


def on_token_continue(
    state: SessionState,
) -> Tuple[
    SessionState,
    Dict[str, Any],  # landing container update
    Dict[str, Any],  # token group update
    Dict[str, Any],  # consent container update
    Dict[str, Any],  # token text update
]:
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
    updated_token_error_box = gr.update(visible=False, value="")
    return (
        state,
        updated_landing,
        updated_token_group,
        updated_consent,
        updated_token_text,
    )


def poll_fn(state: SessionState, events_chat: List[Event]) -> Tuple[
    SessionState,
    List[Event],
    Dict[str, Any],  # timer update
    Dict[str, Any],  # user_box update
    Dict[str, Any],  # send_btn update
    Dict[str, Any],  # loader update
]:
    """Poll for new events to update the chat history."""
    run = state.get("run", None)
    if run is None or run.state is None or "last_seen" not in state:
        # no active run, nothing to poll
        updated_events_chat = events_chat
        updated_timer = gr.update()
        updated_user_box = gr.update()
        updated_send_btn = gr.update()
        updated_loader = gr.update()
    elif run.exited:
        # don't poll for new events if the run is stopped
        end_event = {
            "role": "assistant",
            "content": f"The simulation has ended. Reason: {run.exit_reason}",
        }
        updated_events_chat = events_chat + [end_event]
        updated_timer = gr.update(active=False)
        updated_user_box = gr.update(interactive=False)
        updated_send_btn = gr.update(interactive=False)
        updated_loader = gr.update(visible=False)
    else:
        # DISPLAY - new new special user messages (if exists)
        special = run.state["special_user_message"]
        if isinstance(special, dict):
            key = (
                str(special.get("type") or "info").lower(),
                str(special.get("content") or ""),
            )
            if key[1] and key != state.get(
                "last_special_seen"
            ):  # non-empty content and not yet shown
                events_chat.append(
                    {"role": "assistant", "content": _format_special(special)}
                )
                state["last_special_seen"] = key
                state["is_user_turn"] = True  # after special message, it's user's turn
                logger.debug("Setting is_user_turn to True after special message")

        # DISPLAY - new event content since last seen (if any)
        events = run.state["events"]
        for e in events[state.get("last_seen") :]:
            if not isinstance(e, HumanMessage):
                logger.debug(f"poll_fn appending: {e} to events")
                events_chat.append({"role": "assistant", "content": e.content})  # type: ignore
                state["is_user_turn"] = True  # after AI message, it's user's turn
                logger.debug("Setting is_user_turn to True after AI message")

        updated_events_chat = events_chat
        state["last_seen"] = len(events)
        updated_timer = gr.update()  # keep ticking

        # if last event is from user, keep input disabled, else re-enable it
        if len(events) == 0:
            # logger.debug("No events yet; keeping user input disabled.")
            state["is_user_turn"] = False
            updated_user_box = gr.update(interactive=False)
            updated_send_btn = gr.update(interactive=False)
            updated_loader = gr.update(
                visible=True,
                value="""⏳ *Setting up simulation and loading 
                opening scene (this may take a moment)...*""",
            )
        if state.get("is_user_turn", False):
            # logger.debug("User's turn; enabling user input.")
            updated_user_box = gr.update(interactive=True)
            updated_send_btn = gr.update(interactive=True)
            updated_loader = gr.update(visible=False)
        else:
            # logger.debug("Not user's turn; disabling user input.")
            updated_user_box = gr.update(interactive=False)
            updated_send_btn = gr.update(interactive=False)
            updated_loader = gr.update(visible=True, value="⏳ *Thinking...*")
    return (
        state,
        updated_events_chat,
        updated_timer,
        updated_user_box,
        updated_send_btn,
        updated_loader,
    )


def on_send(
    state: SessionState, event: str, events: List[Event]
) -> Tuple[SessionState, Dict[str, Any], List[Event]]:
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

    run = state.get("run", None)

    if not run:
        raise ValueError("on_send called but no active simulation run found in state.")

    if run.exited:
        logger.debug(f"on_send found run.exited True; not enqueuing event: {event}")
        end_event = {
            "role": "assistant",
            "content": f"The simulation has ended. Reason: {run.exit_reason}",
        }
        updated_user_box = gr.update(interactive=False)
        updated_events = events + [end_event]
    else:
        # disable user input until engine responds
        state["is_user_turn"] = False
        logger.debug("Setting is_user_turn to False")

        # Ensure the play loop is alive (idempotent)
        _ensure_play_running(state)

        # Enqueue user message for the input provider
        if "queue" not in state:
            raise ValueError("App state is missing the event queue.")

        logger.debug(f"Enqueuing event: {event}")
        state["queue"].put(event)

        # Show user message immediately
        updated_events = events + [{"role": "user", "content": event}]
        updated_user_box = gr.update(value="", interactive=False)

    return state, updated_user_box, updated_events
