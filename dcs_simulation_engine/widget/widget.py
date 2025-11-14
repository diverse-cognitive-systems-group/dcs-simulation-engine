"""Gradio widget construction."""

from __future__ import annotations

from typing import Any, Dict

import gradio as gr
from loguru import logger

from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from dcs_simulation_engine.widget.helpers import cleanup
from dcs_simulation_engine.widget.session_state import SessionState
from dcs_simulation_engine.widget.ui.chat import build_chat
from dcs_simulation_engine.widget.ui.form import build_form
from dcs_simulation_engine.widget.ui.game_setup import build_game_setup
from dcs_simulation_engine.widget.ui.gate import build_gate
from dcs_simulation_engine.widget.ui.header import build_header
from dcs_simulation_engine.widget.wiring import wire_handlers

MAX_TTL_SECONDS = 24 * 3600  # 24 hours


def build_widget(
    game_name: str = "explore",
    banner: str | None = None,
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
            if game_config.access_settings.new_player_form is None:
                raise ValueError(
                    "Game config requires access gating but no new player form provided"
                )
        else:
            logger.debug("No access gating required. Prepopulating valid characters.")
            valid_pcs, valid_npcs = game_config.get_valid_characters(
                return_formatted=True
            )
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
        title="DCS Simulation Engine",
        theme=gr.themes.Default(primary_hue="violet"),
    )
    with widget:
        state = gr.State(
            value=SessionState(
                access_gated=access_gated,
                game_config=game_config,
                valid_pcs=valid_pcs if not access_gated else [],
                valid_npcs=valid_npcs if not access_gated else [],
                player_id=None,
                pc_choice=None,
                npc_choice=None,
                is_user_turn=False,
                last_seen=0,
            ),
            time_to_live=MAX_TTL_SECONDS,
            delete_callback=cleanup,  # function to call when state is deleted
        )
        # add custom css look to freeze on system error
        gr.HTML(
            """
            <style>
            /* Overlay for errors */
            .frozen::after {
                content: "";
                position: absolute;
                inset: 0;
                background: rgba(255, 255, 255, 0.3); /* fog: 0.5–0.8 works well */
                backdrop-filter: blur(2px);           /* glassy look */
                pointer-events: all;
            }

            /* Block interaction with children */
            .frozen > * {
                pointer-events: none;
            }
            </style>
        """
        )

        build_header(game_config, banner)
        # Build game setup page based on config
        game_setup = build_game_setup(
            access_gated=access_gated,
            valid_pcs=valid_pcs if not access_gated else [],
            valid_npcs=valid_npcs if not access_gated else [],
        )
        # Build chat page
        chat = build_chat(state=state, access_gated=access_gated)

        # Build gates if needed
        gate = build_gate(access_gated)
        form_config: Dict[str, Any]
        if access_gated and game_config.access_settings.new_player_form is not None:
            form_config = game_config.access_settings.new_player_form.model_dump()
        else:
            form_config = {}
        form = build_form(access_gated, form_config)

        # Wire up event handlers
        wire_handlers(state, gate, form, game_setup, chat)

        ### CLEAN UP ON DISCONNECT ###

        def on_unload(req: gr.Request) -> None:
            """Handle per-user client disconnect resources (temp dirs, etc)."""
            logger.debug(f"Client disconnected with session hash: {req.session_hash}")
            cleanup(state)

        # unload runs when the session ends (tab close, refresh, hard nav away)
        widget.unload(on_unload)

        # TODO: how to handle whole app crashes....

    return widget
