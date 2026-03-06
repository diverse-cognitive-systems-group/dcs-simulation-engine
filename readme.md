# DCS Simulation Engine

`db`, `core`, and `ui` directories are all separate packages

# Quick Start

```sh
# start database container
docker compose down --volumes && docker compose up -d

# deploy schema
cd db && uv run alembic upgrade head

# start api/server
uv run uvicorn dcs_simulation_engine.api.app:app --reload

# start ui
cd ui && uv run dcs-ui
```

