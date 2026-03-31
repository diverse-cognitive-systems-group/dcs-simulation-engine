# Deployment

Each remote deployment creates three Fly apps: `db`, `api`, and `ui`.

## Quickstart (Example Real Deployment)

### 1) Prerequisites

- `flyctl` installed
- Fly.io account access
- `OPENROUTER_API_KEY`
- Experiment config YAML file
- `dcs` CLI available (or use `uv run dcs` from this repo)

### 2) Authenticate and set keys

```bash
flyctl auth login
export FLY_API_TOKEN=your-fly-token
export OPENROUTER_API_KEY=your-openrouter-key
```

### 3) Deploy

```bash
dcs remote deploy \
  --config path/to/example.yml \
  --mongo-seed-path database_seeds/prod \
  --region iad
```

After deploy, save the printed **admin key** to your `.env` file using `DCS_ADMIN_KEY=your-admin-key` or use `--admin-key` flag on remote following commands.

## Workflow Options

### Check status

```bash
dcs remote status \
  --uri https://dcs-example-api.fly.dev \
```

### Save database

Database can be saved at any time, independent of deployment or teardown.

```bash
dcs remote save \
  --uri https://dcs-example-api.fly.dev \
  --save-db-path example.zip
```

### Stop + destroy (with final save)

`remote stop` saves first; if save fails, app destruction does not proceed.

```bash
dcs remote stop \
  --uri https://dcs-example-api.fly.dev \
  --save-db-path example-final.zip \
  --api-app dcs-example-api \
  --ui-app dcs-example-ui \
  --db-app dcs-example-db
```

## Additional Deployment Options

### Free-play mode

```bash
dcs remote deploy \
  --free-play \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax
```

### Fallback regions

```bash
dcs remote deploy \
  --config /path/to/example.yaml \
  --mongo-seed-path database_seeds/dev \
  --regions lax,sjc,sea
```

Fly regions reference: https://fly.io/docs/reference/regions/

### Targeted redeploy

Redeploy only the UI app to a new region, keeping the same API and DB apps:

```bash
dcs remote deploy \
  --config /path/to/example.yaml \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax \
  --only-app ui
```

