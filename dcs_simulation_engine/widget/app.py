"""Gradio app construction for the simulation engine.

Adds a centered title and an Instructions panel derived from the loaded
simulation's characters (A/B) and graph, similar to the CLI UI.
"""

from __future__ import annotations

import time
from typing import Tuple

import gradio as gr
from gradio.themes import Soft

from dcs_simulation_engine.widget.state import AppState

from dcs_simulation_engine.core.game_config import GameConfig
from dcs_simulation_engine.helpers.game_helpers import get_game_config
from loguru import logger

from dcs_simulation_engine.widget.ui.chat import build_chat
from dcs_simulation_engine.widget.ui.header import build_header
from dcs_simulation_engine.widget.ui.theme_toggle import build_theme_toggle
from dcs_simulation_engine.widget.ui.landing import build_landing
from dcs_simulation_engine.widget.ui.consent import build_consent
from dcs_simulation_engine.widget.wiring import wire_handlers


def build_app(game_name: str = "explore") -> gr.Blocks:
    """Build the Gradio UI for running simulations."""
    logger.info(f"Building Gradio app for game '{game_name}'")

    # try loading game config based on provided game
    try:
        game_config_path = get_game_config(game_name)
        game_config = GameConfig.from_yaml(game_config_path)
    except Exception as e:
        gr.Error(f"Failed to load game config: {e}")
        raise e
    
    # try to determine access mode from game config
    try: 
        access_gated = not bool(game_config.is_player_allowed(player_id=None))
        logger.debug(f"Access gate required: {access_gated}")
    except Exception as e:
        gr.Error(f"Failed to determine access mode from game config: {e}")
        raise e

    with gr.Blocks(title="DCS Simulation Engine", theme=Soft()) as app:
        state = gr.State(AppState())
        state.value["run"] = None
        state.value["access_gated"] = access_gated
        state.value["game_name"] = game_config.name
        state.value["game_description"] = game_config.description

        build_header(game_config)
        toggle = build_theme_toggle()
        # gated or un-gated landing page based on game_config access settings
        landing = build_landing(access_gated)
        consent = None
        if access_gated:
            consent = build_consent(game_config.access_settings.consent_form)
        
        # once passed landing (and consent if needed), show main chat interface
        chat = build_chat()

        wire_handlers(state, toggle, landing, consent, chat)

    return app


def _enter_play(
    state: AppState,
) -> Tuple[AppState, gr.update, gr.update, gr.update]:
    state["access_token"] = None

    # hide gates, show main
    return (
        state,
        gr.update(visible=False),  # gate
        gr.update(visible=True),  # main
    )

def _create_access_token() -> str:
    """Create a new access token."""
    # display consent form

def _get_player_id_from_token(
    token: str, state: AppState
) -> Tuple[AppState, gr.update, gr.update, gr.update, gr.update]:
    state["access_token"] = token

    # TODO: try to get player_id from access token

    # hide gates, show main
    return (
        state,
        gr.update(visible=False),  # gate
        gr.update(visible=True),  # main
        gr.update(value=""),  # clear gate message
    )