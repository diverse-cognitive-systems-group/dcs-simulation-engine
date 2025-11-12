"""Web handlers for Gradio interface to the DCS Simulation Engine.

Send → enqueue → sim.play consumes → timer polls state → new messages appear.

"""

from __future__ import annotations

import time
from queue import Queue
from typing import Any, Dict, Iterator, List, Optional, Tuple

import gradio as gr
from langchain_core.messages import HumanMessage
from loguru import logger

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.widget.session_state import SessionState

# Messages are "events" in the simulator
Event = Dict[str, str]

# Tunables
LONG_RESPONSE_THRESHOLD = 25.0  # seconds before we warn it's taking longer
RESPONSE_TIMEOUT = 60.0  # hard timeout for a response
POLL_INTERVAL = 1  # how often we check for completion
MAX_INPUT_LENGTH = 1000  # max length of user input string in characters
FRIENDLY_GR_ERROR = (
    "Yikes! We encountered an error while processing your input."
    " Its been logged and we're looking into it. Sorry about that."
)


def _wpm_to_cps(wpm: int) -> float:
    """Convert words-per-minute to characters-per-second.

    Assumes average word length of 5 characters.
    """
    return max(1.0, (wpm * 5) / 60.0)


def _slow_yield_chars(
    message: str,
    wpm: int = 180,  # ~15 cps
    min_yield_interval: float = 0.03,  # don’t spam UI; yield at most ~33 FPS
) -> Iterator[str]:
    cps = _wpm_to_cps(wpm)
    per_char = 1.0 / cps

    # Natural micro-pauses after punctuation
    pauses = {
        ".": 0.35,
        "!": 0.35,
        "?": 0.35,
        ",": 0.12,
        ";": 0.15,
        ":": 0.15,
        "\n": 0.22,
        "—": 0.10,
        "…": 0.20,
    }

    built = []
    next_yield_at = time.perf_counter()  # throttle UI updates

    for ch in message:
        built.append(ch)
        time.sleep(per_char)

        # add extra pause after certain punctuation
        if ch in pauses:
            time.sleep(pauses[ch])

        now = time.perf_counter()
        if now >= next_yield_at:
            yield "".join(built)
            next_yield_at = now + min_yield_interval

    # final flush
    yield "".join(built)


def _stream_msg(message: str) -> Iterator[str]:
    """Streams a message at about reading speed."""
    for partial in _slow_yield_chars(
        message,
        # wpm=random.randint(150, 220),
    ):
        yield partial


def _create_run(state: SessionState, token_value: Optional[str] = None) -> RunManager:
    """Create a new RunManager and return it."""
    if "game_config" not in state:
        raise ValueError("App state is missing game_config required to create run.")
    if "player_id" not in state:
        state["player_id"] = None
    pc_choice = state.get("pc_choice", None)
    npc_choice = state.get("npc_choice", None)
    try:
        run = RunManager.create(
            game=state["game_config"].name,
            source="widget",
            pc_choice=pc_choice,
            npc_choice=npc_choice,
            player_id=state["player_id"],
        )
    except Exception as e:
        logger.error(f"Error creating RunManager in _create_run: {e}", exc_info=True)
        raise gr.Error(FRIENDLY_GR_ERROR)
    return run


def _format(msg_dict: Dict[str, Any]) -> str:
    """Format dict style message into a markdown formatted string for gradio display."""
    if not isinstance(msg_dict, dict):
        logger.error(
            f"Received non-dict message in _format: {msg_dict}. Returning str()."
        )
        raise gr.Error(FRIENDLY_GR_ERROR)
    if "type" not in msg_dict or "content" not in msg_dict:
        logger.warning(
            f"Received malformed message in _format: {msg_dict}."
            " Dict must include 'type' and 'content' keys."
        )
        raise gr.Error(FRIENDLY_GR_ERROR)
    t = (msg_dict.get("type") or "info").lower()
    c = msg_dict.get("content") or ""
    if not c:
        logger.warning("Received empty content in _format.")
    if t == "warning":
        return f"⚠️ {c}"
    elif t == "error":
        return f"❌ {c}"
    elif t == "info":
        return f"*{c}*"
    elif t == "system" or t == "assistant" or t == "ai":
        return c
    else:
        logger.warning(f"Unknown message type '{t}' in _format; returning raw content.")
        return c


