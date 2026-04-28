# Run The Engine Locally

This page covers the current **local** workflows:

- VS Code devcontainer
- local shell workflow outside VS Code
- Docker Compose quickstart

> For remote deployment to Fly.io, see [Deployment](deployment.md).

All three expose the same core endpoints:

- UI: `http://localhost:5173`
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

For Fly.io deployment, use [Deployment](deployment.md).

## Option 1: Run In VS Code

The repo already includes a devcontainer plus launch/tasks configuration.

### Prerequisites

- VS Code
- Docker Desktop or an equivalent local Docker engine
- the Dev Containers extension

### Workflow

1. Open the repository in the devcontainer.
2. Wait for `postCreateCommand` to finish:
   - `uv sync --extra dev`
   - `cd /app/ui && bun install`
3. Open **Run and Debug** in VS Code.
4. Choose one of the shipped launch configurations:
   - `dcs server`: standard mode with `--default-experiment usability`
   - `dcs server freeplay`: anonymous free-play mode
5. Start the launch configuration. VS Code runs the `start-mongo` task first,
   which brings up Mongo from `.devcontainer/dev.compose.yml`.
6. Open a terminal in the devcontainer and start the UI:

```bash
cd ui
bun run dev
```

7. Open `http://localhost:5173` in your browser.

### What VS Code Automates

- `start-mongo` runs `docker compose -f .devcontainer/dev.compose.yml up --detach`
- `stop-mongo` runs when you stop debugging. It:
  - dumps the database with `dcs dump ./runs`
  - tears Mongo down with `docker compose -f .devcontainer/dev.compose.yml down --volumes`

If you use the `dcs server` launch configuration, the UI will route players into
the shipped `usability` experiment automatically.

## Option 2: Run Outside VS Code

This is the closest manual equivalent to the VS Code workflow.

### Prerequisites

- Python `3.13`
- `uv`
- `bun`
- Docker
- `OPENROUTER_API_KEY`

### One-Time Setup

```bash
uv sync --extra dev
cd ui
bun install
cd ..
```

### Start Mongo

```bash
docker compose -f .devcontainer/dev.compose.yml up --detach
```

### Start The API

Standard mode with the shipped `usability` experiment:

```bash
uv run dcs server \
  --mongo-seed-dir database_seeds/dev \
  --dump ./runs \
  --default-experiment usability
```

Anonymous free-play mode:

```bash
uv run dcs server \
  --mongo-seed-dir database_seeds/dev \
  --dump ./runs \
  --free-play
```

### Start The UI

In a second terminal:

```bash
cd ui
bun run dev
```

### Stop Cleanly

- Stop the API server with `Ctrl+C`. If you passed `--dump ./runs`, shutdown
  writes a fresh timestamped dump automatically.
- Tear down Mongo:

```bash
docker compose -f .devcontainer/dev.compose.yml down --volumes
```

If you did not run the server with `--dump`, export the database manually
before removing Mongo:

```bash
uv run dcs dump ./runs
```

## Option 3: Docker Compose Quickstart

Use this when you want the whole local stack quickly and do not need the VS
Code debug flow.

### Start

```bash
OPENROUTER_API_KEY=your-openrouter-key docker compose up --build --detach
```

Anonymous free-play mode:

```bash
OPENROUTER_API_KEY=your-openrouter-key \
DCS_FREE_PLAY=1 \
docker compose up --build --detach
```

### Notes

- The Compose stack seeds Mongo from `database_seeds/dev`.
- The API container always runs with `--dump ./runs`, so shutdown dumps appear
  in the host `runs/` directory.
- Standard-mode Compose runs do not set `--default-experiment`, so players can
  register and browse games without being pinned to one experiment.

### Stop

```bash
docker compose down --volumes
```

## Choosing A Local Mode

- Use standard mode when you need registration, sign-in, or experiment-specific
  forms and assignment flows.
- Use free play when you want the fastest local human-play smoke test.
- Use `--fake-ai-response "..."` with either local shell workflow when you want
  deterministic local testing without live model calls.



