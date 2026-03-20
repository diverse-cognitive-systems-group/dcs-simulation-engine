# Deployment

This guide covers the new Fly.io-based remote deployment flow for a full DCS stack:

- MongoDB
- API
- UI

Each remote deployment is created as three separate Fly apps.

## Prerequisites

- `flyctl` is installed and available on your `PATH`
- You have access to a Fly.io account
- You have an OpenRouter API key
- You have an experiment config YAML file for experiment mode
- You have the DCS CLI available as `dcs`

If you are running from this repository without installing the CLI globally, use `uv run dcs` in place of `dcs` in the examples below.

Authenticate Fly locally or provide a token through the environment:

```bash
flyctl auth login
export FLY_API_TOKEN=your-fly-token
export OPENROUTER_API_KEY=your-openrouter-key
```


## Deploy The Full Stack

The full remote deployment is a single command:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path database_seeds/dev \
  --region lax
```

If you want ordered fallback attempts across multiple Fly regions, use
`--regions` instead:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path database_seeds/dev \
  --regions lax,sjc,sea
```

The CLI tries each listed region in order and stops on the first successful
deployment attempt.

Free-play deployments use `--free-play` instead of `--config`:

```bash
dcs remote deploy \
  --free-play \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax
```

If you want to install a specific admin key during deployment, generate one first:

```bash
dcs admin keygen
```

Then pass it to deploy:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path backups/usability-ca.tar.gz \
  --admin-key dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU \
  --region lax
```

Required flags:

- `--config`: path to the experiment YAML file, unless using `--free-play`
- `--free-play`: deploy anonymous free-play mode instead of experiment mode
- `--mongo-seed-path`: local seed source for Mongo bootstrap
  Supported values: a directory of `.json`/`.ndjson` files, a single `.json`/`.ndjson` file, or a `.zip`/`.tar.gz` backup archive
- `--openrouter-key`: optional if `OPENROUTER_API_KEY` is already set
- `--fly-io-key`: optional if `FLY_API_TOKEN` is already set or `flyctl` is already authenticated

Optional flags:

- `--region`: Fly primary region, for example `sea`
- `--regions`: comma-separated ordered fallback list of Fly regions to try, for example `lax,sjc,sea`
- `--admin-key`: optional explicit remote admin key to install during bootstrap
- `--only-app`: redeploy only specific app targets (`db`, `api`, `ui`); repeat the flag to deploy multiple apps
- `--api-app`: explicit API Fly app name
- `--ui-app`: explicit UI Fly app name
- `--db-app`: explicit DB Fly app name
- `--json`: print machine-readable output instead of the human-friendly summary

Use `--region` when you want exactly one target region, or `--regions` when you
want the deploy command to retry across multiple regions in order.

Example with explicit credentials passed directly:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path backups/usability-ca.tar.gz \
  --region lax \
  --openrouter-key your-openrouter-key \
  --fly-io-key your-fly-token
```

Example free-play deployment with an explicit admin key:

```bash
dcs remote deploy \
  --free-play \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --admin-key dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU \
  --region lax
```

Example with custom Fly app names:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path database_seeds/dev \
  --region lax \
  --api-app experiment-a-api \
  --ui-app experiment-a-ui \
  --db-app experiment-a-db
```

Example with fallback regions:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path database_seeds/dev \
  --regions lax sjc sea
```

Example targeted redeploy of just the UI app:

```bash
dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --region lax \
  --only-app ui
```

When you use `--only-app`, the command redeploys only those app(s) and does not re-bootstrap the remote deployment or issue a new admin key.

If you do not provide app names, the CLI derives them automatically:

```text
dcs-<experiment-slug>-api
dcs-<experiment-slug>-ui
dcs-<experiment-slug>-db
```

For free-play mode, the derived names are:

```text
dcs-free-play-api
dcs-free-play-ui
dcs-free-play-db
```

## What Deploy Prints

After a successful deploy, the CLI prints:

- the deployment name
- the API URL
- the UI URL
- the concrete Fly app names for API, UI, and DB
- the admin access key
- ready-to-run `status`, `save`, and `stop` commands

Save the admin access key somewhere safe. It is required for authenticated remote status, database export, and teardown. The first deploy output shows it once.

If you supplied `--admin-key`, that exact key becomes the deployed remote admin key. If you omit it, deploy generates one for you and prints it once.

## Check Status

Use the API URL and saved admin key returned by deploy:

```bash
dcs remote status \
  --uri https://dcs-experiment-a-api.fly.dev \
  --admin-key your-admin-key
```

This prints the authenticated status payload for the hosted deployment:

- experiment mode: `/api/experiments/<experiment>/status`
- free-play mode: `/api/remote/status`

