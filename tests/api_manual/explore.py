#!/usr/bin/env python3
"""Test script for DCS Simulation Engine API using gradio_client."""

from gradio_client import Client

# Connect to the Gradio server
client = Client("http://localhost:8080")

# Create a new run
print("Creating run...")
result = client.predict(
    game="explore",
    source="api",
    pc_choice="human-non-hearing",
    npc_choice="thermostat",
    access_key="",
    player_id="",
    api_name="/create_run"
)
print(f"Create run result: {result}")

run_id = result["run_id"]
print(f"RUN_ID: {run_id}")

# Step the run (initial step with empty input)
print("\nStepping run (initial)...")
result = client.predict(
    run_id=run_id,
    user_input="",
    api_name="/step_run"
)
print(f"Initial step result: {result}")

# Step with user input
print("\nStepping run with user action...")
result = client.predict(
    run_id=run_id,
    user_input="You smell and then gently lick the thermostat",
    api_name="/step_run"
)
print(f"Step result: {result}")
print(f"\nSimulator response: {result['state']['simulator_output']}")

# Get current state
print("\nGetting state...")
result = client.predict(
    run_id=run_id,
    api_name="/get_state"
)
print(f"Current state: {result}")

# Cleanup - delete the run
print("\nDeleting run...")
result = client.predict(
    run_id=run_id,
    api_name="/delete_run"
)
print(f"Delete result: {result}")
