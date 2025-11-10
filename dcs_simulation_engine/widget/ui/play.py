"""Play page UI components."""

from typing import NamedTuple, Optional

import gradio as gr

from dcs_simulation_engine.widget.constants import PLAY_MD


class PlayUI(NamedTuple):
    """Play page UI components."""

    container: gr.Group
    pc_dropdown: Optional[gr.Dropdown]
    npc_dropdown: Optional[gr.Dropdown]
    play_btn: gr.Button


def _spacer(h: int = 24) -> None:
    """Create a vertical spacer of given height."""
    gr.HTML(f"<div style='height:{h}px'></div>")


def build_play(
    show_pc_selector: bool,
    show_npc_selector: bool,
    access_gated: bool,
    valid_pcs: list[str] = [],
    valid_npcs: list[str] = [],
) -> PlayUI:
    """Build ungated landing page UI components."""
    with gr.Group(visible=not access_gated) as group:
        _spacer(8)
        gr.Markdown(PLAY_MD)

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

    return PlayUI(
        container=group,
        play_btn=play_btn,
        pc_dropdown=pc_dropdown,
        npc_dropdown=npc_dropdown,
    )
