"""Game setup page UI components."""

from typing import NamedTuple, Optional

import gradio as gr

from dcs_simulation_engine.widget.constants import GAME_MD
from dcs_simulation_engine.widget.helpers import _spacer


class GameSetupUI(NamedTuple):
    """Game setup page UI components."""

    container: gr.Group
    pc_dropdown: Optional[gr.Dropdown]
    npc_dropdown: Optional[gr.Dropdown]
    play_btn: gr.Button


def build_game_setup(
    state: gr.State,
    access_gated: bool,
    show_pc_selector: bool,
    show_npc_selector: bool,
    valid_pcs: list[str] = [],
    valid_npcs: list[str] = [],
) -> GameSetupUI:
    """Build ungated game page UI components."""
    with gr.Group(visible=not access_gated) as group:
        _spacer(8)
        gr.Markdown(GAME_MD)

        # pc input (centered)
        with gr.Group(visible=show_pc_selector):
            with gr.Row():
                with gr.Column(scale=1):
                    pass
                with gr.Column(scale=3):
                    pc_dropdown = gr.Dropdown(
                        label="Player Character",
                        info="Choose your character.",
                        choices=valid_pcs,
                        interactive=True,
                    )
                with gr.Column(scale=1):
                    pass

        _spacer(8)

        # npc input (centered)
        with gr.Group(visible=show_npc_selector):
            with gr.Row():
                with gr.Column(scale=1):
                    pass
                with gr.Column(scale=3):
                    npc_dropdown = gr.Dropdown(
                        label="Non-Player Character",
                        info="Choose the simulator's character.",
                        choices=valid_npcs,
                        interactive=True,
                    )
                with gr.Column(scale=1):
                    pass

        _spacer(8)

        # centered play button
        with gr.Row():
            with gr.Column(scale=1):
                pass
            with gr.Column(scale=0, min_width=220):
                play_btn = gr.Button("Play", variant="primary")
            with gr.Column(scale=1):
                pass

        _spacer(8)

    return GameSetupUI(
        container=group,
        play_btn=play_btn,
        pc_dropdown=pc_dropdown,
        npc_dropdown=npc_dropdown,
    )
