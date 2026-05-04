#!/usr/bin/env python3
"""Manual smoke script for registration-required auth, play, and close."""

import argparse
import json
import uuid

from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.api.models import CreateGameRequest, RegistrationRequest

PREFERRED_PC = "NA"
PREFERRED_NPC = "NA"


def _choose_hid(options, preferred_hid: str) -> str:
    for option in options:
        if option.hid == preferred_hid:
            return option.hid
    if not options:
        raise RuntimeError("No valid character choices were returned by setup.")
    return options[0].hid


def main() -> None:
    """Register a new player, authenticate, play three steps, then close the session."""
    parser = argparse.ArgumentParser(description="Register, auth, play 3 steps, close.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--game", default="Explore", help="Game name")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    email = f"api-smoke-{uuid.uuid4().hex[:10]}@example.com"

    with APIClient(url=base_url, timeout=60.0) as api:
        print("1) Fetch server config")
        config = api.server_config()
        if not config.registration_enabled:
            raise RuntimeError("register_auth_play_close.py requires registration_required: true.")
        print(f"   registration_required={config.registration_enabled}")

        print("2) Register user")
        reg = api.register_player(
            RegistrationRequest(
                full_name="API Smoke Tester",
                email=email,
                phone_number="+1 555 010 9999",
            )
        )
        api_key = reg.api_key
        print(f"   player_id={reg.player_id}")

        print("3) Authenticate")
        auth = api.auth(api_key=api_key)
        print(f"   authenticated={auth.authenticated} player_id={auth.player_id}")

        print("4) Fetch setup options")
        setup = api.setup_options(game_name=args.game, api_key=api_key)
        if not setup.can_start:
            raise RuntimeError(f"{args.game} cannot be started: {setup.message or setup.denial_reason}")
        pc_choice = _choose_hid(setup.pcs, PREFERRED_PC)
        npc_choice = _choose_hid(setup.npcs, PREFERRED_NPC)
        print(f"   pc_choice={pc_choice}")
        print(f"   npc_choice={npc_choice}")

        print("5) Start game")
        with api.start_game(
            CreateGameRequest(
                api_key=api_key,
                game=args.game,
                pc_choice=pc_choice,
                npc_choice=npc_choice,
                source="api-smoke-script",
            )
        ) as run:
            print(f"   session_id={run.session_id}")

            print("6) Opening scene")
            run.step()
            print(json.dumps(run.session_meta.model_dump(mode="json") if run.session_meta else {}, indent=2))
            print(run.simulator_output or "<no simulator output>")

            prompts = [
                "I look around.",
                "I take one careful step forward.",
                "I say 'hello' and listen for a response.",
            ]
            for idx, text in enumerate(prompts, start=1):
                run.step(text)
                print(f"   step {idx}: {run.simulator_output or '<no simulator output>'}")
                print(f"   turn_end: turns={run.turns} exited={run.is_complete}")

        print("7) Session closed")
        print("   closed=True")


if __name__ == "__main__":
    main()
