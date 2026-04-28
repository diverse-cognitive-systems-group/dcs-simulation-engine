# Deploy To Fly.io

This guide covers the current remote deployment flow for a full DCS stack on
Fly.io:

- MongoDB
- API
- UI

Each deployment creates three separate Fly apps.

If you are running from this repository, prefix the commands below with
`uv run` unless `dcs` is already installed in your active environment.

## Prerequisites

- `flyctl`
- access to a Fly.io account
- `OPENROUTER_API_KEY`
- a Mongo seed source such as `database_seeds/dev` or an export archive
- a valid experiment config if you are deploying experiment mode

Authenticate first:

```bash
flyctl auth login
export FLY_API_TOKEN=your-fly-token
export OPENROUTER_API_KEY=your-openrouter-key
```

## Deploy An Experiment

The shipped experiment config in this repo is `experiments/usability.yml`.

```bash
uv run dcs remote deploy \
  --config experiments/usability.yml \
  --mongo-seed-path database_seeds/dev \
  --region lax
```

If deploy succeeds, the CLI prints:

- the deployment name
- the API URL
- the UI URL
- the concrete Fly app names
- the remote admin key
- ready-to-run `status`, `save`, and `stop` commands

Save the admin key immediately. It is required for later lifecycle commands.

## Deploy Free Play

```bash
uv run dcs remote deploy \
  --free-play \
  --mongo-seed-path database_seeds/dev \
  --region lax
```

Use free play when you want an anonymous public stack without experiment forms
or assignment flow.

## Region Selection

Use `--region` when you want one target region:

```bash
uv run dcs remote deploy \
  --config experiments/usability.yml \
  --mongo-seed-path database_seeds/dev \
  --region lax
```

Use `--regions` when you want ordered fallback across multiple Fly regions:

```bash
uv run dcs remote deploy \
  --config experiments/usability.yml \
  --mongo-seed-path database_seeds/dev \
  --regions lax sjc dfw
```

The current CLI expects separate region arguments after `--regions`. Do not use
the older comma-separated form.

## Optional Admin Key

Generate a deployment-ready key if you want to control it explicitly:

```bash
uv run dcs admin keygen
```

Then pass it during deploy:

```bash
uv run dcs remote deploy \
  --config experiments/usability.yml \
  --mongo-seed-path database_seeds/dev \
  --admin-key dcs-ak-your-generated-key \
  --region lax
```

## Targeted Redeploys

Redeploy only selected apps by repeating `--only-app`:

```bash
uv run dcs remote deploy \
  --config experiments/usability.yml \
  --mongo-seed-path database_seeds/dev \
  --region lax \
  --only-app ui
```

When you use `--only-app`, the command redeploys only those apps and does not
re-bootstrap the deployment or issue a new admin key.

## Custom App Names

If you do not provide names, Fly app names are derived automatically:

```text
dcs-<experiment-slug>-api
dcs-<experiment-slug>-ui
dcs-<experiment-slug>-db
```

For free play, the defaults are:

```text
dcs-free-play-api
dcs-free-play-ui
dcs-free-play-db
```

You can override them:

```bash
uv run dcs remote deploy \
  --config experiments/usability.yml \
  --mongo-seed-path database_seeds/dev \
  --region lax \
  --api-app my-usability-api \
  --ui-app my-usability-ui \
  --db-app my-usability-db
```

## Check Deployment Status

```bash
uv run dcs remote status \
  --uri https://dcs-usability-api.fly.dev \
  --admin-key your-admin-key
```

For lower-level Fly state:

```bash
flyctl machine list --app dcs-usability-api
flyctl machine list --app dcs-usability-ui
flyctl machine list --app dcs-usability-db
```

## Save The Remote Database

```bash
uv run dcs remote save \
  --uri https://dcs-usability-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path results/usability-export.zip
```

The saved `.zip` or `.tar.gz` archive can be reused later as
`--mongo-seed-path` for a fresh deploy.

## Stop And Destroy The Deployment

`remote stop` always saves first. If the save step fails, the Fly apps are not
destroyed.

```bash
uv run dcs remote stop \
  --uri https://dcs-usability-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path results/usability-final.zip \
  --api-app dcs-usability-api \
  --ui-app dcs-usability-ui \
  --db-app dcs-usability-db
```

## Notes
- Generated Fly configs are written to `deployments/<deployment-slug>/` each time you run `dcs remote deploy`, and deploy uses those saved files directly.
- No local deployment manifest is written beyond those generated Fly config files. Keep the deploy output or use `--json` and store it yourself.
- The UI is built for the paired API automatically during deploy.
- The API is started in remote-managed mode for either one hosted experiment or free-play mode.
- The first admin key is claimed automatically during deployment and becomes the only key allowed to export the database.
- Database exports written by `dcs remote save` and `dcs dump` include collection JSON plus manifest/index metadata, and those artifacts can be used again with `--mongo-seed-path`.
- When `--regions` is provided, deploy attempts the listed regions in order and uses the first region that succeeds.
- You can deploy multiple experiments independently by running `dcs remote deploy` once per experiment config, or deploy one free-play stack with `--free-play`.
