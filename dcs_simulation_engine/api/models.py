"""Pydantic models (request/response schemas) for the API."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

# ---------------------------
# Run creation & discovery
# ---------------------------


class CreateRunRequest(BaseModel):
    """Create a new run using a game config reference."""

    game: str = Field(
        ..., description="Game name or path resolvable by get_game_config"
    )
    source: str = Field("api", description="Origin tag used in run naming")
    pc_choice: Optional[str] = Field(
        None, description="Player character HID (optional)"
    )
    npc_choice: Optional[str] = Field(None, description="NPC HID (optional)")
    access_key: Optional[str] = Field(
        None, description="Access key used to resolve player_id"
    )
    player_id: Optional[str] = Field(
        None, description="Explicit Player ID (overrides access_key)"
    )


class CharacterSummary(BaseModel):
    """Lightweight character summary for UI."""

    hid: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None


class RunMeta(BaseModel):
    """Common run metadata that changes over time."""

    name: str = Field(..., description="Run identifier (RunManager.name)")
    turns: int = Field(..., description="Total turns so far")
    runtime_seconds: int = Field(..., description="Wall time in seconds")
    runtime_string: str = Field(..., description="HH:MM:SS")
    exited: bool = Field(..., description="True if the run has exited")
    exit_reason: str = Field("", description="Reason if exited")
    saved: bool = Field(..., description="True if run data has been persisted")
    output_path: Optional[str] = Field(None, description="Filesystem/DB path if saved")


class CreateRunResponse(BaseModel):
    """Returned after creating a run."""

    run_id: str = Field(..., description="Alias for RunManager.name")
    game_name: str
    pc: CharacterSummary
    npc: CharacterSummary
    meta: RunMeta


# ---------------------------
# Stepping & state
# ---------------------------


class StepRequest(BaseModel):
    """Advance the simulation one step.

    Accepts either:
      - a string (user text or slash-command)
      - a mapping (structured event payload)
    """

    user_input: Optional[Union[str, Dict[str, Any]]] = Field(
        None, description="Text or mapping to place into state['event_draft']"
    )


class StateResponse(BaseModel):
    """Snapshot of state with run metadata."""

    state: Dict[str, Any]
    meta: RunMeta


class StepResponse(StateResponse):
    """Alias for clarity; same shape as StateResponse."""

    pass


# ---------------------------
# Play (batch inputs)
# ---------------------------


class PlayRequest(BaseModel):
    """Run play() with a finite list of inputs; server will iterate."""

    inputs: List[str] = Field(..., description="Sequential inputs to feed")
    max_steps: Optional[int] = Field(None, description="Optional safety cap")


class PlayResponse(BaseModel):
    """Final state after play()."""

    final_state: Dict[str, Any]
    meta: RunMeta


# ---------------------------
# Save & Exit
# ---------------------------


class SaveRequest(BaseModel):
    """Trigger a save to filesystem or DB."""

    output_dir: Optional[str] = Field(
        None,
        description="Directory or path hint; if file path, that exact path is used",
    )


class SaveResponse(BaseModel):
    """Details about persisted output."""

    saved: bool = True
    output_path: Optional[str] = Field(None, description="Where the run was saved")
    # Back-compat with older clients that expect a list of files
    files: List[str] = Field(default_factory=list)


# ---------------------------
# Misc
# ---------------------------


class Message(BaseModel):
    """Optional normalized transcript message (unused by RunManager)."""

    role: str
    content: str
