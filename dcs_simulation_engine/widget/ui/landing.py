"""Landing page UI components."""
from typing import NamedTuple, Optional
import gradio as gr

from dcs_simulation_engine.widget.constants import GATED_MD, UNGATED_MD
from dcs_simulation_engine.core.game_config import GameConfig

class LandingUI(NamedTuple):
    container: gr.Group
    gated_play_btn: gr.Button
    ungated_play_btn: gr.Button
    token_box: Optional[gr.Textbox] # None for ungated
    token_error_box: Optional[gr.Markdown] # None for ungated
    generate_token_btn: Optional[gr.Button] # None for ungated

def _spacer(h=24):
    gr.HTML(f"<div style='height:{h}px'></div>")

def build_gated() -> LandingUI:
    with gr.Group() as group:
        # intro
        gr.Markdown(GATED_MD)  # keep your long Markdown string in a constant
        _spacer(12)

        # token input (centered)
        with gr.Row():
            with gr.Column(scale=1): ...
            with gr.Column(scale=3):
                token_box = gr.Textbox(
                    show_label=False,
                    placeholder="ak-xxxx-xxxx-xxxx",
                    lines=1,
                    type="password",
                )
                token_error_box = gr.Markdown(value="  Invalid key. Try again or generate a new one.", visible=False, elem_id="error")
            with gr.Column(scale=1): ...

        _spacer(8)

        # primary action (centered)
        with gr.Row():
            with gr.Column(scale=1): ...
            with gr.Column(scale=0, min_width=220):
                gated_play_btn = gr.Button("Play", variant="primary")
            with gr.Column(scale=1): ...

        _spacer(8)
        gr.Markdown("<div style='text-align:center'>OR</div>")
        _spacer(8)

        # generate new token (centered)
        with gr.Row():
            with gr.Column(scale=1): ...
            with gr.Column(scale=0, min_width=280):
                gen = gr.Button("Generate New Access Token", variant="secondary")
            with gr.Column(scale=1): ...
        _spacer(8)

    return LandingUI(
        container=group,
        gated_play_btn=gated_play_btn,
        ungated_play_btn=None,
        token_box=token_box,
        token_error_box=token_error_box,
        generate_token_btn=gen,
    )

def build_ungated() -> LandingUI:
    with gr.Group() as group:
        _spacer(12)
        gr.Markdown(UNGATED_MD)
        with gr.Row():
            with gr.Column(scale=1): ...
            with gr.Column(scale=0, min_width=220):
                ungated_play_btn = gr.Button("Play", variant="primary")
            with gr.Column(scale=1): ...

        _spacer(12)
    return LandingUI(container=group, gated_play_btn=None, ungated_play_btn=ungated_play_btn, token_box=None, token_error_box=None, generate_token_btn=None)

def build_landing(access_gated: bool) -> LandingUI:
    return build_gated() if access_gated else build_ungated()