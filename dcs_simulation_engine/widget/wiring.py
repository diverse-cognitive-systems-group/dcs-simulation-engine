"""Wiring of event handlers to widget components."""
import gradio as gr
from dcs_simulation_engine.widget.handlers import on_play, on_generate_token, on_consent_back, on_consent_submit, on_token_continue, on_send, poll_fn
from dcs_simulation_engine.widget.state import AppState
from dcs_simulation_engine.widget.ui.theme_toggle import ThemeToggleUI
from dcs_simulation_engine.widget.ui.landing import LandingUI
from dcs_simulation_engine.widget.ui.consent import ConsentUI
from dcs_simulation_engine.widget.ui.chat import ChatUI

def wire_handlers(state: AppState, toggle: ThemeToggleUI, landing: LandingUI, consent: ConsentUI, chat: ChatUI):

    # Wire theme toggle handler
    toggle.toggle_btn.click(
        fn=None,
        js="""
            () => {
              const url = new URL(window.location);
              const cur = url.searchParams.get('__theme') || 'system';
              const next = cur === 'dark' ? 'light' : 'dark';
              url.searchParams.set('__theme', next);
              window.location.replace(url);
            }
        """,
    )
    
    # Wire landing page handlers
    if landing.gated_play_btn:
        landing.gated_play_btn.click(
            fn=on_play,
            inputs=[state, landing.token_box],
            outputs=[state, landing.container, chat.container, chat.user_box, chat.send_btn, chat.loader, landing.token_box, landing.token_error_box],
        )

    if landing.ungated_play_btn:
        landing.ungated_play_btn.click(
            fn=on_play,
            inputs=[state],
            outputs=[state, landing.container, chat.container, chat.user_box, chat.send_btn, chat.loader],
        )

    # Wire generate token button if it exists (gated only)
    if landing.generate_token_btn:
        landing.generate_token_btn.click(
            fn=on_generate_token,
            inputs=[state],
            outputs=[state, landing.container, consent.form_group],
        )

    # Wire consent page handlers
    if consent:
        consent.back_btn.click(
            fn=on_consent_back,
            inputs=[state],
            outputs=[state, landing.container, consent.form_group],
        )
        consent.submit_btn.click(
            fn=on_consent_submit,
            inputs=[state, gr.State(list(consent.fields.keys())), *consent.fields.values()],
            outputs=[state, consent.form_group, consent.token_group, consent.token_text],
        )
        consent.token_continue_btn.click(
            fn=on_token_continue,
            inputs=[state],
            outputs=[state, landing.container, consent.token_group, consent.form_group, consent.token_text],
        )

    # Wire chat page handlers
    chat.send_btn.click(
        # wire send button
        fn=on_send, 
        inputs=[chat.user_box, chat.events, state], 
        outputs=[chat.events, chat.user_box, state]
    )

    chat.user_box.submit(
        # wire enter key in user input box
        fn=on_send, 
        inputs=[chat.user_box, chat.events, state],
        outputs=[chat.events, chat.user_box, state])
    
    chat.timer.tick(
        # wire polling time for new events/messages (and to start)
        fn=poll_fn, 
        inputs=[chat.events, state], 
        outputs=[chat.events, state, chat.timer, chat.user_box, chat.send_btn, chat.loader])