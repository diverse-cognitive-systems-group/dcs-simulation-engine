# Analyze Results

The engine can export raw Mongo-backed run data, and the repo also includes
reporting utilities for turning result directories into HTML summaries.

## Raw Exports

### Local Runs

You have two current export paths:

- run the server with `--dump ./runs` so shutdown writes a timestamped dump
- call `uv run dcs dump ./runs` manually against the active local database

Both produce timestamped directories under `runs/`.

### Remote Runs

For Fly.io deployments, save the database as an archive:

```bash
uv run dcs remote save \
  --uri https://dcs-your-experiment-api.fly.dev \
  --admin-key your-admin-key \
  --save-db-path results/remote-export.zip
```

`dcs remote save` writes a `.zip` or `.tar.gz` archive depending on the output
filename. Unpack the archive before pointing report tools at it.

## Generate HTML Reports

The current reporting entrypoint in this repo is the `dcs_utils` module:

```bash
uv run python -m dcs_utils.cli report results <results_dir> --report-path results/my_report.html
```

A checked-in known-good example is:

```bash
uv run python -m dcs_utils.cli report results \
  tests/data/example_results \
  --report-path results/example_results_report.html
```

Useful report flags:

- `--only <section>` to render a subset of sections
- `--include <section>` to add sections to the default set
- `--exclude <section>` to drop sections from the default set
- `--open` to open the report in your browser after generation

Current section slugs include:

- `metadata`
- `runs-overview`
- `player-performance`
- `player-feedback`
- `form-responses`
- `pc-coverage`
- `npc-coverage`
- `sim-quality`
- `system-performance`
- `system-errors`
- `transcripts`

Example: generate only the system-performance section:

```bash
uv run python -m dcs_utils.cli report results \
  tests/data/example_results \
  --only system-performance \
  --report-path results/system_performance_only.html
```

## Character Coverage Report

To generate the built-in character coverage report:

```bash
uv run python -m dcs_utils.cli report coverage --db dev
```

Use `--db prod` if you want the production seed set instead.

## Performance Testing

The repo includes a load-test script at `tests/scripts/load_test.py`.

### Important Limitation

`load_test.py` registers new players before it starts gameplay, so it must run
against a `standard` mode server. Do not point it at a `--free-play` server.

### Recommended Local Setup

Use a fake AI response to remove live-model variability from the test:

```bash
uv run dcs server \
  --mongo-seed-dir database_seeds/dev \
  --fake-ai-response "Load test placeholder response."
```

### Run The Load Test

```bash
uv run python tests/scripts/load_test.py \
  --base-url http://127.0.0.1:8000 \
  --clients 10 \
  --games 5 \
  --turns 3 \
  --out results/load_test_metrics.csv
```

The output CSV contains flattened timing data for:

- total per-game duration
- opening-turn wait time
- per-turn wait time
- close-session wait time

### Analyze Load-Test Output

```bash
uv run python dcs_utils/manual/analyze_load_test_results.py \
  --input results/load_test_metrics.csv \
  --output-dir analysis/load_test
```

That script generates plots for:

- game duration by client
- turn wait time by client
- turn wait time by client and game
- combined duration histograms and density plots

## Deeper Analysis

For deeper offline analysis, inspect:

- `dcs_utils/manual/`
- `analysis` dependencies from `pyproject.toml`
- the example HTML reports in `examples/reports/`
