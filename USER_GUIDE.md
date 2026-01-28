# User Guide

The DCS Simulation Engine is a CLI-driven framework for running and managing interactive games involving diverse cognitive systems.

It is used by:
- Researchers (including internal DCS teams) designing experiments to study cognition across conditions and scenarios
- Team leaders and educators training groups in diverse engagement and decision-making
- AI practitioners using games as a sandbox for agent learning and evaluation

Users can run games locally, deploy them for live participation (human or AI), extend the system with custom characters and games, and collect structured results.

## Installation (PyPI)

Install the engine and verify the CLI.

```sh
pip install dcs-simulation-engine

dcs --version
dcs --help
```

## Quick start

To enable roleplaying models, add your OpenRouter API key to a .env file in the directory where you run the `dcs` commands:

```sh
OPENROUTER_API_KEY=...
```

Run a game locally:

```sh
dcs game list
dcs game run explore
```

## Core Workflow

Users design, run, deploy, and manage games using the CLI.

A game may be run locally for exploration or training, or deployed live to collect structured interactions from human or AI participants.

The CLI follows a noun-centric structure:

```sh
dcs <entity> <action>
```

where primary entities include `game`, `deployment`, and `character`.

#### Discover available games
List all known games and their descriptions:

```sh
dcs game list
```

#### Run a game locally

Run a game locally using default settings:

```sh
dcs game run <game_name>
```

Local runs are useful for:
- Exploration and debugging
- Training or rehearsal before live deployment
- Development of new characters or games

Use `--help` to see all available options.

#### Deploy a game (make it live)

Create a live deployment for participation and data collection:

```sh
dcs game deploy <game_name>
```

Deployments are used to:
- Collect data from human or AI players
- Run structured studies or training sessions
- Share a live game with others via a URL

#### Manage deployments

View your running and completed deploymnents:

```sh
dcs deployment list
```

Stop a live deployment and collect results:

```sh
dcs deployment stop <deployment_name>
```

### Extend the system with custom characters

Create a new character using an interactive workflow:

```sh
dcs character create
```

Validate a character definition and generate a QA notebook:

```sh
dcs character validate <character_name>
```

To suggest inclusion in the core character set, open an issue on [the GitHub repo](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/issues) with:
- Character definition
- Validation outputs and notebook pdf exports attached

### Extend the system with new games

Create a new game scaffold:

```sh
dcs game create <game_name>
```

Validate a game definition:

```sh
dcs game validate <game_name>
```

### Note on terminology

The engine intentionally uses games as the primary abstraction.

Whether a game deployment functions as an experiment, training exercise, or learning sandbox is left to the user.