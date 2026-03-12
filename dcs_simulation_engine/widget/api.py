"""Gradio API functions for programmatic access to the simulation engine.

This module provides API functions that can be mounted on a Gradio Blocks
instance using the `api_name` parameter. These functions mirror the
functionality previously provided by the FastAPI endpoints.

All functions return dicts that Gradio serializes to JSON automatically.
"""



from typing import Any, Dict, List, Mapping, Optional

from loguru import logger

from dcs_simulation_engine.core.session_manager import SessionManager
from dcs_simulation_engine.widget.services import get_registry


def _build_meta(run: SessionManager) -> Dict[str, Any]:
    """Build metadata dict from a SessionManager."""
    return {
        "name": run.name,
        "turns": run.turns,
        "runtime_seconds": run.runtime_seconds,
        "exited": run.exited,
        "exit_reason": run.exit_reason,
        "saved": run._saved,
    }


def _build_character_summary(obj: Any) -> Dict[str, Any]:
    """Build character summary dict from various object types."""
    hid = getattr(obj, "hid", None) or (obj.get("hid") if isinstance(obj, Mapping) else None)
    name = getattr(obj, "name", None) or (obj.get("name") if isinstance(obj, Mapping) else None)
    archetype = getattr(obj, "archetype", None) or (obj.get("archetype") if isinstance(obj, Mapping) else None)
    return {
        "hid": str(hid) if hid is not None else "",
        "name": name,
        "archetype": archetype,
    }


def create_run(
    game: str,
    source: str = "api",
    pc_choice: Optional[str] = None,
    npc_choice: Optional[str] = None,
    player_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new simulation run.

    Args:
        game: Game name or path resolvable by get_game_config.
        source: Origin tag used in run naming. Defaults to "api".
        pc_choice: Player character HID (optional).
        npc_choice: NPC HID (optional).
        player_id: Explicit Player ID (optional).

    Returns:
        Dict containing run_id, game_name, pc, npc, and meta.
        On error, returns dict with "error" key.
    """
    try:
        run = SessionManager.create(
            game=game,
            source=source,
            pc_choice=pc_choice,
            npc_choice=npc_choice,
            player_id=player_id,
        )
        registry = get_registry()
        registry.add(run.name, run)

        pc = getattr(run.game, "_pc", {})
        npc = getattr(run.game, "_npc", {})

        return {
            "run_id": run.name,
            "game_name": run.game_config.name,
            "pc": _build_character_summary(pc),
            "npc": _build_character_summary(npc),
            "meta": _build_meta(run),
        }
    except Exception as e:
        logger.exception("Failed to create run")
        return {"error": str(e)}


def step_run(
    run_id: str,
    user_input: Optional[str] = None,
) -> Dict[str, Any]:
    """Advance a simulation by one step.

    Args:
        run_id: Identifier of the run to step.
        user_input: Optional text to pass as input.

    Returns:
        Dict containing events and meta.
        On error, returns dict with "error" key.
    """
    registry = get_registry()
    run = registry.get(run_id)

    if run is None:
        return {"error": f"Run not found: {run_id}"}

    try:
        for _ in run.step(user_input=user_input):
            pass
        return {
            "state": {"events": run._events},
            "meta": _build_meta(run),
        }
    except Exception as e:
        logger.exception("Step failed")
        return {"error": str(e)}


def play_run(
    run_id: str,
    inputs: List[str],
) -> Dict[str, Any]:
    """Process a batch of inputs sequentially.

    Args:
        run_id: Identifier of the run.
        inputs: List of input strings to process.

    Returns:
        Dict containing final_state and meta.
        On error, returns dict with "error" key.
    """
    registry = get_registry()
    run = registry.get(run_id)

    if run is None:
        return {"error": f"Run not found: {run_id}"}

    try:
        for text in inputs:
            if run.exited:
                break
            for _ in run.step(user_input=text):
                pass

        return {
            "final_state": {"events": run._events},
            "meta": _build_meta(run),
        }
    except Exception as e:
        logger.exception("Play failed")
        return {"error": str(e)}


def get_state(run_id: str) -> Dict[str, Any]:
    """Get current simulation state without advancing.

    Args:
        run_id: Identifier of the run.

    Returns:
        Dict containing state and meta.
        On error, returns dict with "error" key.
    """
    registry = get_registry()
    run = registry.get(run_id)

    if run is None:
        return {"error": f"Run not found: {run_id}"}

    return {
        "state": {"events": run._events},
        "meta": _build_meta(run),
    }


def save_run(run_id: str) -> Dict[str, Any]:
    """Save run to database.

    Args:
        run_id: Identifier of the run.

    Returns:
        Dict containing saved status.
        On error, returns dict with "error" key.
    """
    registry = get_registry()
    run = registry.get(run_id)

    if run is None:
        return {"error": f"Run not found: {run_id}"}

    try:
        run.save()
        return {"saved": run._saved}
    except Exception as e:
        logger.exception("Save failed")
        return {"error": str(e)}


def delete_run(run_id: str) -> Dict[str, Any]:
    """Delete a run from the registry.

    Args:
        run_id: Identifier of the run to delete.

    Returns:
        Dict containing success status.
    """
    registry = get_registry()
    registry.remove(run_id)
    return {"success": True}
