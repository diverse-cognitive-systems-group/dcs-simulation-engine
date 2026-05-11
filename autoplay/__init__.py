"""Automatic API player client for model-driven gameplay."""

from autoplay.driver import PlayerHarness
from autoplay.players import (
    ApiPlayer,
    OpenRouterPlayer,
    PythonModulePlayer,
    ScriptedPlayer,
    player_from_spec,
)
from autoplay.types import (
    AssignmentResult,
    HarnessResult,
    PlayerContext,
    PlayerTurn,
)

__all__ = [
    "ApiPlayer",
    "AssignmentResult",
    "HarnessResult",
    "OpenRouterPlayer",
    "PlayerHarness",
    "PlayerContext",
    "PlayerTurn",
    "PythonModulePlayer",
    "ScriptedPlayer",
    "player_from_spec",
]
