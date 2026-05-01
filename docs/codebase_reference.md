## High-Level Overview

This codebase is a full-stack simulation platform centered on a Python backend package, with a React frontend and Mongo-backed persistence. Reporting, analysis, and admin tooling lives in `dcs_utils`, and configuration is primarily YAML-driven.

The main runtime entry point is the Typer CLI and the FastAPI app factory in `dcs_simulation_engine/api/app.py`. The React frontend is optional; the engine runtime is the API server.

### Design Considerations

This repository is *organized as a monorepo* so the engine, frontend, docs, examples, tests, and operational tooling can evolve together. Keeping these pieces in one place reduces version skew between the API, UI, run configurations, and evaluation workflows, which matters because DCS use cases (research workflows for AI and CogSci, etc.) depend on all of them staying aligned.

The *backend is asynchronous and WebSocket-driven* because gameplay shouldn't be limited to turn-based synchronous interactions. It is event-based, latency-sensitive, and often concurrent across human and AI players. Async I/O keeps the API responsive when it is handling persistence, model calls, or other external work, while WebSockets let the server stream state updates during a session instead of forcing a request/response loop.

The *React frontend is optional* by design. The engine exposes an API endpoint so the same runtime can support the built-in UI, custom clients, automated agents, and non-visual integrations. The default frontend and Fly.io deployment path make the project easy to start quickly, but the containerized runtime keeps it portable for other deployment targets.

The *HITL pipeline* exists because characters are treated as artifacts that need iterative evaluation, not static content. It gives developers a repeatable way to generate scenarios, inspect behavior, and refine character sheets before promotion.

The *character release policy* enforces quality thresholds before characters are promoted to production. Evaluations are fingerprinted to the character + model + prompt configuration, so material changes require re-evaluation of role-playing simulation quality. This keeps low-quality or under-evaluated characters out of the default database and makes the promotion process explicit and reviewable.

*Run harnessing is provided* to support repeatable AI evaluation workflows. Like other benchmarking frameworks, it standardizes orchestration across common providers. We support models from OpenRouter and Hugging Face by default so model runs can be executed consistently and compared with less setup overhead.

*Run configurations are intentionally only as configurable as needed* to support internal use cases. This keeps the configuration surface manageable and testable; exposing every possible toggle would create a combinatorial space that is difficult to reason about and validate, making engine quality and robustness harder to maintain. The goal is minimal configuration for common workflows, with extension points for cases that genuinely need customization. The `examples/` folder contains the DCS group's internal configurations and serves as the primary functional test surface for run configuration behavior.

The *CLI design intentionally departs from strict noun-verb command conventions* to support a mixed user base of AI researchers and less technical operators. Common engine operations are exposed as simple commands for local and remote runs (start, status, save, stop) plus basic report generation, while advanced workflows are grouped under admin subcommands (for example, server and database management, HITL pipelines, and related tooling). This keeps advanced capabilities available without overwhelming users who only need core run operations.

The *architecture also leaves room for future interaction patterns and client modalities*. Because the engine is built around session state, event streaming, and a clean client/server boundary, it can support richer multi-turn behavior and additional frontends without restructuring the core runtime. 

As a *design trade-off, we prioritize Python* for research velocity, readability, and ease of extension, accepting that peak throughput may be lower than in lower-level implementations and may require scaling or optimization for high-load deployments.


## Repo Structure
```sh
├── database_seeds      # seed data (characters and related collections)
├── dcs_simulation_engine
│   ├── core            # core engine components (e.g. session manager)
│   ├── dal             # data access layer for MongoDB
│   ├── deployments     # fly deployment assets (toml files)
│   ├── games           # core games
│   ├── infra           #...
├── dcs_utils          # reporting/analysis/admin tooling
├── ui              # React + Bun frontend
├── docs
├── docker
├── examples
├── tests
├── character-release-policy.yml
```

### Main Components

⚠️ This section needs completion.

The backend API layer `dcs_simulation_engine/api/app.py` ...hands off work between ...

`SessionManager` in `dcs_simulation_engine/core` manages the gameplay sessions.

`SessionRegistry` 

`EngineRunManager` ...

### Data Flow

⚠️ This section needs completion.

At a high level, the system lets a player start a text-based “game” against a simulated character, routes each turn through a game engine implementation, optionally calls an LLM-backed AI client to generate or validate responses, persists the transcript and session metadata to MongoDB, and streams events back to the browser over WebSockets.

For running the engine, the flow is:

1. Startup begins in the CLI calls the `create_app` function in `dcs_simulation_engine/api/app.py`

2. When a session starts, the API enforces auth and returns allowed games, characters and run state.

3. On WebSocket connection (), the server calls the `SessionManager.step_async()` to create the opening scene of a game.

4. Each message by the player and/or simulator is recorded as an event by `SessionEventRecorder`...

5. On termination, the session is finalized in Mongo with the exit reason, turn count, and last sequence number.

For normal gameplay, the flow is:
1. The browser loads the frontend and fetches ...

2. The player registers/authenticates through ...

3. The player opens a game setup page `/api/play/setup/{game}` and the backend loads the game config, queries the data layer for valid characters and returns allowed PC/NPC choices.

4. The UI POSTs `/api/play/game` and calls `SessionManager` which constructs a session object around that game.

5. The new session is inserted into the in-memory `SessionRegistry`

----

## DCS-SE Codebase Reference

::: dcs_simulation_engine
