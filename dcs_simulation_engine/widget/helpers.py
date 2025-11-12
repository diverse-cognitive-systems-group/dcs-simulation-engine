import gradio as gr


def _spacer(h: int = 24) -> None:
    """Create a vertical spacer of given height."""
    gr.HTML(f"<div style='height:{h}px'></div>")
