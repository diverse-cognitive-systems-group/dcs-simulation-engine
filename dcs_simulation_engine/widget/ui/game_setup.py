"""Game setup page UI components."""

from typing import NamedTuple

import gradio as gr

from dcs_simulation_engine.widget.helpers import spacer


class GameSetupUI(NamedTuple):
    """Game setup page UI components."""

    container: gr.Group
    pc_dropdown: gr.Dropdown
    npc_dropdown: gr.Dropdown
    play_btn: gr.Button


def build_game_setup(
    access_gated: bool,
    game_name: str,
    game_description: str,
    valid_pcs: list[str] = [],
    valid_npcs: list[str] = [],
) -> GameSetupUI:
    """Build ungated game page UI components."""
    with gr.Group(visible=not access_gated) as group:
        with gr.Row():
            with gr.Column():
                lower_desc = game_description[0].lower() + game_description[1:]
                gr.Markdown(
                    f"""
                    # Welcome
                    
                    {game_name.capitalize()} is {lower_desc}
                    """
                )
                spacer(12)
                gr.Markdown("## Game Setup")
                if not valid_pcs and not valid_npcs:
                    gr.Markdown(
                        """
                        *This game is already set up for you!* 
                        
                        Click **Play** when you are ready to begin.
                        """
                    )
                    pc_dropdown = gr.Dropdown(visible=False)
                    npc_dropdown = gr.Dropdown(visible=False)
                else:
                    gr.Markdown(
                        """
                        This game is configured to allow you customize the following:

                        ### Character Selection
                        """
                    )
                    spacer(4)
                    with gr.Group(visible=bool(valid_pcs)):
                        with gr.Row():
                            pc_dropdown = gr.Dropdown(
                                label="Player Character",
                                info="Choose the character you will be playing as.",
                                choices=valid_pcs,
                                interactive=True,
                            )
                    with gr.Group(visible=bool(valid_npcs)):
                        with gr.Row():
                            npc_dropdown = gr.Dropdown(
                                label="Non-Player Character",
                                info="Choose the character the simulator will roleplay.",
                                choices=valid_npcs,
                                interactive=True,
                            )
                spacer(8)
                play_btn = gr.Button("Play", variant="primary")

    return GameSetupUI(
        container=group,
        play_btn=play_btn,
        pc_dropdown=pc_dropdown,
        npc_dropdown=npc_dropdown,
    )
