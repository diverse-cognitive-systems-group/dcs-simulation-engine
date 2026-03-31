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

### 3) Generate admin key

```bash
dcs admin keygen
```

### 4) Deploy

```bash
dcs remote deploy \
  --admin-key dcs-ak-YOUR_KEY_HERE \
  --config path/to/run_config.yml \
  --mongo-seed-path database_seeds/prod \
  --region iad
```

After deploy, save the printed admin key. It is required for authenticated status checks, DB export, and teardown.

## Workflow Options

### Check status

```bash
dcs remote status \
  --uri https://dcs-experiment-a-api.fly.dev \
  --admin-key your-admin-key
```

### Save database

Database can be saved at any time, independent of deployment or teardown.

```bash
dcs remote save \
  --uri https://dcs-experiment-a-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path experiment-a.zip
```

### Stop + destroy (with final save)

`remote stop` saves first; if save fails, app destruction does not proceed.

```bash
dcs remote stop \
  --uri https://dcs-experiment-a-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path experiment-a-final.zip \
  --api-app dcs-experiment-a-api \
  --ui-app dcs-experiment-a-ui \
  --db-app dcs-experiment-a-db
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
  --config experiments/experiment-a.yaml \
  --mongo-seed-path database_seeds/dev \
  --regions lax,sjc,sea
```

Fly regions reference: https://fly.io/docs/reference/regions/

### Targeted redeploy

Redeploy only the UI app to a new region, keeping the same API and DB apps:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax \
  --only-app ui
```

