"""Game setup page UI components."""

import random
from typing import NamedTuple

import gradio as gr

from dcs_simulation_engine.widget.helpers import spacer


class GameSetupUI(NamedTuple):
    """Game setup page UI components."""

    container: gr.Group
    no_customization_group: gr.Group
    customization_group: gr.Group
    pc_dropdown_group: gr.Group
    npc_dropdown_group: gr.Group
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
                    
                    '{game_name.capitalize()}' is {lower_desc}
                    """
                )
                spacer(12)
                gr.Markdown("## Game Setup")
                with gr.Group(
                    visible=not bool(valid_pcs or valid_npcs)
                ) as no_customization_group:
                    gr.Markdown(
                        """
                        *This game is already set up for you!* 
                        
                        Click **Play** when you are ready to begin.
                        """
                    )
                    pc_dropdown = gr.Dropdown(visible=False)
                    npc_dropdown = gr.Dropdown(visible=False)
                with gr.Group(
                    visible=bool(valid_pcs or valid_npcs)
                ) as customization_group:
                    gr.Markdown(
                        """
                        This game is configured to allow you customize the following:

                        ### Character Selection
                        """
                    )
                    spacer(4)
                    with gr.Group(visible=bool(valid_pcs)) as pc_dropdown_group:
                        with gr.Row():
                            pc_dropdown = gr.Dropdown(
                                label="Player Character",
                                info="Choose the character you will be playing as.",
                                choices=valid_pcs,
                                value=(
                                    random.choice(valid_pcs)[1] if valid_pcs else None
                                ),
                                interactive=True,
                            )
                    with gr.Group(visible=bool(valid_npcs)) as npc_dropdown_group:
                        with gr.Row():
                            npc_dropdown = gr.Dropdown(
                                label="Non-Player Character",
                                info=(
                                    "Choose the character the "
                                    "simulator will roleplay."
                                ),
                                choices=valid_npcs,
                                value=(
                                    random.choice(valid_npcs)[1] if valid_npcs else None
                                ),
                                interactive=True,
                            )
                spacer(8)
                play_btn = gr.Button("Play", variant="primary")

    return GameSetupUI(
        container=group,
        no_customization_group=no_customization_group,
        customization_group=customization_group,
        pc_dropdown_group=pc_dropdown_group,
        npc_dropdown_group=npc_dropdown_group,
        play_btn=play_btn,
        pc_dropdown=pc_dropdown,
        npc_dropdown=npc_dropdown,
    )
