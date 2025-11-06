"""App state definition for the Gradio UI."""

from queue import Queue
from threading import Thread
from typing import TypedDict

from dcs_simulation_engine.core.run_manager import RunManager


class SessionState(TypedDict, total=False):
    """Custom state for the Gradio app."""

    run: RunManager
    access_gated: bool
    game_name: str
    game_description: str
    queue: Queue[str]
    is_user_turn: bool
    last_seen: int
    last_special_seen: tuple[str, str]
    _play_thread: Thread
