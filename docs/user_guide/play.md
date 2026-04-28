# Play And Monitor

Players can use the browser UI or connect directly to the API. The exact flow
depends on whether the server is running in `standard` mode or `free_play`
mode.

## Human Players In The Web UI

### Standard Mode

Standard mode is used when the server starts without `--free-play`.

- registration is enabled at `/signup`
- returning players can sign in at `/login`
- if the server has `--default-experiment usability`, the UI routes players into
  `/experiments/usability`
- if no default experiment is configured, authenticated players can browse the
  games list directly

This is the right mode for consent forms, intake/outtake forms, assignments,
and study-style workflows.

### Free-Play Mode

Free-play mode is used when the server starts with `--free-play`.

- no registration or sign-in
- no experiment routes
- the UI opens directly to `/games`

This is the quickest path for local human playtesting.

## API And AI Clients

The repo includes known-good example scripts in `examples/api_usage/`.

### Free-Play Example

Start the server:

```bash
uv run dcs server \
  --mongo-seed-dir database_seeds/dev \
  --free-play
```

Then run the example client:

```bash
uv run python examples/api_usage/explore.py \
  --base-url http://127.0.0.1:8000
```

### Standard-Mode Example

Start the server:

```bash
uv run dcs server \
  --mongo-seed-dir database_seeds/dev \
  --default-experiment usability
```

Then run the registration/auth/play example:

```bash
uv run python examples/api_usage/register_auth_play_close.py \
  --base-url http://127.0.0.1:8000 \
  --game "Explore"
```

That script:

- fetches `/api/server/config`
- registers a player
- authenticates with the issued access key
- fetches setup options
- starts a session
- advances several turns
- closes the session

## Monitoring A Local Run

### Browser And API Checks

- `http://localhost:8000/healthz`: quick server readiness check
- `http://localhost:8000/docs`: Swagger UI
- `http://localhost:8000/redoc`: ReDoc
- `http://localhost:8000/api/server/config`: current server mode and capability
  flags

### Experiment Status

If you are running a standard-mode experiment such as `usability`, you can also
inspect the experiment status payload:

```text
http://localhost:8000/api/experiments/usability/status
```

The browser UI exposes the same information on the experiment route while
players are moving through the study.

### Remote Monitoring

For Fly.io deployments, use the CLI instead:

```bash
uv run dcs remote status \
  --uri https://dcs-your-experiment-api.fly.dev \
  --admin-key your-admin-key
```
