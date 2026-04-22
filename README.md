🚧 NOTICE: This is a W.I.P. (official releases will be tagged and licensed when ready)

# Diverse Cognitive Systems (DCS) Simulation Engine 

*A playground for engaging with diverse cognitive systems.*

[![Web Demo](https://img.shields.io/badge/Web%20Demo-blue)](https://dcs-free-play-ui.fly.dev)
[![API Demo](https://img.shields.io/badge/API%20Demo-blue)](https://dcs-free-play-api.fly.dev/docs)
[![Documentation](https://img.shields.io/badge/Docs-blue)](https://diverse-cognitive-systems-group.github.io/dcs-simulation-engine/)
[![Build Status](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/actions/workflows/ci.yml)

## What is this?

A gameplay framework for engaging with diverse cognitive systems (neurodivergent humans, artificial intelligences, etc.).

Users—researchers or anyone curious about how different minds interact—can choose from core games and characters, or create their own, then launch the system for AI or human players to access via the web.

Within a collaborative, improv arena, player characters (PCs) and simulated characters (NPCs) interact as a cast with distinct abilities and cognitive profiles. Everything unfolds through language—action, imagination, and world-building—in a format inspired by tabletop roleplaying games.

## How can I use it?

### Try web demo instantly (no setup)
Anybody can play the core games via the live web demo for free *(the demo has limits, so it may be slower—run it locally with your own API keys for full speed and features).*

[👉 Web Demo](https://dcs-free-play-ui.fly.dev)

### Run locally with Docker (quickstart)
Anybody can run the full stack locally with Docker and their own API keys. 

Install [Docker](https://docs.docker.com/engine/install/) following the instructions for your operating system.

Configure your API keys in the `.env` file. You can copy the `.env.example` file and fill in your keys there.

Run the full stack with the commands below. 

*The build may take a few minutes the first time you run the command.*

```sh
# start the app
docker compose up --build --detach

# go to http://localhost:5173 to view the ui

# teardown
docker compose down --volumes

# the entire state of the database in store in a timestamped folder
ls ./runs
```

Users can design, run, and deploy custom engine configurations—including their own games and characters.

[👉 Usage](USAGE.md) for detailed instructions.

### Features

| Item | Supported | Notes |
|------|----------|------|
| Easy setup (pip, API keys, run) | ✅ | Minimal friction onboarding |
| Out-of-the-box platform support | ✅ | Includes: built-in games & characters, React UI, local + Fly.io runs, reporting & analytics |
| Headless / modular usage | ✅ | Engine can run without UI or default deployment stack |
| Custom deployments & providers | ✅ | Containerized; deploy anywhere, plug in custom infra/UI |
| YAML run configurations | ✅ | Reproducible, config-driven runs |
| Configurable game parameters | ✅ | Optional game-specific configurations |
| Dev workflows & container | ✅ | Extensible + consistent onboarding |
| Example workflows | ✅ | Provided in `examples/` |
| Python game classes | ✅ | Flexible, expressive game logic |
| Game lifecycle validation | ✅ | Setup, step, finish, evaluate |
| Python runtime performance | ❌ | Not ideal for ultra low-latency use cases; performant AI |
| Multi-character interactions | ❌ | Not fully implemented yet |

## Contact

Get in touch with the maintainers by creating an [issue](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/issues) on GitHub or [emailing us](mailto:dcs@psych.gatech.edu).
