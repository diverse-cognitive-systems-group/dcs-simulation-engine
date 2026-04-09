# Advanced Usage

> Note: All advanced usage requires checking out the codebase. If you’re not sure how to do this, see the Contributing Guide in the main repository.

## Custom Characters

To add custom characters to the simulation, first check out the codebase, then follow this workflow:

### 1. Create character sheet(s)

Create or modify a character sheet based on research (e.g., primary sources, expert interviews) and add it to the character to the database: `database_seeds/dev/characters.json`

### 2. Iteratively update characters sheet(s) to meet quality thresholds

Use the human-in-the-loop CLI to generate scenarios and evaluate character behavior:

`dcs admin hitl --help`

> Optionally running external evaluations using `expert-evaluation.yml` and/or `select-characters.yml` run configs can be useful where you have access to domain experts that can provide feedback on character behavior. 

### 3. Generate a Simulation Quality Report

Generate a simulation quality report (`dcs report <path/to/results> sim-quality --title "Character Quality Report"`) and determine if the coverage and in-character fidelity (ICF) scores are sufficient for publication 

If results are insufficient go back to step 2 to improve the character sheets or adjust the thresholds in `character-release-policy.yml`. If results are sufficient, move to step 4 to publish for review.

### 4. Publish for Review

Publish the character (`dcs admin publish --help`)

> To propose the DCS-SE adds this character to core characters database open a PR that includes reasoning and design decisions, code changes and the quality report with scores.

⸻

## Custom Games

To build a custom game:

### 1. Implement the Game Interface

Create a new game file:

`dcs_simulation_engine/games/new_game.py`

Implement all required interface methods.

### 2. Add to a Run Config

Reference your game in a run config. See: `examples/run_configs/`

### 3. Test and Run

Test the game manually and/or add automated tests in `tests/` to validate game logic and integration with the engine.

### 4. Publish

Run the engine remotely with your new game.

⸻

## Custom Deployments (Non-Fly.io)

The engine is containerized and supports any platform that can run multi-container Docker applications.

To deploy to a new provider:

⚠️ TODO: Deployment example (e.g. AWS, GCP, Azure)

⸻

## Custom Clients (Unity, VR/AR, etc.)

The engine exposes a FastAPI + WebSocket interface. Any client can integrate as long as it can:

1.	Send player actions

2.	Receive and render simulation updates

This is useful for non-run-harnessed gameplay, where the client directly interacts with the engine API without using the run harness. This enables custom orchestration, AI-driven control loops, and integration into external systems or apps.

### Example Non-Run-Harnessed Gameplay with OpenEvolve

TODO: alex

### Example Unity Integration

```plaintext
[Client Application (Unity / VR / AR)]
   - Player input
   - 3D rendering
   - Voice / UI / controllers
          │
          │ WebSocket / HTTP
          ▼
[Simulation Engine API]
   - Simulation state
   - Character decisions
   - World logic
   - Game rules
```

⸻