#!/usr/bin/env python3
"""Test script for DCS Simulation Engine API using gradio_client - Foresight game.

NOTE: This game requires consent. The player_id must reference a player record
that has a consent_signature. Create a player through the widget UI first,
or use an existing player_id that has completed the consent form.
"""

import json

from pygments import highlight
from pygments.formatters import TerminalFormatter
from pygments.lexers import JsonLexer
from gradio_client import Client


def pprint(data):
    print(highlight(json.dumps(data, indent=2), JsonLexer(), TerminalFormatter()))

# Connect to the Gradio server
client = Client("http://localhost:8080")

# IMPORTANT: Replace with a valid player_id that has consent_signature
# You can create a player through the widget UI first
player_id = "000000000000000000000001"
access_key = "dev"

# Create a new run
result = client.predict(
    game="Foresight",
    source="api",
    pc_choice="human-normative",
    npc_choice="flatworm",
    access_key="",
    player_id=player_id,
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
print("\nStepping run with user action:")
result = client.predict(
    run_id=run_id,
    user_input="I predict the character will move toward the light source",
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
