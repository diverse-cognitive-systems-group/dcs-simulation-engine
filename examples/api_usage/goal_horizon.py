#!/usr/bin/env python3
"""Manual smoke script for the Goal Horizon game via APIClient."""

import argparse
import json

from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.api.models import CreateGameRequest

GAME_NAME = "Goal Horizon"
PREFERRED_PC = "NA"
PREFERRED_NPC = "FW"


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


def main() -> None:
    """Start Goal Horizon, print the opening turn, then take one action."""
    parser = argparse.ArgumentParser(description="Run a short Goal Horizon session.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Player API key for runs with registration_required: true.",
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    with APIClient(url=base_url, timeout=60.0) as api:
        print("1) Fetch server config")
        config = api.server_config()
        registration_required = config.registration_enabled
        print(f"   registration_required={config.registration_enabled}")

        if registration_required or args.api_key:
            api_key = _require_api_key(registration_required, args.api_key)
            print("2) Authenticate")
            auth = api.auth(api_key=api_key)
            print(f"   authenticated={auth.authenticated} player_id={auth.player_id}")
        else:
            print("2) Create anonymous player")
            anonymous = api.anonymous_player()
            api_key = anonymous.api_key
            print(f"   player_id={anonymous.player_id}")

        print("3) Fetch setup options")
        setup = api.setup_options(game_name=GAME_NAME, api_key=api_key)
        if not setup.can_start:
            raise RuntimeError(f"{GAME_NAME} cannot be started: {setup.message or setup.denial_reason}")
        pc_choice = _choose_hid(setup.pcs, PREFERRED_PC)
        npc_choice = _choose_hid(setup.npcs, PREFERRED_NPC)
        print(f"   pc_choice={pc_choice}")
        print(f"   npc_choice={npc_choice}")

        print("4) Start session")
        with api.start_game(
            CreateGameRequest(
                api_key=api_key,
                game=GAME_NAME,
                pc_choice=pc_choice,
                npc_choice=npc_choice,
                source="api-example-goal-horizon",
            )
        ) as run:
            print(f"   session_id={run.session_id}")

            print("5) Opening scene")
            run.step()
            print(json.dumps(run.session_meta.model_dump(mode="json") if run.session_meta else {}, indent=2))
            print(run.simulator_output or "<no simulator output>")

            print("6) Advance one turn (send player's next action)")
            run.step("I look around.")
            print(run.simulator_output or "<no simulator output>")

            print("7) Session state")
            print(json.dumps([event.model_dump(mode="json") for event in run.history], indent=2))
            print(f"   turns={run.turns}")
            print(f"   is_complete={run.is_complete}")


if __name__ == "__main__":
    main()
