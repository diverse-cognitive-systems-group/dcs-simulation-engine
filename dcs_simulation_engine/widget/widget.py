"""Gradio app construction for the simulation engine.

Adds a centered title and an Instructions panel derived from the loaded
simulation's characters (A/B) and graph, similar to the CLI UI.
"""

from __future__ import annotations

import gradio as gr
from loguru import logger

from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from dcs_simulation_engine.widget.session_state import SessionState
from dcs_simulation_engine.widget.ui.chat import build_chat
from dcs_simulation_engine.widget.ui.consent import build_consent
from dcs_simulation_engine.widget.ui.game_setup import build_game_setup
from dcs_simulation_engine.widget.ui.gate import build_gate
from dcs_simulation_engine.widget.ui.header import build_header
from dcs_simulation_engine.widget.wiring import wire_handlers

MAX_TTL_SECONDS = 24 * 3600  # 24 hours


def _cleanup(state: gr.State) -> None:
    """Clean up resources associated with a session."""
    logger.debug("Cleaning up session resources")
    session_state: SessionState = state.value
    if "run" not in session_state:
        logger.debug("No 'run' in session state to clean up")
        return
    try:
        logger.debug("Exiting simulation...")
        session_state["run"].exit(reason="session deleted")
    except Exception:
        logger.exception("Failed to cleanly exit simulation on delete")
    finally:
        logger.debug("Session cleanup complete.")


def build_widget(
    game_name: str = "explore",
    banner: str | None = None,
    show_npc_selector: bool = True,
    show_pc_selector: bool = True,
) -> gr.Blocks:
    """Build the Gradio UI for running simulations."""
    logger.info(f"Building Gradio widget for game '{game_name}'")

    ### LOAD GAME CONFIGS/SETTINGS ###

    try:
        logger.debug(f"Loading game config for game '{game_name}'")
        game_config_path = get_game_config(game_name)
        game_config = GameConfig.from_yaml(game_config_path)
    except Exception as e:
        gr.Error(f"Failed to load game config: {e}")
        raise e  # terminate build

    try:
        logger.debug("Checking if access should be gated")
        access_gated = not bool(game_config.is_player_allowed(player_id=None))
        logger.debug(f"Access gate required: {access_gated}")
        if access_gated:
            if game_config.access_settings is None:
                raise ValueError(
                    "Game config requires access gating but has no access settings"
                )
            if game_config.access_settings.consent_form is None:
                raise ValueError(
                    "Game config requires access gating but no consent form provided"
                )
        else:
            logger.debug("No access gating required. Prepopulating valid characters.")
            valid_pcs, valid_npcs = game_config.get_valid_characters()
            logger.debug(
                f"Found {len(valid_pcs)} valid PCs and {len(valid_npcs)} valid NPCs."
            )
            if not valid_pcs:
                logger.warning("No valid PCs found for game.")
            if not valid_npcs:
                logger.warning("No valid NPCs found for game.")
    except Exception as e:
        gr.Error(f"Failed to determine access mode from game config: {e}")
        raise e  # terminate build

    ### BUILD WIDGET ###

    widget = gr.Blocks(
        title="DCS Simulation Engine", theme=gr.themes.Default(primary_hue="blue")
    )
    with widget:
        state = gr.State(
            value=SessionState(
                access_gated=access_gated,
                game_config=game_config,
                valid_pcs=valid_pcs if not access_gated else [],
                valid_npcs=valid_npcs if not access_gated else [],
                player_id=None,
                is_user_turn=False,
                last_seen=0,
            ),
            time_to_live=MAX_TTL_SECONDS,
            delete_callback=_cleanup,  # function to call when state is deleted
        )

        build_header(game_config, banner)
        # Build game setup page based on config
        play = build_game_setup(
            state=state,
            access_gated=access_gated,
            show_npc_selector=show_npc_selector,
            show_pc_selector=show_pc_selector,
            valid_pcs=valid_pcs if not access_gated else [],
            valid_npcs=valid_npcs if not access_gated else [],
        )
        # Build chat page
        chat = build_chat(state=state, access_gated=access_gated)

        # Build gates if needed
        gate = build_gate(access_gated)
        consent_form = game_config.access_settings.consent_form if access_gated else {}
        consent = build_consent(access_gated, consent_form)

        # Wire up event handlers
        wire_handlers(state, gate, consent, play, chat)

        ### CLEAN UP ON DISCONNECT ###

        def on_unload(req: gr.Request) -> None:
            """Handle per-user client disconnect resources (temp dirs, etc)."""
            logger.debug(f"Client disconnected with session hash: {req.session_hash}")
            _cleanup(state)

        # unload runs when the session ends (tab close, refresh, hard nav away)
        widget.unload(on_unload)

    return widget
