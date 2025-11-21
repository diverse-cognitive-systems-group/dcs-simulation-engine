"""Web handlers for Gradio interface to the DCS Simulation Engine.

Send → enqueue → sim.play consumes → timer polls state → new messages appear.

"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Dict, Iterator, List, Tuple

import gradio as gr
from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

import dcs_simulation_engine.helpers.database_helpers as dbh
from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.widget.constants import (
    MAX_INPUT_LENGTH,
    USER_FRIENDLY_EXC,
)
from dcs_simulation_engine.widget.helpers import (
    collect_form_answers,
    create_run,
    format,
    stream_msg,
)
from dcs_simulation_engine.widget.session_state import SessionState


def validate_chat_input(user_input: str) -> Any:
    """Validate user input before sending to the simulation.

    A function that takes in the inputs and can optionally return
    a gr.validate() object for each input.
    """
    # User input can be empty (e.g., just pressing Enter)
    # if not user_input.strip():
    #     return gr.validate(
    #         is_valid=False,
    #         message="Input cannot be empty.",
    #     )
    if len(user_input) > MAX_INPUT_LENGTH:
        return gr.validate(
            is_valid=False,
            message=f"Input is too long. Max chars: {MAX_INPUT_LENGTH}",
        )
    else:
        return gr.validate(is_valid=True, message="")


def handle_chat_feedback(data: gr.LikeData, state: SessionState) -> None:
    """Handle user feedback (like/dislike) on chat messages."""
    if "run" not in state:
        logger.error(
            "handle_feedback called but no active simulation run found in state."
        )
        return  # don't want to crash the app over feedback
    run = state["run"]
    logger.warning(
        f"🚩 Player ({run.player_id}) flagged a message as"
        f" '{data.liked}' in run '{run.name}': {data.value}"
    )
    data_dict = {
        "liked": data.liked,
        "value": data.value,
        "index": data.index,
    }
    run.feedback.append({"timestamp": datetime.now().isoformat(), "data": data_dict})
    logger.debug("Flag data saved")


# TODO: loading indicators for this process disappeared....not sure
# why but it was more user friendly before...look into it.
def setup_simulation(
    state: SessionState,
    pc_choice: str,
    npc_choice: str,
) -> Tuple[SessionState, List[Dict[str, Any]]]:
    """Handle clicking the Play button on the ungated landing page.

    - tries calling RunManager.create and updates state with run
    """
    try:
        logger.debug("Creating simulation run.")
        state["pc_choice"] = pc_choice
        state["npc_choice"] = npc_choice
        run = create_run(state)
        state["run"] = run
        logger.debug("Stepping simulation to get opener.")
        initial_history = []
        for e in run.step():
            if isinstance(e, AIMessage):
                formatted_response_partial = format(
                    {
                        "type": "ai",
                        "content": e.content,
                    }
                )  # type: ignore
                initial_history.append(
                    {"role": "assistant", "content": formatted_response_partial}
                )
            elif isinstance(e, HumanMessage):
                initial_history.append(
                    {"role": "user", "content": e.content}
                )  # type: ignore
            elif isinstance(e, dict) and "type" in e and "content" in e:
                formatted_response = format(e)
                initial_history.append(
                    {"role": "assistant", "content": formatted_response}
                )
            else:
                logger.warning(
                    f"Unknown message type in history during setup: {type(e)}"
                )
        state["initial_history"] = initial_history
        logger.debug(f"Initial history length: {len(initial_history)}")
        updated_chatbot_value = initial_history
        return state, updated_chatbot_value
    except Exception as e:
        logger.error(f"Error while handling on_play_ungated: {e}", exc_info=True)
        if "run" in state:
            run = state["run"]
            run.exit(reason="error")
        raise gr.Error(USER_FRIENDLY_EXC)


def on_gate_continue(state: SessionState, token_value: str) -> Tuple[
    SessionState,
    Dict[str, Any],  # gate container update
    Dict[str, Any],  # setup container update
    Dict[str, Any],  # setup no customization group update
    Dict[str, Any],  # setup customization group update
    Dict[str, Any],  # setup pc dropdown group update
    Dict[str, Any],  # setup npc dropdown group update
    Dict[str, Any],  # setup pc selector update
    Dict[str, Any],  # setup npc selector update
    Dict[str, Any],  # token box update
    Dict[str, Any],  # token error box update
]:
    """Handle clicking the Continue button on the gate page."""
    logger.debug("on_continue called with token")
    updated_gate_container = gr.update()
    updated_setup_container = gr.update()
    updated_setup_no_customization_group = gr.update()
    updated_setup_customization_group = gr.update()
    updated_setup_pc_dropdown_group = gr.update()
    updated_setup_npc_dropdown_group = gr.update()
    updated_setup_pc_selector = gr.update()
    updated_setup_npc_selector = gr.update()
    updated_token_box = gr.update()
    updated_token_error_box = gr.update()

    if "access_gated" not in state:
        logger.error("on_continue called without access_gated being set in state.")
        if "run" in state:
            run = state["run"]
            run.exit(reason="error")
        raise gr.Error(USER_FRIENDLY_EXC)
    if state["access_gated"] is False:
        logger.error("on_continue called but access_gated is False in state.")
        if "run" in state:
            run = state["run"]
            run.exit(reason="error")
        raise gr.Error(USER_FRIENDLY_EXC)

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

            # make sure player is allowed to play this game
            if "game_config" not in state:
                raise ValueError(
                    """App state is missing game_config
                                  required to get characters."""
                )

            if not state["game_config"].is_player_allowed(player_id=player_id):
                logger.warning(
                    f"Player {player_id} is not allowed to play"
                    " this game according to game_config."
                )
                raise gr.Error(
                    "Sorry, your account is not authorized to"
                    " access this game. If you think this is an error, "
                    "please let us know."
                )

            updated_gate_container = gr.update(visible=False)
            updated_token_box = gr.update(value="")
            updated_token_error_box = gr.update(visible=False, value="")
            updated_setup_container = gr.update(visible=True)

            logger.debug(f"Getting valid characters for game with player: {player_id}")
            if "game_config" not in state:
                raise ValueError(
                    """App state is missing game_config
                                  required to get characters."""
                )

            game_config: GameConfig = state["game_config"]
            valid_pcs, valid_npcs = game_config.get_valid_characters(
                player_id=player_id
            )
            logger.debug(
                f"Updating internal gradio state with"
                f" {len(valid_pcs)} PCs and {len(valid_npcs)} NPCs."
            )
            state["valid_pcs"]: List[tuple[str, str]] = valid_pcs
            state["valid_npcs"]: List[tuple[str, str]] = valid_npcs
            if not valid_pcs:
                logger.warning("No valid PCs found for this player.")
                raise gr.Error(
                    "Sorry, no valid player characters available for"
                    " your account. If you think this is an error, "
                    "please contact support."
                )
            if not valid_npcs:
                logger.warning("No valid NPCs found for this player.")
                raise gr.Error(
                    "Sorry, no valid non-player characters available for"
                    " your account. If you think this is an error, "
                    "please contact support."
                )
            updated_setup_no_customization_group = gr.update(visible=False)
            updated_setup_customization_group = gr.update(visible=True)
            updated_setup_pc_dropdown_group = gr.update(visible=bool(valid_pcs))
            updated_setup_npc_dropdown_group = gr.update(visible=bool(valid_npcs))
            updated_setup_pc_selector = gr.update(
                choices=valid_pcs,
                value=(random.choice(valid_pcs)[1] if valid_pcs else None),
            )
            updated_setup_npc_selector = gr.update(
                choices=valid_npcs,
                value=(random.choice(valid_npcs)[1] if valid_npcs else None),
            )
        except PermissionError as e:
            logger.warning(f"PermissionError in on_continue: {e}")
            updated_token_error_box = gr.update(
                visible=True, value="  Invalid access token"
            )
        except gr.Error as e:
            logger.error(
                "Gradio Error while handling on_continue: {}", e, exc_info=True
            )
            if "run" in state:
                run = state["run"]
                run.exit(reason="error")
            raise e  # re-raise gr.Error as is
        except Exception as e:
            logger.error("Error while handling on_continue: {}", e, exc_info=True)
            if "run" in state:
                run = state["run"]
                run.exit(reason="error")
            raise gr.Error(USER_FRIENDLY_EXC)
    return (
        state,
        updated_gate_container,
        updated_setup_container,
        updated_setup_no_customization_group,
        updated_setup_customization_group,
        updated_setup_pc_dropdown_group,
        updated_setup_npc_dropdown_group,
        updated_setup_pc_selector,
        updated_setup_npc_selector,
        updated_token_box,
        updated_token_error_box,
    )


def on_form_submit(
    state: SessionState, *field_values: Any
) -> Tuple[
    SessionState, Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]
]:
    """Handle clicking submit on the consent form.

    - creates player with consent data, issues access token
    - takes landing container and consent container and sets visibility to show
    landing and not consent form.
    """
    logger.debug(f"on_form_submit called with {len(field_values)} form values.")

    if "game_config" not in state:
        logger.error("App state missing game_config in on_form_submit.")
        raise gr.Error(USER_FRIENDLY_EXC)
    form_config = state["game_config"].access_settings.new_player_form
    if not form_config:
        logger.error("No form_config found in state during on_form_submit.")
        raise gr.Error(USER_FRIENDLY_EXC)

    form_config_dict = form_config.model_dump()
    ok, message, answers_dict = collect_form_answers(form_config_dict, field_values)
    logger.debug(f"Form validation result: ok={ok}, message={message}")
    if not ok:
        logger.debug("Form validation failed.")
        gr.Warning(message, duration=None, title="Form Validation Error")
        return (  # unchanged state, show form with error
            state,
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
        )

    # create player with consent data, issue access token
    try:
        new_player_data: Dict[str, Dict[str, Any]] = {
            q.key: {**q.model_dump(), "answer": value}
            for q, value in zip(form_config.questions, field_values)
        }
        player_id, access_key = dbh.create_player(
            player_data=new_player_data, issue_access_key=True
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
        if "run" in state:
            run = state["run"]
            run.exit(reason="error")
        raise gr.Error(USER_FRIENDLY_EXC)


def process_new_user_chat_message(
    new_user_message: str,
    history: List[Dict[str, str]],
    state: SessionState,
) -> Iterator[str]:
    """Handle a user message sent from the chat interface."""
    logger.debug(
        f"on_new_user_message called \nwith\nnew_user_message: {new_user_message}\n"
        f"len(history): {len(history)}"
    )

    if "run" not in state:
        logger.error(
            "on_new_user_message called but no active simulation run found in state."
        )
        raise gr.Error(USER_FRIENDLY_EXC)
    run = state["run"]

    # Add any initial history if not already present
    if "initial_history" not in state:
        logger.warning("No initial_history found in state during on_new_user_message.")
    else:
        initial_history = state["initial_history"]
        if len(history) == 0:
            logger.debug("Adding initial history to chat history.")
            history.extend(initial_history)

    # Block until the simulator returns or response time thresholds are met
    try:
        # simulator may have exited after step()
        if run.exited:
            logger.debug(
                "on_new_user_message found run.exited True after step();"
                " not streaming response"
            )
            formatted_response = format(
                {
                    "type": "info",
                    "content": (
                        f"Simulator has exited and will not process "
                        f"further input. Sorry. (Exit reason: {run.exit_reason})"
                    ),
                }
            )
            yield formatted_response
        else:
            for event in run.step(new_user_message):
                etype = event.get("type")
                content = event.get("content")

                # format simulator responses/messages for gradio chat display
                if etype in {"ai", "assistant"}:
                    formatted_response = format(
                        {
                            "type": "ai",
                            "content": content,
                        }
                    )
                    logger.warning(f"DEBUG::: simulator reply: {formatted_response}")
                    yield from stream_msg(formatted_response)  # stream simulator reply
                elif etype in {"info", "system", "error", "warning"}:
                    formatted_response = format(
                        {
                            "type": etype,
                            "content": content,
                        }
                    )
                    logger.warning(f"DEBUG::: simulator reply: {formatted_response}")
                    yield formatted_response  # don't stream system/info messages
                else:
                    logger.warning(
                        f"Unknown event type yielded from simulator: {etype}."
                        " Skipping display."
                    )
                    continue
    except Exception:
        logger.exception("Simulator step raised an exception.")
        formatted_response = format(
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
        if "run" in state:
            run = state["run"]
            run.exit(reason="error")
        raise gr.Error(USER_FRIENDLY_EXC)
    logger.debug("Generator done yielding response.")
