"""Chat UI components."""
from typing import NamedTuple, Optional
import gradio as gr

class ChatUI(NamedTuple):
    container: gr.Group
    events: gr.Chatbot
    user_box: gr.Textbox
    send_btn: gr.Button
    timer: gr.Timer

def build_chat() -> ChatUI:
    with gr.Group(visible=False) as group:
        # Chat (messages API)
        chat = gr.Chatbot(label="Chat", height=400, type="messages")
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
        events=chat,
        user_box=user_box,
        send_btn=send_btn,
        timer=timer
    )