def show_chat_view() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Handle showing the chat view and hiding the game setup view."""
    update_game_setup = gr.update(visible=False)
    update_chat = gr.update(visible=True)
    updated_chatinterface = gr.update(visible=False)  # disable textbox initially
    return update_game_setup, update_chat, updated_chatinterface


def setup_simulation(
    state: SessionState,
) -> Tuple[SessionState, Dict[str, Any]]:
    """Handle clicking the Play button on the ungated landing page.

    - tries calling RunManager.create and updates state with run
    """
    try:
        logger.debug("Creating simulation run.")
        run = _create_run(state)
        state["run"] = run
        state["queue"] = Queue()  # TODO: remove if not needed
        logger.debug("Stepping simulation to get opener.")
        run.step()  # simulator takes first step to initialize
        initial_history = []
        special = run.state.get("special_user_message", None)
        if special:
            logger.debug("Found special user message on setup.")
            formatted_response_partial = _format(
                {
                    "type": special.get("type", ""),
                    "content": special.get("content", ""),
                }
            )
            initial_history.append(
                {"role": "assistant", "content": formatted_response_partial}
            )
        if run.state.get("events", []):
            logger.debug("Found events on setup.")
            for e in run.state["events"]:
                if not isinstance(e, HumanMessage):
                    formatted_response_partial = _format(
                        {
                            "type": "ai",
                            "content": e.content,
                        }
                    )  # type: ignore
                    initial_history.append(
                        {"role": "assistant", "content": formatted_response_partial}
                    )
        # initial_history = [
        #     {"role": "assistant", "content": "changed initial msg"},
        # ]
        updated_chatbot_value = gr.update(value=initial_history)
        return state, updated_chatbot_value
    except Exception as e:
        logger.error(f"Error while handling on_play_ungated: {e}", exc_info=True)
        raise gr.Error(
            """Yikes! We encountered an error starting the simulation.
            Its been logged and we're looking into it. Sorry about that."""
        )


def on_gate_continue(state: SessionState, token_value: str) -> Tuple[
    SessionState,
    Dict[str, Any],  # gate container update
    Dict[str, Any],  # play container update
    Dict[str, Any],  # play pc selector update
    Dict[str, Any],  # play npc selector update
    Dict[str, Any],  # token box update
    Dict[str, Any],  # token error box update
]:
    """Handle clicking the Continue button on the gate page."""
    logger.debug("on_continue called with token")
    if "access_gated" not in state:
        raise ValueError("on_continue called without access_gated being set in state.")
    if state["access_gated"] is False:
        raise ValueError("on_continue called but access_gated is False in state.")

    updated_gate_container = gr.update()
    updated_play_container = gr.update()
    updated_play_pc_selector = gr.update()
    updated_play_npc_selector = gr.update()
    updated_token_box = gr.update()
    updated_token_error_box = gr.update()

    if not token_value:  # empty token "" or None
        logger.debug(
            "Access gated but no token provided; returning token validation error."
        )
        updated_token_error_box = gr.update(
            visible=True, value="  Access token required"
        )
    else:
        try:
            logger.debug("Trying to get player ID from access token.")
            player_id = dbh.get_player_id_from_access_key(token_value)
            if not player_id:
                raise PermissionError("  Invalid access token: no such player.")
            logger.debug("Access token valid.")
            state["player_id"] = player_id

            updated_gate_container = gr.update(visible=False)
            updated_token_box = gr.update(value="")
            updated_token_error_box = gr.update(visible=False, value="")
            updated_play_container = gr.update(visible=True)

            logger.debug(f"Getting valid characters for game with player: {player_id}")
            if "game_config" not in state:
                raise ValueError(
                    """App state is missing game_config
                                  required to get characters."""
                )
            valid_pcs, valid_npcs = state["game_config"].get_valid_characters()
            state["valid_pcs"] = valid_pcs
            state["valid_npcs"] = valid_npcs
            if not valid_pcs:
                logger.warning("No valid PCs found for this player.")
            if not valid_npcs:
                logger.warning("No valid NPCs found for this player.")
            updated_play_pc_selector = gr.update(
                choices=valid_pcs, value=valid_pcs[0] if valid_pcs else None
            )
            updated_play_npc_selector = gr.update(
                choices=valid_npcs, value=valid_npcs[0] if valid_npcs else None
            )
        except PermissionError as e:
            logger.warning(f"PermissionError in on_continue: {e}")
            updated_token_error_box = gr.update(
                visible=True, value="  Invalid access token"
            )
        except Exception as e:
            logger.error("Error while handling on_continue: {}", e, exc_info=True)
            raise gr.Error(
                """An internal error occurred and has been logged. 
                We apologize and are looking into it."""
            )
    return (
        state,
        updated_gate_container,
        updated_play_container,
        updated_play_pc_selector,
        updated_play_npc_selector,
        updated_token_box,
        updated_token_error_box,
    )


def on_generate_token(
    state: SessionState,
) -> Tuple[
    SessionState, Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]
]:
    """Handle clicking the Generate New Access Token button on the landing page.

    Takes landing container and consent container and sets
    visibility to show consent form and not landing.
    """
    logger.debug("on_generate_token called")
    updated_gate = gr.update(visible=False)
    updated_consent = gr.update(visible=True)
    updated_token_box = gr.update(value="")  # clear token box
    updated_token_error_box = gr.update(visible=False, value="")  # clear error box
    return (
        state,
        updated_gate,
        updated_consent,
        updated_token_box,
        updated_token_error_box,
    )


