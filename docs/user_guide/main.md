# User Guide

The DCS user guide is organized around the workflows that are supported by this
checkout today: configure an experiment, run the stack locally, let humans or
API clients play, export results, generate reports, and optionally deploy the
stack to Fly.io.

<img src="../assets/workflow.png" alt="Workflow overview" width="600"/>

## Start Here

- Use [Configure](configure.md) to create or edit an experiment YAML file.
- Use [Run](run.md) for local execution in VS Code, from a terminal, or with
  Docker Compose.
- Use [Play and Monitor](play.md) for human-player flow, API usage, and basic
  monitoring.
- Use [Analyze Results](analyze_results.md) for exports, HTML reports, and load
  testing.
- Use [Deployment](deployment.md) to deploy the stack to Fly.io.
- Use [Advanced Usage](advanced.md) when you need custom games, characters,
  assignment strategies, or non-default clients.

## Supported Modes

- `standard`: registration and authentication are enabled. Players can sign up,
  sign in, and either enter a default experiment or browse games directly.
- `free_play`: anonymous local play. Registration and experiment flows are
  disabled and the UI opens directly to game selection.
- `remote_managed`: the same API server with additional bootstrap/export
  endpoints enabled for Fly.io deployments.

## Current Source Of Truth

- `experiments/usability.yml` is the shipped runnable experiment used by the
  VS Code launch configuration.
- `examples/run_configs/_example.yml` is the best current schema reference for
  authoring a new experiment config.
- `dcs_simulation_engine/core/experiment_config.py` is the validation model for
  experiment configs.
- Several other files in `examples/run_configs/` still reflect an older draft
  schema. Do not treat them as the primary template unless you update them to
  the current `ExperimentConfig` shape first.

## Common URLs And Outputs

- UI: `http://localhost:5173`
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Local database dumps: `runs/<timestamp>/`
- Generated HTML reports: `results/`

## Before You Run Anything

- Set `OPENROUTER_API_KEY` for any workflow that uses live model responses.
- Install Docker for MongoDB or for the full Docker Compose stack.
- If you are running outside Docker, use Python `3.13`, `uv`, and `bun`.
