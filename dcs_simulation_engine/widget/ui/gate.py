"""Gate UI components."""

from typing import NamedTuple

import gradio as gr
from dcs_simulation_engine.widget.constants import GATE_MD
from dcs_simulation_engine.widget.helpers import spacer


class GateUI(NamedTuple):
    """Gate page UI components."""

    container: gr.Group
    continue_btn: gr.Button
    token_box: gr.Textbox
    token_error_box: gr.Markdown
    generate_token_btn: gr.Button


def build_gate(access_gated: bool) -> GateUI:
    """Build gate UI components."""
    if not access_gated:
        # return empty components
        return GateUI(
            container=gr.Group(visible=False),
            continue_btn=gr.Button(visible=False),
            token_box=gr.Textbox(visible=False),
            token_error_box=gr.Markdown(visible=False),
            generate_token_btn=gr.Button(visible=False),
        )

    with gr.Group(visible=access_gated) as group:
        # intro
        gr.Markdown(GATE_MD)
        spacer(12)

        # token input (centered)
        with gr.Row():
            with gr.Column(scale=1):
                pass
            with gr.Column(scale=3):
                token_box = gr.Textbox(
                    show_label=False,
                    placeholder="ak-xxxx-xxxx-xxxx",
                    lines=1,
                    type="password",
                    container=False,
                )
                token_error_box = gr.Markdown(
                    value="  Invalid key. Try again or generate a new one.",
                    visible=False,
                    elem_id="error",
                )
            with gr.Column(scale=1):
                pass

        spacer(8)

        # primary action (centered)
        with gr.Row():
            with gr.Column(scale=1):
                pass
            with gr.Column(scale=0, min_width=220):
                continue_btn = gr.Button("Continue", variant="primary")
            with gr.Column(scale=1):
                pass

        spacer(8)
        gr.Markdown("<div style='text-align:center'>OR</div>")
        spacer(8)

        # generate new token (centered)
        with gr.Row():
            with gr.Column(scale=1):
                pass
            with gr.Column(scale=0, min_width=280):
                gen = gr.Button("Generate New Access Token", variant="secondary")
            with gr.Column(scale=1):
                pass
        spacer(8)

    return GateUI(
        container=group,
        continue_btn=continue_btn,
        token_box=token_box,
        token_error_box=token_error_box,
        generate_token_btn=gen,
    )
