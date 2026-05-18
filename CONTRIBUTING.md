# Contributing Guidelines

> ⚠️ **Note: Use `dev` as the access key for any game type that requires one.**

## Prerequisites

1. Install Docker Desktop from [docker.com](https://www.docker.com/get-started/).
2. Get an OpenAI API key from [platform.openai.com](https://platform.openai.com/).

## 1. Checkout Code

If you have write access to the repository (i.e., DCS members), you can clone it directly (otherwise fork and clone your fork if you are an external contributor):

```sh
git clone https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine.git
cd dcs-simulation-engine
```

Then create a `.env` file from the example and add your API keys:

```sh
cp .env.example .env
```

_Note: DCS members can request access keys from a DCS group admin._

## 2. Open in VS Code Dev Container

This project includes a VS Code Dev Container for a consistent development environment.

Open the project in VS Code and select **“Reopen in Container”** when prompted. VS Code will build the image defined in `.devcontainer/dev.Dockerfile` and launch the container automatically.

### Verify `dcs` CLI is available

Use `dcs --help` in terminal from within the dev container and verify dcs cli is working.

## 3. Run the engine and clients + modify code

The DCS-SE stack include a database, the engine api and a couple client options (e.g., react ui for human players and autoplay client for AI models). 

#### Option 1: Use `dcs engine` commands
You can run it using the `dcs engine start/stop/status` commands which wrap docker compose up commands for starting up and tearning down each service in the correct order. (You can also just docker compose up/down the services yourself if you want.)

#### Option 2: Use VS Code launch configurations
You can also click on the "Run and Debug" tab in VS Code and select `dcs server XX` with whatever configuration you want to run. This starts the server locally using the run configuration specified in `.vscode/launch.json`.

Then you can start the ui in another terminal with:

```sh
cd ui
bun dev
```

#### Tests

You can run `make test`, `make lint`, etc. for ease or run specific tests with `uv run pytest tests/test_x.py`.

### Submit PR
Once you are done making changes and testing them, submit a pull request. Suggested PR format is 

#### Example PR Template
```md
# Overview

Currently, users must manually configure development environments and engine settings, which can make onboarding inconsistent and error-prone. This PR improves the developer experience by simplifying setup, clarifying documentation, and standardizing local workflows.

Addresses issue #000

## Changes

- Added a VS Code Dev Container configuration
- Improved Quickstart and setup documentation
- Clarified terminology around users, players, and runs
- Added example environment configuration instructions
- Cleaned up README wording and structure

## Test

- Built and launched the Dev Container in VS Code
- Verified local installation with `pip install`
- Ran the engine locally using configured API keys
- Confirmed updated documentation instructions work on macOS, Linux, and Windows workflows

```sh
uv run pytest tests/test_setup.py
```

## Notes

- No breaking API changes
- Documentation and onboarding focused PR
- Future improvements may include an interactive `dcs setup` command
```

---

Thank you for contributing!
