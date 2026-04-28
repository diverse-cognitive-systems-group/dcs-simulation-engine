# Advanced Usage

> Note: Most advanced usage requires checking out the codebase (see the [Contributing Guide](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/CONTRIBUTING.md)).

## Custom Assignment Strategies

Assignment strategies control what gameplay scenario (game + characters) is available next for a player. Researchers use this to ensure that players gameplay sessions are distributed across games and characters in a way that meets their research goals. For example, a researcher might want to ensure that each player gets a balanced mix of games and characters, or that certain underrepresented characters are prioritized for assignment.

To add one:

1. Implement the `AssignmentStrategy` protocol in
   `dcs_simulation_engine/core/assignment_strategies/base.py`.
2. Add the implementation to the registry in
   `dcs_simulation_engine/core/assignment_strategies/__init__.py`.
3. Reference the new strategy name from your experiment YAML under
   `assignment_strategy.strategy`.

## Custom Characters

Character seed data lives under `database_seeds/`.

Typical local workflow:

1. Edit or add entries in `database_seeds/dev/characters.json`.
2. Reseed the database by starting the server with
   `--mongo-seed-dir database_seeds/dev`.
3. Exercise the character locally through the UI or the API example scripts in
   `examples/api_usage/`.
4. Export results and generate reports from the resulting run data.

If you are preparing data for production-like use, keep the dev and prod seed
sets separate and only promote the character after review.

## Custom Games

Built-in game metadata is defined in `games/*.yaml`, and each game points to a
Python implementation class under `dcs_simulation_engine/games/`.

To add a new game:

1. Add a new metadata file in `games/`.
2. Implement the referenced Python game class.
3. Reference the canonical game name from your experiment config.
4. Test the game locally before deploying it remotely.

## Custom Clients And Frontends

The default React UI is only one client. Any custom client can talk to the API
over HTTP and WebSocket.

Useful starting points:

- browser UI source: `ui/`
- Python client examples: `examples/api_usage/`
- API docs: `/docs` and `/redoc` on a running server

At a minimum, a custom client needs to:

- discover server mode from `/api/server/config`
- create or resume a session
- send actions
- receive streamed gameplay updates

## Non-Fly Deployments

The engine is containerized, so you can deploy it on any platform that can run
the equivalent of:

- MongoDB
- the API container from `docker/api.dockerfile`
- the UI container from `docker/ui.dockerfile`

The Fly.io workflow is the only fully documented remote deployment path in this
repo today, but the generated files in `deployments/<slug>/` are a useful
reference when adapting the stack to another provider.

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