"""Chat UI components."""

from typing import NamedTuple

import gradio as gr

from dcs_simulation_engine.widget.handlers import (
    process_new_user_message,
    validate_user_input,
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
        </style>
        """
        )

        chatbot = gr.Chatbot(
            placeholder="""<strong>Loading simulation environment..</strong>
            <br>This might take a minute...☕""",
            type="messages",
            show_copy_all_button=True,
        )

        # TODO: we didn't end up using "every"...consider if we need it.

        chatinterface = gr.ChatInterface(
            fn=process_new_user_message,  # takes message, history
            additional_inputs=[state],  # add state to inputs via wiring
            # additional_outputs=[state],  # add state to outputs via wiring
            multimodal=False,  # only text input
            type="messages",  # pass history (list of dics - openai-style role/content
            chatbot=chatbot,
            # textbox=gr.Textbox(),
            editable=False,  # users cannot edit past messages
            # title="Simulating",
            # description="A game with ...",
            flagging_mode="manual",  # users will see a button to flag
            flagging_options=["Dislike", "Other"],
            flagging_dir="flags",  # path to directory where flagged data is stored
            analytics_enabled=True,  # enable gradio analytics
            autofocus=True,  # focus on textbox on load
            autoscroll=True,  # scroll to latest message on update
            stop_btn=False,  # don't show stop button while waiting for response
            concurrency_limit=1,  # limit to 1 user at a time
            show_progress="full",  # show progress while waiting for response
            fill_height=True,  # fill height of container
            fill_width=True,  # fill width of container
            validator=validate_user_input,  # input validation function
        )
        chatinterface.textbox.placeholder = "What do you do next?"
        chatinterface.chatbot.show_label = False  # no chat label
        chatinterface.chatbot.show_copy_all_button = True
        chatinterface.chatbot.group_consecutive_messages = False  # separate back2back
        chatinterface.chatbot.render_markdown = True  # render markdown in messages

    return ChatUI(container=group, interface=chatinterface)
