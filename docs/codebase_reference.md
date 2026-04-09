# Codebase Reference

This codebase is a full-stack simulation platform centered on a **Python backend** package, `dcs_simulation_engine`, with a **React frontend** in `ui`, **Mongo-backed persistence** in `dcs_simulation_engine/dal`, reporting/analysis/admin tooling in `dcs_utils`, and content/configuration in yaml run configs.

The main runtime entry point is the Typer CLI in `XX/app.py` and the FastAPI app factory in dcs_simulation_engine/api/app.py.


## Repo Structure
```sh
├── database_seeds # characters for simulation
├── dcs_simulation_engine
│   ├── core
│   ├── dal
│   ├── deployments
│   ├── games
│   ├── infra
├── dcs_utils
├── ui
├── docs
├── examples
├── tests
```

## Main Components

The backend API layer `dcs_simulation_engine/api/app.py` ...hands off work between ...

`SessionManager`

`SessionRegistry`

`EngineRunManager` ...

--

The UI mirrors the backend split. The games pages call HTTP `setup/create` endpoints, then the `play` page switches to WebSockets for 

## Data Flow

At a high level, the system lets a player start a text-based “game” against a simulated character, routes each turn through a game engine implementation, optionally calls an LLM-backed AI client to generate or validate responses, persists the transcript and session metadata to MongoDB, and streams events back to the browser over WebSockets.

For running the engine, the flow is:
1. Startup begins in the CLI which resolves Mongo, validates AI configuration, and calls the APIs create_app. Create app preloads game and experiment configs, then starts the in-memory session registry.

For normal gameplay, the flow is:
1. The browser loads the frontend and fetches `/api/server/config`

2. The player registers/authenticates through `/api/player/*` and the UI stores the API key ...

3. The player opens a game setup page `/api/play/setup/{game}` and the backend loads the game config, asks the provider??? for valid characters and returns allowed PC/NPC choices.

4. The UI POSTs `/api/play/game` and calls SessionManager which constructs a session object around that game.

5. The new session is inserted into the in-memory SessionRegistry

QUESTIONS

- the engien is started via cli, this calls the APIs create_app
- running the engine always runs the FastAPI app/server
- the ui can be started or not 
- the ui is react + bun

- changing characters, ...

- 

::: dcs_simulation_engine
