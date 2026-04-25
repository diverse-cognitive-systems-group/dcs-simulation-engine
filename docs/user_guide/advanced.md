# Advanced Usage

> Note: Most advanced usage requires checking out the codebase (see the [Contributing Guide](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/CONTRIBUTING.md)).

## Custom Assignment Strategies

Assignment strategies control what gameplay scenario (game + characters) is available next for a player. Researchers use this to ensure that players gameplay sessions are distributed across games and characters in a way that meets their research goals. For example, a researcher might want to ensure that each player gets a balanced mix of games and characters, or that certain underrepresented characters are prioritized for assignment.

To customize assignment strategies, checkout the code and implement the `AssignmentStrategy` interface in `dcs_simulation_engine/core/assignment_strategies.py`. Then reference your strategy by name in a run configuration.

⚠️ Note: This feature is incomplete or missing.

## Custom Character Filters

Character filters allow users to specify useful categories of PCs/NPCs allowed in gameplay. For example, if a user wants only neurodivergent non-player characters allows they can use the built-in `neurodivergent` filter by name.

To customize character filters, checkout the code and 

### 1. Add the filter

Implement the `CharacterFilter` interface in `dcs_simulation_engine/core/character_filters/base.py` (use the other filters as examples) and add it to the list of available filters in `dcs_simulation_engine/core/character_filters/__init__.py`

### 2. Add the filter to a game

Add the character filter to the games configuration (in `dcs_simulation_engine/games/`) that you want to make it available in

Then run the engine with the filter referenced by name in the run config and only those characters will be selected from for gameplay.

## Custom Characters

To customize (add/modify) characters, checkout the codebase and use the workflow below.

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

To customize games, beyond their existing exposed configuration options, checkout the codebase and use the workflow below.

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

⚠️ TODO: Add high level external deployment workflow example (e.g. AWS, GCP, Azure)

⸻

## Custom Clients and Frontends (Unity, VR/AR, etc.)

The engine exposes an API endpoint, so you do not have to use our text-based React frontend. Any client can connect to the endpoint to:

1.	Send player actions

2.	Receive and render simulation updates

### Example Non-Run-Harnessed Gameplay with OpenEvolve

This is useful for non-run-harnessed gameplay, where the client directly interacts with the engine API without using the run harness. This enables custom orchestration, AI-driven control loops, and integration into external systems or apps.

TODO: Add open-evolve example

### Example Unity Integration

Unity or other custom clients can use the engine API directly to send player input and receive simulation state updates. This makes it possible to build bespoke visuals, controls, or interaction loops without relying on the default React frontend.

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