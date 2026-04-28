# Advanced Usage

> Note: Most advanced usage requires checking out the codebase (see the [Contributing Guide](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/CONTRIBUTING.md)).

## Custom Assignment Strategies

Assignment strategies control what gameplay scenario (game + characters) is available next for a player. Researchers use this to ensure that player gameplay sessions are distributed across games and characters in a way that meets their research goals. For example, a researcher might want to ensure that each player gets a balanced mix of games and characters, or that certain underrepresented characters are prioritized for assignment.

To customize assignment strategies, check out the code and implement the `AssignmentStrategy` interface in `dcs_simulation_engine/core/assignment_strategies.py`. Then reference your strategy by name in a run configuration.

⚠️ Note: This feature is incomplete or missing.

## Custom Character Filters

Character filters allow users to specify useful categories of PCs/NPCs allowed in gameplay. For example, if a user wants only neurodivergent non-player characters, they can use the built-in `neurodivergent` filter by name.

To customize character filters, check out the code and:

### 1. Add the filter

Implement the `CharacterFilter` interface in `dcs_simulation_engine/core/character_filters/base.py` (use the other filters as examples) and add it to the list of available filters in `dcs_simulation_engine/core/character_filters/__init__.py`

### 2. Add the filter to a game

Add the character filter to the games configuration (in `dcs_simulation_engine/games/`) that you want to make it available in

Then run the engine with the filter referenced by name in the run config and only those characters will be selected from for gameplay.

## Custom Characters

To customize (add/modify) characters, check out the codebase and use the workflow below.

### 1. Create character sheet(s)

Create or modify a character sheet based on research (for example primary sources, expert interviews, or first-person experiential input) and add it to the development database: `database_seeds/dev/characters.json`.

Character sheets usually include:

- Short and long descriptions
- Abilities, persona features, and goals
- Structured dimensions such as origin, form, agency, substrate, and size

### 2. Iteratively update character sheet(s) to meet quality thresholds

Use the human-in-the-loop (HITL) CLI to generate scenarios and evaluate character behavior:

```bash
dcs admin hitl create <character_hid> --db dev
```

This creates a scaffolded scenarios file in `dcs_utils/data/character_scenarios/`. Edit the prompts so they actually pressure-test the character's behavior.

Then run HITL updates while the DCS server is running:

```bash
dcs admin hitl update <character_hid>
```

`hitl update` can:

- Build or rebuild scenario history
- Generate simulator responses
- Collect evaluator feedback on whether outputs are in character, out of character, or invalid

In practice, this stage is iterative: adjust the character sheet and/or scenario prompts, rerun HITL, and keep going until the behavior looks good.

> Optionally running external evaluations using `expert-evaluation.yml` and/or `select-characters.yml` run configs can be useful where you have access to domain experts that can provide feedback on character behavior. 

### 3. Generate a Simulation Quality Report

Export the completed HITL scenarios to a results directory:

```bash
dcs-utils hitl export <character_hid>
```

Then generate a simulation quality report:

```bash
dcs-utils report results results/hitl_<character_hid> --only sim-quality --title "Simulation Quality — <character_hid>"
```

Review the report and determine whether the coverage and in-character fidelity (ICF) scores are sufficient for publication.

If results are insufficient, go back to step 2 and improve the character sheet and/or scenario prompts. If results are sufficient, move to step 4.

### 4. Publish for Review

Publish the character evaluation results:

```bash
dcs-utils admin publish characters <path-to-sim-quality-report.html>
```

Then open a PR that includes:

- The character JSON changes
- The character scenarios JSON file
- Any evaluation artifacts that are appropriate for the current workflow, such as simulation-quality reports

> To propose that DCS-SE add a character to the core character database, open a PR that includes the reasoning and design decisions, code changes, and the quality report with scores.

⸻

## Custom Games

To customize games, beyond their existing exposed configuration options, check out the codebase and use the workflow below.

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
