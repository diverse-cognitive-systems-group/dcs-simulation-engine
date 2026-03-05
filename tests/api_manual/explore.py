#!/usr/bin/env python3
"""Test script for DCS Simulation Engine API using gradio_client."""

import json

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer
from gradio_client import Client


def pprint(data):
    print(highlight(json.dumps(data, indent=2), JsonLexer(), TerminalFormatter()))

# Connect to the Gradio server
client = Client("http://localhost:8080")

# Create a new run
result = client.predict(
    game="explore",
    source="api",
    pc_choice="human-non-hearing",
    npc_choice="thermostat",
    access_key="",
    player_id="",
    api_name="/create_run"
)
print("Create run result:")
pprint(result)

run_id = result["run_id"]

# Step the run (initial step with empty input)
print("\nStepping run (initial):")
result = client.predict(
    run_id=run_id,
    user_input="",
    api_name="/step_run"
)
print("Initial step result:")
pprint(result)

# Step with user input
print("Stepping run with user action:")
result = client.predict(
    run_id=run_id,
    user_input="You smell the thermostat",
    api_name="/step_run"
)
print("Step result:")
pprint(result)
print("\nSimulator response:")
pprint(result['state']['simulator_output'])


# Get current state
print("\nGetting state:")
result = client.predict(
    run_id=run_id,
    api_name="/get_state"
)
print("Current state:")
pprint(result)

# Cleanup - delete the run
print("\nDeleting run:")
result = client.predict(
    run_id=run_id,
    api_name="/delete_run"
)
pprint(result)
