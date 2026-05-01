# Run the engine

⚠️ Note: This page is incomplete and/or missing information.

The engine can be run locally and played just on your local computer or it can be run remotely (on an external server, called a "deployment") so that the access link can be shared any player(s) (human or AI).

## Run locally

TODO: complete localy deployment instructions when CLI is finalized

## Run remotely (deployment)

By default the engine supports Fly.io for remote deployment however it is dockerized and can be deployed on any platform that supports Docker containers. 

The `dcs` CLI provides a streamlined interface for deploying to Fly.io, and the generated Fly configs can be adapted for other platforms as needed.

Each remote deployment creates three Fly apps: `db`, `api`, and `ui`.

### Example Real Deployment (quickstart)

#### 1) Prerequisites

- `flyctl` installed
- Fly.io account access
- `OPENROUTER_API_KEY`
- Run config YAML file
- `dcs` CLI available (or use `uv run dcs` from this repo)

#### 2) Authenticate and set keys

```bash
flyctl auth login
export FLY_API_TOKEN=your-fly-token
export OPENROUTER_API_KEY=your-openrouter-key
```

#### 3) Deploy

```bash
dcs remote deploy \
  --config path/to/example.yml \
  --mongo-seed-path database_seeds/prod \
  --region iad
```

After deploy, save the printed **admin key** to your `.env` file using `DCS_ADMIN_KEY=your-admin-key` or use `--admin-key` flag on remote following commands.

### Workflow Options

#### Check status

```bash
dcs remote status \
  --uri https://dcs-example-api.fly.dev \
```

#### Save database

Database can be saved at any time, independent of deployment or teardown.

```bash
dcs remote save \
  --uri https://dcs-example-api.fly.dev \
  --save-db-path example.zip
```

#### Stop + destroy (with final save)

`remote stop` saves first; if save fails, app destruction does not proceed.

```bash
dcs remote stop \
  --uri https://dcs-example-api.fly.dev \
  --save-db-path example-final.zip \
  --api-app dcs-example-api \
  --ui-app dcs-example-ui \
  --db-app dcs-example-db
```

### Additional Deployment Options

#### Anonymous demo run

Deploy any run config with `ui.registration_required: false` to allow players
to enter through automatically issued anonymous access keys.

```bash
dcs remote deploy \
  --config examples/run_configs/demo.yml \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax
```

#### Fallback regions

```bash
dcs remote deploy \
  --config /path/to/example.yaml \
  --mongo-seed-path database_seeds/dev \
  --regions lax,sjc,sea
```

Fly regions reference: https://fly.io/docs/reference/regions/

#### Targeted redeploy

Redeploy only the UI app to a new region, keeping the same API and DB apps:

```bash
dcs remote deploy \
  --config /path/to/example.yaml \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax \
  --only-app ui
```

### Additional Notes
- Generated Fly configs are written to `deployments/<deployment-slug>/` each time you run `dcs remote deploy`, and deploy uses those saved files directly.
- No local deployment manifest is written beyond those generated Fly config files. Keep the deploy output or use `--json` and store it yourself.
- The UI is built for the paired API automatically during deploy.
- The API is started in remote-managed mode for the selected run config.
- The first admin key is claimed automatically during deployment and becomes the only key allowed to export the database.
- Database exports written by `dcs remote save` and `dcs dump` include collection JSON plus manifest/index metadata, and those artifacts can be used again with `--mongo-seed-path`.
- When `--regions` is provided, deploy attempts the listed regions in order and uses the first region that succeeds.
- You can deploy multiple runs independently by running `dcs remote deploy` once per run config.
