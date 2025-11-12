"""Wiring of event handlers to widget components."""

import gradio as gr

from dcs_simulation_engine.widget.handlers import (
    on_consent_submit,
    on_gate_continue,
    on_generate_token,
    on_token_continue,
    setup_simulation,
    show_chat_view,
)
from dcs_simulation_engine.widget.ui.chat import ChatUI
from dcs_simulation_engine.widget.ui.consent import ConsentUI
from dcs_simulation_engine.widget.ui.game_setup import GameSetupUI
from dcs_simulation_engine.widget.ui.gate import GateUI


def wire_handlers(
    state: gr.State,
    gate: GateUI,
    consent: ConsentUI,
    game_setup: GameSetupUI,
    chat: ChatUI,
) -> None:
    """Wire event handlers to widget components."""
    # Note: Chat handlers are wired in ChatUI build function as args of gr.ChatInterface

    # Wire play
    game_setup.play_btn.click(
        fn=show_chat_view,
        inputs=[],
        outputs=[game_setup.container, chat.container, chat.interface.textbox],
    ).then(
        fn=setup_simulation,
        inputs=[state],
        outputs=[state, chat.interface.chatbot],
    ).then(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[chat.interface.textbox],
    )

    # Wire gate page if present
    if gate:
        # Wire gate continue button
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
                game_setup.pc_dropdown,
                game_setup.npc_dropdown,
                gate.token_box,
                gate.token_error_box,
            ],
        )

        # Wire gate generate token button
        if consent:
            gate.generate_token_btn.click(
                fn=on_generate_token,
                inputs=[state],
                outputs=[
                    state,
                    gate.container,
                    consent.form_group,
                    gate.token_box,
                    gate.token_error_box,
                ],
            )

            # Wire consent page handlers
            consent.submit_btn.click(
                fn=on_consent_submit,
                inputs=[
                    state,
                    gr.State(list(consent.fields.keys())),
                    *consent.fields.values(),
                ],
                outputs=[
                    state,
                    consent.form_group,
                    consent.token_group,
                    consent.token_text,
                    gate.token_error_box,
                ],
                # show_progress="full",
            )
            consent.token_continue_btn.click(
                fn=on_token_continue,
                inputs=[state],
                outputs=[
                    state,
                    gate.container,
                    consent.token_group,
                    consent.form_group,
                    consent.token_text,
                ],
            )
