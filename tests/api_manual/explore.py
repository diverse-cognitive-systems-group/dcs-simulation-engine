#!/usr/bin/env python3
"""Test script for DCS Simulation Engine API - explore game."""

import json

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer

from dcs_simulation_engine.client import APIClient


def _pprint(data):
    print(highlight(json.dumps(data, indent=2, default=str), JsonLexer(), TerminalFormatter()))


client = APIClient("http://localhost:8080")

with client.create_run(game="explore", pc="human-non-hearing", npc="thermostat") as run:
    print(f"Run created: {run!r}")

    print("\nStepping run (initial):")
    run.step()
    print(f"Simulator output: {run.simulator_output}")

    print("\nStepping run with user input:")
    run.step("You smell the thermostat")
    print(f"Simulator output: {run.simulator_output}")

    print("\nFull state:")
    _pprint(run.raw_state)

    print(f"\nMeta: turns={run.turns}, is_complete={run.is_complete}")

print("Run deleted.")
