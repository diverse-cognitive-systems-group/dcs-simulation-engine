# Configure An Engine Run

Experiment configuration is currently driven by the
`ExperimentConfig` model in `dcs_simulation_engine/core/experiment_config.py`.
If you want a runnable starting point, use `experiments/usability.yml`. If you
want a fuller template that shows the current schema, use
`examples/run_configs/_example.yml`.

Do not use `examples/run_configs/benchmark-ai-performance.yml` or the other
legacy draft files as the primary template without updating them first. Several
of those files still use an older schema and do not validate against the
current model.

## Where Config Files Live

- For local standard-mode runs that use `--default-experiment`, put the YAML
  file in `experiments/` and refer to it by name.
- For Fly.io deployments, pass any readable YAML path with
  `dcs remote deploy --config`.
- The engine also discovers experiment configs copied into
  `deployments/<deployment-slug>/experiments/`.

## Minimal Example

```yaml
name: my-study
description: |
  Example experiment config for a local or remote study.
condition: learning

assignment_strategy:
  strategy: random_unique_game
  games:
    - Explore
    - Infer Intent
  quota_per_game: 5
  max_assignments_per_player: 1
  seed: 42
  allow_choice_if_multiple: false
  require_completion: true

forms:
  - name: intake
    before_or_after: before
    questions:
      - key: participant_background
        prompt: Briefly describe any relevant background.
        answer_type: string
```

## Top-Level Fields

- `name`: required experiment identifier. This is also the experiment name used
  in API routes and in `--default-experiment`.
- `description`: optional human-readable summary.
- `condition`: optional label. Current accepted values are `learning` and
  `static`.
- `assignment_strategy`: required. Controls which games are included and how
  assignments are created.
- `forms`: optional list of before-play and after-play forms.

## Assignment Strategy Fields

The current schema accepts these common fields under `assignment_strategy`:

- `strategy`
- `games`
- `player_characters`
- `non_player_characters`
- `quota_per_game`
- `max_assignments_per_player`
- `seed`
- `pc_eligible_only`
- `allow_choice_if_multiple`
- `require_completion`

Current built-in strategy names are:

- `full_character_access`
- `unplayed_combination_choice`
- `expertise_matched_character_choice`
- `next_incomplete_combination`
- `least_played_combination_next`
- `progressive_divergence_assignment`
- `max_contrast_pairing`
- `expertise_matched_character_next`
- `expertise_matched_character_batch`
- `random_unique_game`

## Built-In Games

The repo currently ships these canonical game names:

- `Explore`
- `Infer Intent`
- `Foresight`
- `Goal Horizon`
- `Teamwork`

Game references are normalized, so `goal-horizon`, `goal_horizon`, and
`Goal Horizon` resolve to the same built-in game.

## Forms

Forms are attached to the experiment and appear either before or after
gameplay.

- `before_or_after` must be `before` or `after`.
- `answer_type` may be `string`, `bool`, `single_choice`, `multi_choice`,
  `number`, `email`, or `phone`.
- Choice questions require an `options` list.
- Question keys are optional, but providing stable keys is recommended if you
  plan to compare results across runs.

## Using A Config Locally

Save a config as `experiments/my-study.yml`, then start the server in standard
mode:

```bash
uv run dcs server \
  --mongo-seed-dir database_seeds/dev \
  --dump ./runs \
  --default-experiment my-study
```

That makes the experiment available at `/experiments/my-study` in the UI and at
the corresponding experiment API routes.

## Using A Config On Fly.io

Pass the YAML path directly during deploy:

```bash
uv run dcs remote deploy \
  --config experiments/my-study.yml \
  --mongo-seed-path database_seeds/dev \
  --region lax
```
