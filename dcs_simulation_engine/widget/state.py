"""App state definition for the Gradio UI."""

from queue import Queue
from threading import Thread
from typing import TypedDict

from dcs_simulation_engine.core.run_manager import RunManager

class AppState(TypedDict, total=False):
    """State stored in gr.State for a single browser session."""

    access_gated: bool
    game_name: str
    game_description: str
    run: RunManager
    queue: Queue[str]
    is_user_turn: bool
    last_seen: int
    _play_thread: Thread
