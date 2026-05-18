# Run the engine

The engine can be run locally and played just on your local computer or it can be run remotely (on an external server, called a "deployment") so that the access link can be shared with any player(s) (human or AI).

## Run locally

> Prerequisites for local runs include Docker installed and OpenRouter API key set in your environment variables or `.env` file. The `dcs` CLI will prompt you for these if you try to start a run without them.

```sh
dcs engine start --config path/to/config.yml
```

## Run remotely

By default the engine supports Fly.io for remote deployment however it is dockerized and can be deployed on any platform that supports Docker containers. 

> Prerequisites for remote deployment include a Fly.io account, `flyctl` installed, and an OpenRouter API key. The `dcs` CLI provides a streamlined interface for deploying to Fly.io, and the generated Fly configs can be adapted for other platforms as needed.

```sh
dcs remote deploy \
  --config path/to/config.yml \
  --mongo-seed-path dev \
```

The `dcs` CLI provides a streamlined interface for deploying to Fly.io, and the generated Fly configs can be adapted for other platforms as needed.

Each remote deployment creates three Fly apps: `db`, `api`, and `ui`.

After deploy, save the printed **admin key** to your `.env` file using `DCS_ADMIN_KEY=your-admin-key` or use `--admin-key` flag on remote following commands.

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
- The API is started with remote management enabled for the selected run config.
- The first admin key is claimed automatically during deployment and becomes the only key allowed to export the database.
- Database exports written by `dcs remote save` and `dcs database dump` include collection JSON plus manifest/index metadata, and those artifacts can be used again with `--mongo-seed-path`.
- When `--regions` is provided, deploy attempts the listed regions in order and uses the first region that succeeds.
- You can deploy multiple runs independently by running `dcs remote deploy` once per run config.
