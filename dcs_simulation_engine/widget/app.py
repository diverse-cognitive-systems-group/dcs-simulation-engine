"""Gradio app construction for the simulation engine.

Adds a centered title and an Instructions panel derived from the loaded
simulation's characters (A/B) and graph, similar to the CLI UI.
"""

from __future__ import annotations

import gradio as gr
from gradio.themes import Soft
from loguru import logger

from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from dcs_simulation_engine.widget.session_state import SessionState
from dcs_simulation_engine.widget.ui.chat import build_chat
from dcs_simulation_engine.widget.ui.consent import build_consent
from dcs_simulation_engine.widget.ui.header import build_header
from dcs_simulation_engine.widget.ui.landing import build_landing
from dcs_simulation_engine.widget.ui.theme_toggle import build_theme_toggle
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


def build_app(
    game_name: str = "explore",
    banner: str | None = None,
    show_npc_selector: bool = False,
    show_pc_selector: bool = False,
) -> gr.Blocks:
    """Build the Gradio UI for running simulations."""
    logger.info(f"Building Gradio app for game '{game_name}'")

    try:
        logger.debug(f"Loading game config for game '{game_name}'")
        game_config_path = get_game_config(game_name)
        game_config = GameConfig.from_yaml(game_config_path)
    except Exception as e:
        gr.Error(f"Failed to load game config: {e}")
        raise e  # terminate build

    try:
        logger.debug("Determining if access gate is required from game config")
        access_gated = not bool(game_config.is_player_allowed(player_id=None))
        logger.debug(f"Access gate required: {access_gated}")
    except Exception as e:
        gr.Error(f"Failed to determine access mode from game config: {e}")
        raise e  # terminate build

    app = gr.Blocks(title="DCS Simulation Engine", theme=Soft())
    with app:
        state = gr.State(
            value=SessionState(
                access_gated=access_gated,
                game_name=game_config.name,
                game_description=game_config.description,
                is_user_turn=False,
                last_seen=0,
            ),
            time_to_live=MAX_TTL_SECONDS,
            delete_callback=_cleanup,  # function to call when state is deleted
        )

        build_header(game_config, banner)
        toggle = build_theme_toggle()
        # gated or un-gated landing page based on game_config access settings
        landing = build_landing(access_gated, show_npc_selector, show_pc_selector)
        consent = None
        if access_gated:
            if game_config.access_settings.consent_form is None:
                raise ValueError(
                    "Game config requires access gating but no form provided"
                )
            consent = build_consent(game_config.access_settings.consent_form)

        # once passed landing (and consent if needed), show main chat interface
        chat = build_chat()

        wire_handlers(state, toggle, landing, chat, consent)

        def on_unload(req: gr.Request) -> None:
            """Handle per-user client disconnect resources (temp dirs, etc)."""
            logger.debug(f"User disconnected: {req.session_hash}")
            _cleanup(state)

        # unload runs when the session ends (tab close, refresh, hard nav away)
        app.unload(on_unload)

    return app
