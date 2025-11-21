"""Wiring of event handlers to widget components."""

import gradio as gr

from dcs_simulation_engine.widget.handlers import (
    handle_chat_feedback,
    on_form_submit,
    on_gate_continue,
    setup_simulation,
)
from dcs_simulation_engine.widget.ui.chat import ChatUI
from dcs_simulation_engine.widget.ui.form import FormUI
from dcs_simulation_engine.widget.ui.game_setup import GameSetupUI
from dcs_simulation_engine.widget.ui.gate import GateUI


def wire_handlers(
    state: gr.State,
    gate: GateUI,
    form: FormUI,
    game_setup: GameSetupUI,
    chat: ChatUI,
) -> None:
    """Wire event handlers to widget components."""
    # Note: Chat handlers are wired in ChatUI build function as args of gr.ChatInterface

    # Wire game setup
    setup_sim_evt = game_setup.play_btn.click(
        # show chat view
        fn=lambda: [
            gr.update(visible=False),  # hide game setup
            gr.update(visible=True),  # show chat container
            gr.update(visible=False),  # disable chat textbox initially
        ],
        inputs=[],
        outputs=[
            game_setup.container,
            chat.container,
            chat.interface.textbox,
        ],
    ).success(
        fn=setup_simulation,
        inputs=[state, game_setup.pc_dropdown, game_setup.npc_dropdown],
        outputs=[state, chat.interface.chatbot_value],
    )

    setup_sim_evt.success(
        fn=lambda: gr.update(visible=True),  # renable chat textbox
        inputs=[],
        outputs=[chat.interface.textbox],
    )
    setup_sim_evt.failure(
        fn=lambda: gr.update(elem_classes="frozen"),
        inputs=[],
        outputs=[chat.container],
    )

    # Wire chat feedback
    chat.interface.chatbot.like(
        fn=handle_chat_feedback,
        inputs=[state],
        outputs=[],
    )

    # Wire gate page if present
    gate.continue_btn.click(
        fn=on_gate_continue,
        inputs=[
            state,
            gate.token_box,  # token value input
        ],
        outputs=[
            state,
            gate.container,
            game_setup.container,
            game_setup.no_customization_group,
            game_setup.customization_group,
            game_setup.pc_dropdown_group,
            game_setup.npc_dropdown_group,
            game_setup.pc_dropdown,
            game_setup.npc_dropdown,
            gate.token_box,
            gate.token_error_box,
        ],
    ).failure(
        fn=lambda: gr.update(elem_classes="frozen"),
        inputs=[],
        outputs=[gate.container],
    )

    # Wire gate generate token button
    gate.generate_token_btn.click(
        fn=lambda: [
            gr.update(visible=False),  # hide gate
            gr.update(visible=True),  # show consent
            gr.update(value=""),  # clear token box
            gr.update(visible=False, value=""),  # clear token error box
        ],
        inputs=[],
        outputs=[
            gate.container,
            form.form_group,
            gate.token_box,
            gate.token_error_box,
        ],
    )

    # Wire consent page handlers
    form.submit_btn.click(
        fn=on_form_submit,
        inputs=[
            state,
            *form.fields,  # unpack component list to individual inputs
        ],
        outputs=[
            state,
            form.form_group,
            form.token_group,
            form.token_text,
            gate.token_error_box,
        ],
    ).failure(
        fn=lambda: gr.update(elem_classes="frozen"),
        inputs=[],
        outputs=[form.form_group],
    )

    form.token_continue_btn.click(
        fn=lambda: [],  # dummy function
        inputs=None,
        outputs=[],
        js="window.location.reload()",  # reload the entire app to avoid data leakage
    )
