"""Chat UI components."""
from typing import NamedTuple, Optional
import gradio as gr

class ChatUI(NamedTuple):
    container: gr.Group
    events: gr.Chatbot
    user_box: gr.Textbox
    send_btn: gr.Button
    loader: gr.Markdown
    timer: gr.Timer

def build_chat() -> ChatUI:
    with gr.Group(visible=False) as group:

        # chat message bubbles
        # TODO: I think this has a built-in timer...consider using it instead of custom timer below
        chatbot = gr.Chatbot(
            show_label=False, # no chat label
            group_consecutive_messages=False, # keep back-to-back messages separate
            render_markdown=True, # render markdown in messages
            # show_share_button=True, # shows share button
            show_copy_all_button=True,
            # watermark=True,
            # feedback_options=["👍", "👎", "🚩"],
            # feedback_value=["Like", "Dislike", "Report"],
            # examples=["/help"], # default examples
            autoscroll=True,
            min_height=600, 
            type="messages"
            )

        # loader indicator for waiting simulator response
        loader = gr.Markdown("⏳ *Thinking...*", visible=False)
        with gr.Row(equal_height=True):
            with gr.Column(scale=8):
                user_box = gr.Textbox(
                    show_label=False,
                    placeholder="What do you do next?",
                )
            with gr.Column(scale=1):
                send_btn = gr.Button("Send")

        # Polling timer to check for new messages from simulation engine
        timer = gr.Timer(2, active=True)
    return ChatUI(
        container=group,
        events=chatbot,
        user_box=user_box,
        send_btn=send_btn,
        loader=loader,
        timer=timer
    )