#!/usr/bin/env python3
"""Test script for DCS Simulation Engine API - Foresight game.

NOTE: This game requires consent. The player_id must reference a player record
that has a consent_signature. Create a player through the widget UI first,
or use an existing player_id that has completed the consent form.
"""

import json

from dcs_simulation_engine.client import DCSClient
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer


def _pprint(data):
    print(highlight(json.dumps(data, indent=2, default=str), JsonLexer(), TerminalFormatter()))


player_id = "000000000000000000000001"
access_key = "dev"

client = DCSClient("http://localhost:8080")

with client.create_run(
    game="Foresight",
    pc="human-normative",
    npc="flatworm",
    access_key=access_key,
    player_id=player_id,
) as run:
    print(f"Run created: {run!r}")

    print("\nStepping run (initial):")
    run.step()
    print(f"Simulator output: {run.simulator_output}")

    print("\nStepping run with user input:")
    run.step("I predict the character will move toward the light source")
    print(f"Simulator output: {run.simulator_output}")

    print("\nFull state:")
    _pprint(run.raw_state)

    print(f"\nMeta: turns={run.turns}, is_complete={run.is_complete}")

print("Run deleted.")
