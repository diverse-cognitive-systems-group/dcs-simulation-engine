# Overview

A flexible gameplay framework that lets users define, run, and analyze interactions between diverse cognitive systems to study and improve meaningful engagement.

Our primary goal is to enable training and research on how humans and AI systems can better configure and mediate interactions across cognitive differences.

We use the following terminology:

- **Users** use the CLI tools to run the engine and/or define new games and characters. They can be researchers, team leaders, educators, AI practitioners, or anyone interested in exploring interactions between diverse cognitive systems.

- **Players** are the human or AI participants who interact with the using a player character (PC) system via the web UI or API.

- **Characters** are all possible cognitive systems that the player or simulator can use as a PC or NPC (non-player character). They can have different goals, sensory, perceptual, regulatory, and motor/action modalities.

- **Games** are python files that define the flow of an interaction (what scenarios, objectives, characters, etc.)

- **Run configs** define the configurations for running the engine (e.g., which game, which characters, how many players, etc.). See `examples/run_configs/` for examples.

## Workflow Example

Users decide to run the engine (e.g., for training or research purposes) using CLI --> they use existing games with default characters or define their own --> if configured for human players, they share the gameplay link with players; if configured for AI players, they use the run harness with their model or manually play via API --> users start/monitor and stop the engine and then analyze results data.

## Foundational Studies

Foundational studies including usability, quality and baseline performance benchmarking for human and AI players are maintained and refreshed ...
