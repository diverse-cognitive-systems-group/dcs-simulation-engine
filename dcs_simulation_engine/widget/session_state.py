"""App state definition for the Gradio UI."""

from queue import Queue
from threading import Thread
from typing import TypedDict

from dcs_simulation_engine.core.game_config import (
    GameConfig,
)
from dcs_simulation_engine.core.session_manager import (
    SessionManager,
)


class SessionState(TypedDict, total=False):
    """Custom state for the Gradio app."""

    run: SessionManager
    game_config: GameConfig

    is_user_turn: bool  # TODO: should be accessible in run.state

    # Convenience fields (may also exist in game_config and/or run once initialized)
    access_gated: bool
    player_id: str | None
    pc_choice: str | None
    npc_choice: str | None
    valid_pcs: list[str]
    valid_npcs: list[str]
    initial_history: list[dict[str, str]]

    queue: Queue[str]
    last_seen: int
    last_special_seen: tuple[str, str]
    _play_thread: Thread
