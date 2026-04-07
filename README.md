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

## Why'd we build this?
Interfacing between different cognitive systems--even within the same species and cultures--is often difficult. **We lack reliable metrics for evaluating how well an AI, human, or any cognitive system understands the goals and perspectives of minds unlike its own.** 

This tool addresses that gap by modeling configurable interaction scenarios where humans, AI systems, and other characters — each with distinct sensory, perceptual, regulatory, and action modalities — can engage, coordinate, and uncover what the other cares about, how their goalspace is structured, and how to accomplish shared or competing objectives.

There’s also a social reason: divergent humans are, by definition, outliers in the bell curve and often underrepresented in everyday interaction. That makes communicating with fundamentally different minds an underdeveloped skill for many. Our simulated characters draw from real (neuro-) divergent humans, making aspects of their behavior more widely accessible to neurotypical individuals. While the primary purpose of this tool is research, we hope that by including a wide range of real human cognitive profiles, both researchers and users will be encouraged to explore, understand, and learn from minds that are not usually easy to encounter or practice engaging with.

Ultimately, our long-term goal is to build systems that let us "walk up to" any being — of any kind, anywhere in the cosmos — and understand the potential for interaction. We want to recognize what its capacities and abilities are, what it may care about, what forms of communication are possible, what goals we might share, and what we can actually do together. 

This tool is a step toward that larger research objective. It gives us a controlled way to explore how radically different minds might meet, interpret one another, and discover the foundations of engagement.

## How does it work?
The system runs like a turn-based, text-only tabletop role playing game (RPG). You play a character; the simulator plays another. Each turn, you describe an action, and the engine generates the next world step that includes any actions from simulated character.

Behind the scenes, every simulated response comes from a dedicated model trained generated bounded representations of diverse cognitive systems. It takes your action, updates the world state, and replies in character, reflecting that system’s sensory limits, goals, and behavioral patterns.

A configurable game layer sits on top of this core. The scenario, what information is hidden or revealed, and how the interaction should flow is configurable. Some games, for example, conceal the character’s type so the player must infer it through behavior alone.

In short: you take an action, the engine performs a world step through the simulation model, and the story advances — always in character.

## Contact

Get in touch with the maintainers by creating an [issue](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/issues) on GitHub or [emailing us](mailto:dcs@psych.gatech.edu).
