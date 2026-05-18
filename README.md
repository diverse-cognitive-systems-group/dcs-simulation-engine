# Diverse Cognitive Systems (DCS) Simulation Engine 

*A playground for interacting with diverse cognitive systems.*

<a href="https://dcs-demo-ui.fly.dev" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/UI%20Demo-blue" alt="UI Demo"></a>
<a href="https://dcs-demo-api.fly.dev/docs" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/API%20Demo-blue" alt="API Demo"></a>
<a href="https://diverse-cognitive-systems-group.github.io/dcs-simulation-engine/" target="_blank" rel="noopener noreferrer"><img src="https://img.shields.io/badge/Docs-blue" alt="Documentation"></a>
[![Build Status](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/actions/workflows/ci.yml)

## What is this?

A gameplay framework for interacting with diverse cognitive systems, including neurodivergent humans, artificial intelligences, and hybrid systems.

![RPG-style DCS-SE gameplay](docs/assets/full-turn.gif)

Users configure the engine with games, scenarios, objectives, characters, and environments, then run simulations through various clients (such as a web UI for human players).

Within a collaborative improvisational environment, player characters and other simulated characters interact as a cast with distinct abilities, goals, and cognitive profiles. Interaction unfolds primarily through language — including action, imagination, communication, and world-building — in a format inspired by tabletop roleplaying games.

## How can I use it?

### Try web demo instantly (no setup)
[👉 Web Demo](https://dcs-demo-ui.fly.dev) for a time and rate limited version of the engine. No setup required.

### Quickstart
Alternatively, you can run the engine from your computer with your own API keys. 

#### 1. Install the package

```sh
pip install dcs-simulation-engine

# use --help after any dcs command to see usage info
dcs --help
```

#### 2. Set up API keys

Add your API keys to a local .env file or set them as environment variables. See `.env.example`.

#### 3. Run the engine

The first time you try and run it you will be prompted for your API keys if you haven't set them up in the `.env` file yet. You will also need to install [Docker](https://docs.docker.com/engine/install/) if you haven't already - the engine uses Docker containers to run the simulations.

```sh
dcs engine start --config examples/run_configs/demo.yml
```

Users can design, run, and deploy custom engine configurations—including their own games and characters.

[👉 Usage](https://diverse-cognitive-systems-group.github.io/dcs-simulation-engine/user_guide/overview.html) for the full user guide.

### Features

| Item | Supported | Notes |
|------|----------|------|
| Easy setup (pip, setup, run) | ✅ | Minimal friction onboarding |
| Out-of-the-box platform support | ✅ | Includes: built-in games & characters, default React web UI, autoplay client, local + Fly.io runs, reporting & analytics |
| Headless / modular usage | ✅ | Engine can run without default clients or deployment stack |
| Custom deployments & providers | ✅ | Containerized; deploy anywhere, plug in custom infra/UI |
| YAML run configurations | ✅ | Reproducible, config-driven runs |
| Configurable game parameters | ✅ | Optional game-specific configurations |
| Dev workflows & container | ✅ | Extensible + consistent onboarding |
| Example workflows | ✅ | Provided in `examples/` |
| Python game classes | ✅ | Flexible, expressive game logic |
| Game lifecycle validation | ✅ | Setup, step, finish, score |
| Python runtime performance | ⚠️ | Not ideal for ultra low-latency use cases; performant AI |

See <a href="https://diverse-cognitive-systems-group.github.io/dcs-simulation-engine/" target="_blank" rel="noopener noreferrer">docs</a> for more details on features, usage, and development.

---

_Developed and maintained by the Diverse Cognitive Systems (DCS) group at [Georgia Tech](https://www.gatech.edu/), within the [Sonification Lab](http://sonify.psych.gatech.edu/). Contact: [dcs@psych.gatech.edu](mailto:dcs@psych.gatech.edu)._