def on_consent_submit(
    state: SessionState, field_names: List[str], *field_values: List[Any]
) -> Tuple[
    SessionState, Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]
]:
    """Handle clicking the I Agree & Continue button on the consent page.

    - creates player with consent data, issues access token
    - takes landing container and consent container and sets visibility to show
    landing and not consent form.
    """
    # TODO: validate consent fields and if not valid return error message text below
    user_data = {
        "consent_signed": True,
        "consent_form_data": dict(zip(field_names, field_values)),
    }
    # create player with consent data, issue access token
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
        raise gr.Error(
            """Yikes! We encountered an error while processing your consent form.
            Its been logged and we're looking into it. Sorry about that."""
        )


def on_token_continue(
    state: SessionState,
) -> Tuple[
    SessionState,
    Dict[str, Any],  # gate container update
    Dict[str, Any],  # token group update
    Dict[str, Any],  # consent container update
    Dict[str, Any],  # token text update
]:
    """Handle clicking the Continue button on the token display page."""
    logger.debug("on_token_continue called")
    updated_gate = gr.update(visible=True)
    updated_token_group = gr.update(visible=False)
    # IMPORTANT: clear token display
    updated_token_text = gr.update(placeholder="")  # clear placeholder
    logger.debug("Cleared token display on continue.")
    updated_consent = gr.update(visible=False)
    # updated_token_error_box = gr.update(visible=False, value="")
    return (
        state,
        updated_gate,
        updated_token_group,
        updated_consent,
        updated_token_text,
    )


def process_new_user_message(
    new_user_message: str,
    history: List[Event],
    state: SessionState,
    # ) -> Generator[str, None, Tuple[str, SessionState]]:
) -> Iterator[str]:
    """Handle a user message sent from the chat interface."""
    logger.debug(
        f"on_new_user_message called with new_user_message: {new_user_message}"
    )

    run = state.get("run", None)

    if not run:
        logger.error(
            "on_new_user_message called but no active simulation run found in state."
        )
        raise gr.Error(FRIENDLY_GR_ERROR)

    if run.exited:
        logger.debug(
            "on_new_user_message found run.exited True; not enqueuing user message"
        )
        formatted_response = _format(
            {
                "type": "info",
                "content": f"The simulation has ended. Reason: {run.exit_reason}",
            }
        )
        yield formatted_response
    else:
        # Block until the simulator returns or response time thresholds are met
        try:
            # TODO: presently this blocks, we want it to yield messages as they
            # become available from the simulator instead (step refactor needed)
            run.step(new_user_message)  # returns an updated state

            # simulator may have exited after step()
            if run.exited:
                logger.debug(
                    "on_new_user_message found run.exited True after step();"
                    " not streaming response"
                )
                formatted_response = _format(
                    {
                        "type": "info",
                        "content": f"Simulation exited. Reason: {run.exit_reason}",
                    }
                )
                yield formatted_response
            # Display any special user message first
            if run.state["special_user_message"]:
                special = run.state["special_user_message"]
                if isinstance(special, dict):
                    key = (
                        str(special.get("type") or "").lower(),
                        str(special.get("content") or ""),
                    )
                    # non-empty content and not yet shown
                    if key[1] and key != state.get("last_special_seen"):
                        formatted_response = _format(
                            {
                                "type": key[0],
                                "content": key[1],
                            }
                        )
                state["last_special_seen"] = key
                yield formatted_response
            # Display the any new AI messages from events
            events = run.state["events"]
            if "last_seen" not in state:
                state["last_seen"] = 0
            for e in events[state["last_seen"] :]:
                if not isinstance(e, HumanMessage):
                    formatted_response = _format(
                        {
                            "type": "ai",
                            "content": e.content,
                        }
                    )  # type: ignore
            state["last_seen"] = len(events)
            yield from _stream_msg(formatted_response)  # stream simulator reply
        except Exception:
            logger.exception("Simulator step raised an exception.")
            formatted_response = _format(
                {
                    "type": "error",
                    "content": (
                        "Yikes! We couldn't generate response."
                        " We're looking into it. Sorry about that."
                    ),
                }
            )
            yield formatted_response
            logger.error("Generator done yielding response (error).")
            raise gr.Error(FRIENDLY_GR_ERROR)
    logger.debug("Generator done yielding response.")


def validate_user_input(user_input: str) -> Optional[Dict[str, str]]:
    """Validate user input before sending to the simulation.

    A function that takes in the inputs and can optionally return
    a gr.validate() object for each input.
    """
    if not user_input.strip():
        return gr.validate(
            False,
            "Input cannot be empty.",
        )
    if len(user_input) > MAX_INPUT_LENGTH:
        return gr.validate(
            False,
            f"Input is too long. Please limit input to {MAX_INPUT_LENGTH} characters.",
        )
    return None
