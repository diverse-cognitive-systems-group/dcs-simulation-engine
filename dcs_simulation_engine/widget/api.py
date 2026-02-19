"""Gradio API functions for programmatic access to the simulation engine.

This module provides API functions that can be mounted on a Gradio Blocks
instance using the `api_name` parameter. These functions mirror the
functionality previously provided by the FastAPI endpoints.

All functions return dicts that Gradio serializes to JSON automatically.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Union

from loguru import logger

from dcs_simulation_engine.core.run_manager import RunManager
from dcs_simulation_engine.widget.services import get_registry


def _build_meta(run: RunManager) -> Dict[str, Any]:
    """Build metadata dict from a RunManager."""
    return {
        "name": run.name,
        "turns": run.turns,
        "runtime_seconds": run.runtime_seconds,
        "runtime_string": run.runtime_string,
        "exited": run.exited,
        "exit_reason": run.exit_reason,
        "saved": run.saved,
        "output_path": (
            str(run.state.get("output_path")) if run.state.get("output_path") else None
        ),
    }


def _build_character_summary(obj: Any) -> Dict[str, Any]:
    """Build character summary dict from various object types."""
    hid = getattr(obj, "hid", None) or (
        obj.get("hid") if isinstance(obj, Mapping) else None
    )
    name = getattr(obj, "name", None) or (
        obj.get("name") if isinstance(obj, Mapping) else None
    )
    archetype = getattr(obj, "archetype", None) or (
        obj.get("archetype") if isinstance(obj, Mapping) else None
    )
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
    access_key: Optional[str] = None,
    player_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new simulation run.

    Args:
        game: Game name or path resolvable by get_game_config.
        source: Origin tag used in run naming. Defaults to "api".
        pc_choice: Player character HID (optional).
        npc_choice: NPC HID (optional).
        access_key: Access key used to resolve player_id (optional).
        player_id: Explicit Player ID, overrides access_key (optional).

    Returns:
        Dict containing run_id, game_name, pc, npc, and meta.
        On error, returns dict with "error" key.
    """
    try:
        run = RunManager.create(
            game=game,
            source=source,
            pc_choice=pc_choice,
            npc_choice=npc_choice,
            access_key=access_key,
            player_id=player_id,
        )
        registry = get_registry()
        registry.add(run.name, run)

        pc = run.context.get("pc")
        npc = run.context.get("npc")

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
    user_input: Optional[Union[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Advance a simulation by one step.

    Args:
        run_id: Identifier of the run to step.
        user_input: Optional text or mapping to pass as input.

    Returns:
        Dict containing state and meta.
        On error, returns dict with "error" key.
    """
    registry = get_registry()
    run = registry.get(run_id)

    if run is None:
        return {"error": f"Run not found: {run_id}"}

    try:
        # run.step() is a generator, must consume it to execute
        for _ in run.step(user_input=user_input):
            pass
        state = run.state or {}
        return {
            "state": state,
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
            # run.step() is a generator, must consume it to execute
            for _ in run.step(user_input=text):
                pass

        # If last event was user, one extra step may be needed
        if not run.exited and run.state.get("events"):
            last = run.state["events"][-1]
            if getattr(last, "type", None) == "user" or (
                isinstance(last, dict) and last.get("type") == "user"
            ):
                for _ in run.step(None):
                    pass

        return {
            "final_state": run.state or {},
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
        "state": run.state or {},
        "meta": _build_meta(run),
    }


def save_run(
    run_id: str,
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Save run outputs to filesystem.

    Args:
        run_id: Identifier of the run.
        output_dir: Optional directory or path hint.

    Returns:
        Dict containing saved, output_path, and files.
        On error, returns dict with "error" key.
    """
    registry = get_registry()
    run = registry.get(run_id)

    if run is None:
        return {"error": f"Run not found: {run_id}"}

    try:
        out_path = run.save(path=output_dir) if output_dir else run.save()
        files = [str(out_path)] if out_path else []
        return {
            "saved": True,
            "output_path": str(out_path) if out_path else None,
            "files": files,
        }
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
