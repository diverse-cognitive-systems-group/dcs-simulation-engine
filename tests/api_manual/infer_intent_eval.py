#!/usr/bin/env python3
"""Manual test for Infer Intent flow through the FastAPI/WS server."""

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
    pc="human-normative",
    npc="flatworm",
    access_key=access_key,
) as run:
    print(f"Run created: {run!r}")

    # Initial step — opening scene
    run.step()
    print(f"\n[Turn 0 - Simulator] {run.simulator_output}")

    # 3 hardcoded interaction turns
    turns = [
        "I crouch down and look closely at the creature on the ground.",
        "I place a small piece of food near it and step back to watch.",
        "I gently prod the ground beside it with my finger.",
    ]
    for i, action in enumerate(turns, start=1):
        print(f"\n[Turn {i} - Player] {action}")
        run.step(action)
        print(f"[Turn {i} - Simulator] {run.simulator_output}")

    print(f"\n  turns={run.turns}, lifecycle={run.lifecycle}")

    # Submit guess via /guess command
    print("\n[Guess] /guess")
    run.step("/guess")
    print(f"[Simulator] {run.simulator_output}")
    print(f"  lifecycle={run.lifecycle}")

    # Answer completion form: user_goal_inference
    guess_text = "The creature is trying to find food or move toward a food source."
    print(f"\n[Form answer 1] {guess_text}")
    run.step(guess_text)
    print(f"[Simulator] {run.simulator_output}")

    # Answer completion form: other_feedback
    feedback_text = "No additional feedback."
    print(f"\n[Form answer 2] {feedback_text}")
    run.step(feedback_text)
    print(f"[Simulator] {run.simulator_output}")
    print(f"  lifecycle={run.lifecycle}, is_complete={run.is_complete}")

    print(f"\n  Exit reason: {run.exit_reason}")
    print(f"  Total turns: {run.turns}")

    print("Full Final State")
    _pprint(run.raw_state)

print("\nRun deleted.")
