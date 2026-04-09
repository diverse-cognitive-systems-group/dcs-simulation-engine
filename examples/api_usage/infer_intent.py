#!/usr/bin/env python3
"""Test script for DCS Simulation Engine API - Infer Intent game."""

import json

from dcs_simulation_engine.client import DCSClient
from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer


def _pprint(data):
    print(highlight(json.dumps(data, indent=2, default=str), JsonLexer(), TerminalFormatter()))


access_key = "dev"

client = DCSClient("http://localhost:8080")

with client.start_game(
    game="Infer Intent",
    pc="NA",
    npc="FW",
    access_key=access_key,
) as run:
    print(f"Run created: {run!r}")

    print("\nStepping run (initial):")
    run.step()
    print(f"Simulator output: {run.simulator_output}")

    print("\nStepping run with user input:")
    run.step("I believe the character's intent is to find food")
    print(f"Simulator output: {run.simulator_output}")

    print("\nFull state:")
    _pprint(run.raw_state)

    print(f"\nMeta: turns={run.turns}, is_complete={run.is_complete}")

print("Run deleted.")