For detailed Fly container state, use:

```bash
flyctl machine list --app dcs-experiment-a-api
flyctl machine list --app dcs-experiment-a-ui
flyctl machine list --app dcs-experiment-a-db
```

## Save The Database

Download the remote database state as a local `.tar.gz` or `.zip` archive:

```bash
dcs remote save \
  --uri https://dcs-experiment-a-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path experiment-a.zip
```

The archive contains the exported JSON dump produced by the API. The format is chosen from the filename extension.

Exports created by `dcs remote save` or `dcs dump` can be reused later as `--mongo-seed-path` values for a fresh deployment.

## Stop And Destroy The Deployment

`remote stop` always saves the database first. If the save fails, the Fly apps are not destroyed.

```bash
dcs remote stop \
  --uri https://dcs-experiment-a-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path experiment-a-final.zip \
  --api-app dcs-experiment-a-api \
  --ui-app dcs-experiment-a-ui \
  --db-app dcs-experiment-a-db
```

After a successful stop:

- the database export is written locally
- the UI Fly app is destroyed
- the API Fly app is destroyed
- the DB Fly app is destroyed

After destruction, the saved API URL is no longer expected to answer `dcs remote status`, because the API app itself has been removed.

## Notes

- Generated Fly configs are written to `deployments/<deployment-slug>/` each time you run `dcs remote deploy`, and deploy uses those saved files directly.
- No local deployment manifest is written beyond those generated Fly config files. Keep the deploy output or use `--json` and store it yourself.
- The UI is built for the paired API automatically during deploy.
- The API is started in remote-managed mode for either one hosted experiment or free-play mode.
- The first admin key is claimed automatically during deployment and becomes the only key allowed to export the database.
- Database exports written by `dcs remote save` and `dcs dump` include collection JSON plus manifest/index metadata, and those artifacts can be used again with `--mongo-seed-path`.
- When `--regions` is provided, deploy attempts the listed regions in order and uses the first region that succeeds.
- You can deploy multiple experiments independently by running `dcs remote deploy` once per experiment config, or deploy one free-play stack with `--free-play`.

## Repo Checkout Usage

If you are running directly from this repository, the same flow usually looks like:

```bash
export OPENROUTER_API_KEY=your-openrouter-key
export FLY_API_TOKEN=your-fly-token

uv run dcs remote deploy \
  --config experiments/experiment-a.yaml \
  --mongo-seed-path database_seeds/dev \
  --regions lax,sjc,sea
```

Repo checkout example for free-play with an explicit admin key:

```bash
export OPENROUTER_API_KEY=your-openrouter-key
export FLY_API_TOKEN=your-fly-token

uv run dcs remote deploy \
  --free-play \
  --mongo-seed-path dump/2026_03_20_07_35_09 \
  --admin-key dcs-ak-r9kc-B9kmhuyV85tUWIcl8KHrPl_HO7Z3BnAlcgMtJU \
  --region lax
```


## Fly Regions

[fly.io regions](https://fly.io/docs/reference/regions/)

| Region ID | Region Location | Gateway |
| --- | --- | --- |
| `ams` | Amsterdam, Netherlands | ✅ |
| `arn` | Stockholm, Sweden | ✅ |
| `bom` | Mumbai, India | ✅ |
| `cdg` | Paris, France | ✅ |
| `dfw` | Dallas, Texas (US) | ✅ |
| `ewr` | Secaucus, NJ (US) | ✅ |
| `fra` | Frankfurt, Germany | ✅ |
| `gru` | Sao Paulo, Brazil |  |
| `iad` | Ashburn, Virginia (US) | ✅ |
| `jnb` | Johannesburg, South Africa |  |
| `lax` | Los Angeles, California (US) | ✅ |
| `lhr` | London, United Kingdom | ✅ |
| `nrt` | Tokyo, Japan | ✅ |
| `ord` | Chicago, Illinois (US) | ✅ |
| `sin` | Singapore, Singapore | ✅ |
| `sjc` | San Jose, California (US) | ✅ |
| `syd` | Sydney, Australia | ✅ |
| `yyz` | Toronto, Canada | ✅ |

# Example Real Deployment

```bash
# generate an admin key
dcs admin keygen

# deploy usability-ca experiment with the generated admin key and fallback regions
dcs remote deploy \
  --admin-key dcs-ak-YOUR_KEY_HERE \
  --config /experiments/usability-ca.yml \
  --mongo-seed-path database_seeds/prod \
  --regions lax sjc sea

# deploy free play
dcs remote deploy \
  --admin-key dcs-ak-YOUR_KEY_HERE \
  --free-play \
  --mongo-seed-path database_seeds/prod \
  --regions lax sjc sea
```
