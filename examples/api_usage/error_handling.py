#!/usr/bin/env python3
"""Manual smoke script showing APIClient error handling for AI players."""

import argparse
from typing import Literal

from dcs_simulation_engine.api.client import APIClient, SimulationRun
from dcs_simulation_engine.api.models import CreateGameRequest, WSEventFrame

GAME_NAME = "Explore"
PREFERRED_PC = "NA"
PREFERRED_NPC = "NA"

PLAYER_FAULT = "player_turn_validation_failed"
SYSTEM_FAULTS = {"simulator_turn_validation_retry_exhausted", "internal_error"}

TurnClassification = Literal[
    "no_error",
    "player_retryable",
    "player_terminal",
    "system_terminal",
    "unknown_error",
]


def _choose_hid(options, preferred_hid: str) -> str:
    for option in options:
        if option.hid == preferred_hid:
            return option.hid
    if not options:
        raise RuntimeError("No valid character choices were returned by setup.")
    return options[0].hid


def _require_api_key(registration_required: bool, api_key: str | None) -> str:
    if api_key:
        return api_key
    if not registration_required:
        raise RuntimeError("Anonymous player creation should handle registration_required: false runs.")
    raise RuntimeError("--api-key is required when the active run config has registration_required: true.")


def latest_error_event(run: SimulationRun) -> WSEventFrame | None:
    """Return the most recent API-visible error event for a run."""
    return next((event for event in reversed(run.history) if event.event_type == "error"), None)


def classify_error_event(event: WSEventFrame | None) -> TurnClassification:
    """Classify an API-visible error into the action an AI player should take."""
    if event is None:
        return "no_error"
    if event.failure_type == PLAYER_FAULT:
        if event.retries_remaining is not None and event.retries_remaining > 0:
            return "player_retryable"
        return "player_terminal"
    if event.failure_type in SYSTEM_FAULTS:
        return "system_terminal"
    return "unknown_error"


def main() -> None:
    """Start Explore, send a deliberately invalid action, and branch on error type."""
    parser = argparse.ArgumentParser(description="Show APIClient error handling for AI players.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Player API key for runs with registration_required: true.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    with APIClient(url=base_url, timeout=60.0) as api:
        config = api.server_config()
        registration_required = config.registration_enabled

        if registration_required or args.api_key:
            api_key = _require_api_key(registration_required, args.api_key)
            api.auth(api_key=api_key)
        else:
            api_key = api.anonymous_player().api_key

        setup = api.setup_options(game_name=GAME_NAME, api_key=api_key)
        if not setup.can_start:
            raise RuntimeError(f"{GAME_NAME} cannot be started: {setup.message or setup.denial_reason}")
        pc_choice = _choose_hid(setup.pcs, PREFERRED_PC)
        npc_choice = _choose_hid(setup.npcs, PREFERRED_NPC)

        with api.start_game(
            CreateGameRequest(
                api_key=api_key,
                game=GAME_NAME,
                pc_choice=pc_choice,
                npc_choice=npc_choice,
                source="api-example-error-handling",
            )
        ) as run:
            print(f"session_id={run.session_id}")

            run.step()
            print(f"opening={run.simulator_output or '<no simulator output>'}")

            bad_action = "You set the world on fire."
            print(f"action={bad_action}")
            run.step(bad_action)

            error = latest_error_event(run)
            classification = classify_error_event(error)
            print(f"classification={classification}")

            if classification == "player_retryable":
                assert error is not None
                print(f"failure_type={error.failure_type}")
                print(f"retries_remaining={error.retries_remaining}")
                print(error.content)

                safer_action = "I look around carefully and describe what I can observe."
                print(f"retry_action={safer_action}")
                run.step(safer_action)
                print(f"retry_output={run.simulator_output or '<no simulator output>'}")
            elif classification == "player_terminal":
                assert error is not None
                print(f"failure_type={error.failure_type}")
                print("The AI player's failed attempts are exhausted. Stop this session.")
            elif classification == "system_terminal":
                assert error is not None
                print(f"failure_type={error.failure_type}")
                print("The engine failed this turn. This was not caused by the AI player's action.")
            elif classification == "unknown_error":
                assert error is not None
                print(f"failure_type={error.failure_type}")
                print(error.content)
            else:
                print(f"accepted_output={run.simulator_output or '<no simulator output>'}")


if __name__ == "__main__":
    main()
