"""Chat UI components."""

from typing import NamedTuple

import gradio as gr

from dcs_simulation_engine.widget.handlers import (
    process_new_user_chat_message,
    validate_chat_input,
)


class ChatUI(NamedTuple):
    """Named tuple for chat UI components."""

    container: gr.Group
    interface: gr.ChatInterface


def build_chat(state: gr.State, access_gated: bool) -> ChatUI:
    """Build chat UI components."""
    with gr.Group(visible=False) as group:
        # Hide unwanted buttons (clear, retry, undo)
        # Note: this is a bit hacky but Gradio doesn't
        # provide direct API to hide these buttons and
        # injecting css using the css arg of gr.ChatInterface
        # didn't work.
        gr.HTML(
            """
        <style>
        button[aria-label="Clear"] {
            display: none !important;
        }
        button[aria-label="Retry"] {
            display: none !important;
        }
        button[aria-label="Undo"] {
            display: none !important;
        }
        /* Fix flagging buttons overlapping chat messages */
        /* Target the flag button container within chat messages */
        .message-buttons-bot, .message-buttons-user {
            position: relative !important;
            display: block !important;
            clear: both !important;
            margin-top: 8px !important;
        }
        /* Ensure flagging options don't overlap message content */
        .chatbot .message-wrap .message {
            position: relative !important;
            overflow: visible !important;
        }
        .chatbot .message-wrap .message .prose {
            position: relative !important;
            z-index: 1 !important;
        }
        /* Style the flag buttons to appear below message text */
        .chatbot button.flag {
            position: relative !important;
            margin-top: 4px !important;
        }
        </style>
        """
        )

        chatbot = gr.Chatbot(
            placeholder="""<strong>Loading simulation environment.</strong>
            <br>This might take a minute...☕""",
        )

        chatinterface = gr.ChatInterface(
            fn=process_new_user_chat_message,  # takes message, history
            additional_inputs=[state],  # add state to inputs via wiring
            # TODO: add additional outputs that freeze group on exception
            # additional_outputs=[group],  # add state to outputs via wiring
            multimodal=False,  # only text input
            chatbot=chatbot,
            # textbox=gr.Textbox(),
            editable=False,  # users cannot edit past messages
            # title="Simulating",
            # description="A game with ...",
            # NOTE: Using Chatbot's feedback_options instead of ChatInterface flagging
            # as the latter has rendering issues in Gradio 6.x
            analytics_enabled=True,  # enable gradio analytics
            autofocus=True,  # focus on textbox on load
            autoscroll=True,  # scroll to latest message on update
            stop_btn=False,  # don't show stop button while waiting for response
            concurrency_limit=1,  # limit to 1 user at a time
            show_progress="full",  # show progress while waiting for response
            fill_height=True,  # fill height of container
            fill_width=True,  # fill width of container
            validator=validate_chat_input,  # input validation function
        )
        chatinterface.textbox.placeholder = "What do you do next?"
        chatinterface.chatbot.show_label = False  # no chat label
        chatinterface.chatbot.group_consecutive_messages = False  # separate back2back
        chatinterface.chatbot.render_markdown = True  # render markdown in messages

    return ChatUI(container=group, interface=chatinterface)
