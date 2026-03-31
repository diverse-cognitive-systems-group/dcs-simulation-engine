# Contributing Guidelines

## Prerequisites

### Install Docker

Install Docker Desktop from [docker.com](https://www.docker.com/get-started/).

Here’s a clean, updated version you can drop in:

## Checkout Code and Create `.env` File

If you have write access to the repository (i.e., DCS members), you can clone it directly (otherwise fork and clone your fork if you are an external contributor):

```sh
git clone https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine.git
cd dcs-simulation-engine
```

Then create your .env file:

```sh
cp .env.example .env
```

Add your access keys for MongoDB, OpenRouter, etc. (internal DCS members can request access keys from a DCS group admin).

## Open in VSCode Dev Container

We provide a dev container configuration for development in VS Code which automatically sets up a consistent development environment. Open the project in VS Code and click "Reopen in Container" when prompted. This will build the Docker image defined in `.devcontainer/dev.Dockerfile` and start a container with the project mounted inside.

### Verify Setup

Use `dcs --help` in terminal from within the dev container and verify dcs cli is working.

### Run locally

Click on the "Run and Debug" tab in VS Code and select the "dcs server" configuration. This starts the server locally using the run configuration specified in `.vscode/launch.json`.

Then you can start the ui in another terminal with:

```sh
cd ui
bun dev
```

The gui should now be available at `http://localhost:5173/`.

> ⚠️ **Use `dev` as the access key for any game type that requires one.**

#### Tests

Currently, only functional tests are automated. You can run them with:

```sh
uv run pytest -m functional
```

### Submit PR
Once you are done making changes and testing them, submit a pull request.

---

Thank you for contributing!
