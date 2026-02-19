"""Consent form UI components."""

from __future__ import annotations

from typing import Any, Dict, List, NamedTuple

import gradio as gr

from dcs_simulation_engine.widget.helpers import make_component, spacer


class FormUI(NamedTuple):
    """Holds references to form UI components."""

    form_group: gr.Group
    fields: List[gr.Component]  # Note: list order preserves question order in config
    submit_btn: gr.Button
    token_group: gr.Group
    token_text: gr.Textbox
    token_continue_btn: gr.Button


def build_form(access_gated: bool, form_config: Dict[str, Any]) -> FormUI:
    """Builds form UI components.

    Builds two exclusive views:
      1) Form (hidden by default)
      2) One-time token display (hidden by default)
    """
    if not access_gated:
        # return empty components
        return FormUI(
            form_group=gr.Group(visible=False),
            fields=[],
            submit_btn=gr.Button(visible=False),
            token_group=gr.Group(visible=False),
            token_text=gr.Textbox(visible=False),
            token_continue_btn=gr.Button(visible=False),
        )

    # Build form
    with gr.Group(visible=False) as form_group:
        with gr.Row():
            with gr.Column():
                pre_md = form_config.get("preamble") or "**Participation Form**"
                gr.Markdown(pre_md)
                spacer(8)

                fields: List[gr.Component] = []
                for q in form_config.get("questions", []):
                    comp = make_component(q)
                    fields.append(comp)
                spacer(8)
                with gr.Row():
                    submit_btn = gr.Button("Submit", variant="primary")

    # Built one-time token display
    with gr.Group(visible=False) as token_group:
        with gr.Row():
            with gr.Column():
                gr.Markdown(
                    """
                    ### Your Access Token
                    *This token will only be shown once. We do not it and you 
                    will not able able to see it again so please store it 
                    somewhere safe. If you lose it, you will need to 
                    generate a new one.*
                    """
                )
                spacer(8)
                token_text = gr.Textbox(
                    interactive=False,
                    lines=1,
                    show_label=False,
                    container=False,
                    buttons=["copy"],
                )
                spacer(8)
                with gr.Row():
                    token_continue_btn = gr.Button(
                        "I have saved my token.", variant="primary"
                    )

    return FormUI(
        form_group=form_group,
        fields=fields,
        submit_btn=submit_btn,
        token_group=token_group,
        token_text=token_text,
        token_continue_btn=token_continue_btn,
    )
