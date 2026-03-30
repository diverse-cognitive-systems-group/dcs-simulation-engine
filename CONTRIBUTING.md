# Contributing Guidelines

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

---OLD README CONTENT BELOW---

## Prerequisites

### Docker Setup

To run the engine locally, you will need to have Docker installed and running on your machine. You can download Docker Desktop from [docker.com](https://www.docker.com/get-started/).

### `.env` file

Create a .env file in the root of the project. (Just copy the .env.example file and rename it to .env then add your access keys for MongoDB, OpenRouter, etc.) Request access keys from a DCS group admin.

## Dev Container Setup

We provide a dev container configuration for development in VS Code which automatically sets up a consistent development environment. Open the project in VS Code and click "Reopen in Container" when prompted. This will build the Docker image defined in `.devcontainer/dev.Dockerfile` and start a container with the project mounted inside.

## Verify Setup

Use the `dcs server` or `dcs server freeplay` debug targets to run the server locally. This will start the database, and server.

The ui must be manually started. You can do this with 
```sh
cd ui
bun dev
```

To verify everything is working, run the tests

```sh
make test
```

The entire state of the database is stored in a timestamped folder in `./runs` each time you stop the stack.

## PR Workflow

### Make changes
Make whatever changes you want to the codebase. Create new branches for your changes and commit your changes with clear commit messages.

- Make sure to thoroughly test your changes locally before submitting a PR.

### Submit PR
Once you are done making changes and want to submit a PR you can do in the "Source Control" tab in VS-code (or use git commands in terminal or the GitHub web interface if you prefer).

From the Source Control tab in your branch you click the "Create Pull Request" button to open the PR creation page.

---

Thank you for contributing!
