# Docker Setup

The Docker stack now runs as three separate services:

- `mongo`: upstream `mongo:8.0`
- `api`: Python server image built from [`docker/api.dockerfile`](./api.dockerfile)
- `ui`: Bun/Vite UI image built from [`docker/ui.dockerfile`](./ui.dockerfile)

This replaces the older all-in-one container that bundled MongoDB, the API, and
the Vite dev server under `supervisord`.

## Why Split It

Each service now owns one responsibility:

- MongoDB stays on the standard upstream image instead of being embedded in the app container.
- The API image installs Python dependencies once and runs `dcs server`.
- The UI image runs the same Bun/Vite workflow we use locally from the `ui/` folder.

That gives us simpler process management, more realistic production behavior,
and cleaner deploy/scale boundaries.

## How Routing Works

The browser talks to the UI container on `http://localhost:5173`.

Inside Docker, Vite proxies HTTP `/api/*` requests to the API service using
`VITE_API_PROXY_TARGET=http://api:8000`. Gameplay WebSockets still connect from
the browser to `ws://<host>:8000`, which works because the API container is
published directly on port `8000`.

## Compose

[`compose.yaml`](../compose.yaml) is the main entrypoint for the local stack.

```sh
docker compose up --build
```

Services:

- UI: `http://localhost:5173`
- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- MongoDB: `mongodb://localhost:27017`

The compose file always seeds Mongo from `/app/database_seeds/dev` and can run
in either standard mode or anonymous free-play mode:

```yaml
command:
  [
    "/bin/sh",
    "-c",
    "exec /app/.venv/bin/dcs server --mongo-seed-dir /app/database_seeds/dev ${DCS_FREE_PLAY:+--free-play}",
  ]
```

The API service bind-mounts `./runs` to `/app/runs`, so shutdown dumps written
with `--dump ./runs` appear in the repo's local `runs/` directory on the host.

Use standard mode by default:

```sh
OPENROUTER_API_KEY=... docker compose up --build
```

Enable free-play mode by setting `DCS_FREE_PLAY=1`:

```sh
OPENROUTER_API_KEY=... DCS_FREE_PLAY=1 docker compose up --build
```

## Environment

The API container requires `OPENROUTER_API_KEY`. Compose will fail fast during
startup if the variable is missing. Set it in your shell or `.env` file:

```sh
OPENROUTER_API_KEY=... docker compose up --build
```

## Image Notes

### API image

The API image runs from the source tree instead of a wheel-only install. That
keeps repo-relative assets available inside the container:

- `games/`
- `experiments/`
- `database_seeds/`

### UI image

The UI image installs Bun dependencies from the `ui/` folder and starts the
Vite dev server with:

```sh
bun run dev --host 0.0.0.0
```

That keeps Docker aligned with the existing frontend workflow instead of
introducing a separate nginx-only runtime path.
