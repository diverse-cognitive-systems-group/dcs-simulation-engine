🚧 NOTICE: This is a W.I.P. (official releases will be tagged and licensed when ready)

# Diverse Cognitive Systems (DCS) Simulation Engine 


*A textual role-playing simulator for diverse cognitive systems to play and learn.*

[![Web Demo](https://img.shields.io/badge/Demo%20-28A745)](https://dcs-free-play-ui.fly.dev) <!-- green -->
[![API Docs](https://img.shields.io/badge/API%20Docs%20-FF8C00)](https://dcs-free-play-api.fly.dev/docs) <!-- orange -->
[![Project Wiki](https://img.shields.io/badge/Project%20Wiki%20-FF69B4)](https://github.com/fuzzy-tribble/dcs-simulation-engine/wiki) <!-- pink -->
[![Build Status](https://github.com/fuzzy-tribble/dcs-simulation-engine/actions/workflows/ci.yaml/badge.svg?branch=main)](https://github.com/fuzzy-tribble/dcs-simulation-engine/actions/workflows/ci.yaml)

## Quickstart

Install [Docker](https://docs.docker.com/engine/install/) following the instructions for your operating system.

Run the full stack with the commands below. ***The build may take a few minutes the first time you run the command.***

```sh
# configure your OpenRouter API key in a .env first

# start the app
docker compose up --build --detach

# go to http://localhost:5173 to view the ui

# teardown
docker compose down --volumes

# the entire state of the database in store in a timestamped folder
ls ./runs
```


## What is this?

It's both a research framework and a play space.

For researchers, it offers a way to **study interactions between diverse cognitive systems in controlled, designed scenarios with reliably simulated character responses**--from how neurodivergent humans collaborate on a task, to how AI systems with varying architectures generate communication protocols, to how neurotypical humans interpret and engage with unfamiliar or radically different beings.

For players, it's a collaborative improve arena where a player character (you) and a simulated character take on a cast of characters with distinct abilities and cognitive profiles. Everything unfolds through language: actions, imagination, and world-building in a style inspired by tabletop roleplaying games.

Under the hood, it’s built to faithfully represent the actions and behavioral patterns of a curated range of real cognitive systems—from neurodivergent humans to simple mechanical homeostatic agents and biological systems with basal intelligence. This foundation supports rich, varied interactions that push participants to adapt and think differently, while giving researchers a structured way to observe and analyze the dynamics that emerge.

And the interface is delightfully simple:
*It runs on the world’s most powerful graphics chip: your imagination. Its controller? The world’s most powerful cognitive interface: symbolic language.*

## Why'd we build this?
Interfacing between different cognitive systems--even within the same species and cultures--is often difficult. **We lack reliable metrics for evaluating how well an AI, human, or any cognitive system understands the goals and perspectives of minds unlike its own.** 

This tool addresses that gap by modeling configurable interaction scenarios where humans, AI systems, and other characters — each with distinct sensory, perceptual, regulatory, and action modalities — can engage, coordinate, and uncover what the other cares about, how their goalspace is structured, and how to accomplish shared or competing objectives.

There’s also a social reason: divergent humans are, by definition, outliers in the bell curve and often underrepresented in everyday interaction. That makes communicating with fundamentally different minds an underdeveloped skill for many. Many of our simulated characters draw from real divergent humans, making those behavioral patterns more accessible. While the primary purpose of this tool is research, we hope that by including a wide range of real human cognitive profiles, both researchers and users will be encouraged to explore, understand, and learn from minds that are not usually easy to encounter or practice engaging with.

Ultimately, our long-term goal is to build systems that let us "walk up to" any being — of any kind, anywhere in the cosmos — and understand the potential for interaction. We want to recognize what its capacities and abilities are, what it may care about, what forms of communication are possible, what goals we might share, and what we can actually do together. 

This tool is a step toward that larger research objective. It gives us a controlled way to explore how radically different minds might meet, interpret one another, and discover the foundations of engagement.

## How does it work?
The system runs like a turn-based, text-only tabletop RPG. You play a character; the simulator plays another. Each turn, you describe an action, and the engine generates the next world step that includes any actions from simulated character.

Behind the scenes, every simulated response comes from a dedicated model trained to represent diverse cognitive systems. It takes your action, updates the world state, and replies in character, reflecting that system’s sensory limits, goals, and behavioral patterns.

A configurable game layer sits on top of this core. Researchers define the scenario, what information is hidden or revealed, and how the interaction should flow. Some games, for example, conceal the character’s type so the player must infer it through behavior alone.

In short: you take an action, the engine performs a world step through the simulation model, and the story advances — always in character.

The [Project Wiki](https://github.com/fuzzy-tribble/dcs-simulation-engine/wiki) offers more technical background.

## How can I use it?

### Try it instantly (no setup)
Anybody can play the Explore game via the live web demo.

[👉 Web Demo](https://dcs-free-play-ui.fly.dev/)

<img src="images/web-demo.png" alt="Web Demo">


### Developers

#### Python Setup

It is recommend that you use [uv](https://github.com/astral-sh/uv) to manage your Python environment. You can install it with

```sh
# install uv (if you don't have it already)
pip install uv

# install python 3.13 with uv
uv python install 3.13

# create a new virtual environment with uv
uv venv --python 3.13

# activate the virtual environment
source .venv/bin/activate

# installs dependencies and installs your current project in editable mode (similar to pip install -e .)
uv sync --extra dev
```

To run the engine locally, you will need to have Docker installed and running on your machine. You can download Docker Desktop from [docker.com](https://www.docker.com/get-started/).


#### Debugging

It is recommended to use the [vscode](https://code.visualstudio.com/) to debug the application. The `.vscode/tasks.json` file automatically handles stopping and starting the docker containers for you.

When you run the debug configuration, the application will create a new mongo database and seed it with the json files in `database_seeds/dev`.

> ⚠️ **Use `dev` as the access key for any game type that requires one.**


#### Tests

Currently, only functional tests are automated. You can run them with:

```sh
uv run pytest -m functional
```

#### API Usage

Programmatic API access is provided by the FastAPI + WebSocket `dcs-server`.

- Start server: `uv run dcs server`
- Start server in anonymous free play mode: `uv run dcs server --free-play`
- Docs: `http://localhost:8000/docs`
- Python client: `dcs_simulation_engine.client.DCSClient`

Manual usage examples are in `tests/api_manual`.


### Researchers

If you’re a researcher, you can design, run, and deploy your own experiments—create new games, add or modify characters, and explore different simulation setups.

The full Researcher User Guide lives in the wiki and walks through these options in detail.
[👉 Researcher User Guide](USER_GUIDE.md)

At a high level, the recommended way to work with the project is to install and run it directly from PyPI. This lets you create and launch custom games and experiments without modifying the core codebase.

- Install from Docker: Run the split Docker stack from [`compose.yaml`](compose.yaml) without installing the project locally. This is ideal if you want to test or demo the system with the packaged API and UI images.

Install the `dcs-simulation-engine` package from PyPI, create a new game or modify an existing one, test it locally then use the deploy script to launch it for others to play.

The [Researcher User Guide](USER_GUIDE.md) covers the complete workflow including game and character creation, validation, deployment and experimental result collection.

If you want to contribute to the engine itself--core characters, games, orchestration logic, or other codebase change--fork the repository and follow the Contributing Guide to set up the full codebase locally.

[👉 Contributing Guide](CONTRIBUTING.md)

## Future Directions
**Extending the character and scenario space**: The simulation engine currently supports a carefully curated set of characters and scenarios, designed to represent a diverse range of cognitive systems—from basal intelligence and human neurodivergence to temporary disabilities, robotic agents, and even alien-like intelligences. Each has been rigorously quality-checked to ensure their representation is high quality. As new use cases emerge and scenarios grow in complexity, we aim to expand this character and scenario space while maintaining the same high standards of quality and realism.

**Extending beyond narrative interface**: While the simulation engine’s core reasoning remains language-based (as explained in the Wiki), the top-level orchestration agent uses a modular, multi-modal agent graph. This design allows additional agents, models, and I/O interfaces to be integrated seamlessly.

For example, the system might normally generate a line such as “I whistle softly back slowly rising and falling off like a bell curve.” Instead of only producing text, that output could be routed to a dedicated audio model to generate the actual sound. Similarly it could receive an input that is described linguistically to the main reasoning system. In the future, we plan to add built-in support for microphone, audio, visual, and hopefuly tactile modules as the project expands and connects with other systems.

## Resources

- [GitHub Repo](https://github.com/fuzzy-tribble/dcs-simulation-engine) - the source code for the simulation engine (you are here)
- [Contributing Guide](CONTRIBUTING.md) - how to contribute to the project
- [Researcher User Guide](USER_GUIDE.md) - how to create, run, and deploy your own experiments
- [Project Wiki](https://github.com/fuzzy-tribble/dcs-simulation-engine/wiki) - background information on the project
- [Web Demo](https://dcs-free-play-ui.fly.dev) - try the simulation engine online
- [API Docs](https://dcs-simulation-demo.fly.io/docs) - interactive Swagger API documentation
- [Analysis Notebooks](analysis_notebooks/) - Jupyter notebooks containing anonymized analysis of simulation sessions
- [Contact](mailto:dcs@psych.gatech.edu) - get in touch with the maintainers for questions, suggestions, etc. using the "Issues" tab on GitHub or email
