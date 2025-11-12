"""Header UI for the DCS Simulation Engine widget."""

from typing import NamedTuple

import gradio as gr

from dcs_simulation_engine.core.game_config import GameConfig


class HeaderUI(NamedTuple):
    """Named tuple for header UI components."""

    pass  # no fields


def build_header(game_config: GameConfig, banner: str | None = None) -> HeaderUI:
    """Build the header UI component."""
    if banner:
        gr.HTML(f'<div style="text-align:center" id="banner">{banner} </div>')
    gr.Markdown(
        f"""
        <div style='text-align:center'>
          <h1 style='margin-bottom:0'>{game_config.name.title()}</h1>
          <p style='margin-top:6px;color:#666'>A DCS Simulation Engine Game</p>
        </div>
        """
    )
    return HeaderUI()
