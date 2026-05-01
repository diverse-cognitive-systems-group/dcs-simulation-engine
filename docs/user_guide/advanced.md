# Advanced Usage

> Note: Most advanced usage requires checking out the codebase (see the [Contributing Guide](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/CONTRIBUTING.md)).

## Custom Assignment Strategies

Assignment strategies control what gameplay scenario (game + characters) is available next for a player. Researchers use this to ensure that players gameplay sessions are distributed across games and characters in a way that meets their research goals. For example, a researcher might want to ensure that each player gets a balanced mix of games and characters, or that certain underrepresented characters are prioritized for assignment.

To customize assignment strategies, checkout the code and implement the `AssignmentStrategy` interface in `dcs_simulation_engine/core/assignment_strategies.py`. Then reference your strategy by name in a run configuration.

⚠️ Note: This feature is incomplete or missing.

## Custom Character Filters

Character filters allow users to specify useful categories of PCs/NPCs allowed in gameplay. For example, if a user wants only neurodivergent non-player characters allows they can use the built-in `neurodivergent` filter by name.

To customize character filters, checkout the code and 

### 1. Add the filter

Implement the `CharacterFilter` interface in `dcs_simulation_engine/core/character_filters/base.py` (use the other filters as examples) and add it to the list of available filters in `dcs_simulation_engine/core/character_filters/__init__.py`

### 2. Add the filter to a game

Add the character filter to the games configuration (in `dcs_simulation_engine/games/`) that you want to make it available in

Then run the engine with the filter referenced by name in the run config and only those characters will be selected from for gameplay.

## Custom Characters

To customize (add/modify) characters, checkout the codebase and use the workflow below.

### 1. Create character sheet(s)

Create or modify a character sheet based on research (e.g., primary sources, expert interviews) and add it to the character to the database: `database_seeds/dev/characters.json`

### 2. Iteratively update characters sheet(s) to meet quality thresholds

Use the human-in-the-loop CLI to generate scenarios and evaluate character behavior:

`dcs admin hitl --help`

> Optionally running external evaluations using `expert-evaluation.yml` and/or `select-characters.yml` run configs can be useful where you have access to domain experts that can provide feedback on character behavior. 

### 3. Generate a Simulation Quality Report

Generate a simulation quality report (`dcs report <path/to/results> sim-quality --title "Character Quality Report"`) and determine if the coverage and in-character fidelity (ICF) scores are sufficient for publication 

If results are insufficient go back to step 2 to improve the character sheets or adjust the thresholds in `character-release-policy.yml`. If results are sufficient, move to step 4 to publish for review.

### 4. Publish for Review

Publish the character (`dcs admin publish --help`)

> To propose the DCS-SE adds this character to core characters database open a PR that includes reasoning and design decisions, code changes and the quality report with scores.

⸻

## Custom Games

To customize games, beyond their existing exposed configuration options, checkout the codebase and use the workflow below.

### 1. Implement the Game Interface

Create a new game file:

`dcs_simulation_engine/games/new_game.py`

Implement all required interface methods.

### 2. Add to a Run Config

Reference your game in a run config. See: `examples/run_configs/`

### 3. Test and Run

Test the game manually and/or add automated tests in `tests/` to validate game logic and integration with the engine.

### 4. Publish

Run the engine remotely with your new game.

⸻

## Custom Deployments (Non-Fly.io)

The engine is containerized and supports any platform that can run multi-container Docker applications.

To deploy to a new provider:

⚠️ TODO: Add high level external deployment workflow example (e.g. AWS, GCP, Azure)

⸻

## Custom Clients and Frontends (Unity, VR/AR, etc.)

The engine exposes an API endpoint, so you do not have to use our text-based React frontend. Any client can connect to the endpoint to:

1.	Send player actions

2.	Receive and render simulation updates

### Example Non-Run-Harnessed Gameplay with OpenEvolve

This is useful for non-run-harnessed gameplay, where the client directly interacts with the engine API without using the run harness. This enables custom orchestration, AI-driven control loops, and integration into external systems or apps.

[OpenEvolve](https://github.com/codelion/openevolve) is an evolutionary coding agent: it mutates a small "initial program" file across generations and scores each candidate with an evaluator function. To evolve a program that *plays* a game on the engine, start the engine without the UI (see [examples/run_configs/benchmark-ai.yml](../../examples/run_configs/benchmark-ai.yml), which sets `launch_gui: false`) and have the candidate program call the API directly (see [examples/api_usage/](../../examples/api_usage/)).

```plaintext
[OpenEvolve controller]
   - mutates initial_program
   - schedules evaluations
          │
          ▼
[evaluator.py: evaluate(candidate_path)]
   - imports candidate
   - opens APIClient → start_game(...)
   - loops run.step(text) until done
   - returns {"combined_score": float, ...}
          │
          │ HTTP + WebSocket
          ▼
[Simulation Engine API on :8000]
```

#### Step 1 — Drive a single game from Python

The minimal non-harnessed loop uses `APIClient.start_game` (in `dcs_simulation_engine.api.client`)
and the returned `SimulationRun` context manager. The first `step()` consumes the engine's opening
turn; subsequent `step(text)` calls submit player input.

```python
# openevolve-run.py
from dcs_simulation_engine.api.client import APIClient
from dcs_simulation_engine.api.models import CreateGameRequest

def play_one_game(strategy_fn, *, max_turns: int = 12) -> dict:
    """Drive one game session end-to-end. `strategy_fn(history) -> str` is the policy."""
    request = CreateGameRequest(
        game="Infer Intent",
        pc_choice=None,         # let the server pick a default-eligible PC
        npc_choice=None,
        source="openevolve",    # tag the session for downstream filtering
    )
    with APIClient(url="http://localhost:8000") as client, \
         client.start_game(request) as run:
        run.step()              # consume the opening turn
        while not run.is_complete and run.turns < max_turns:
            utterance = strategy_fn(run.history)
            run.step(utterance)
        return {"turns": run.turns, "exited": run.is_complete, "history": run.history}
```

#### Step 2 — Make the strategy evolvable

OpenEvolve evolves whatever lives between `EVOLVE-BLOCK-START` / `EVOLVE-BLOCK-END` markers in the
initial program file. For prompt evolution this can be as small as a strategy snippet that gets
injected into a frozen LLM prompt template; for code evolution it is a callable.

```python
# initial_program.py
# OpenEvolve will mutate the body of the "EVOLVE-.." block.

# EVOLVE-BLOCK-START
def choose_utterance(history: list) -> str:
    """Return the next player utterance given prior events."""
    return "Tell me more about what you want."
# EVOLVE-BLOCK-END
```

#### Step 3 — Wire up the evaluator

The evaluator imports the candidate, runs one or more games against the live engine, and returns
metrics. OpenEvolve maximizes `combined_score`; additional keys become artifacts the next generation
can be conditioned on.

```python
# evaluator.py
import importlib.util

def _load(candidate_path: str):
    spec = importlib.util.spec_from_file_location("candidate", candidate_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def evaluate(candidate_path: str) -> dict:
    candidate = _load(candidate_path)
    try:
        result = play_one_game(candidate.choose_utterance, max_turns=12)
    except Exception as exc:
        return {"combined_score": 0.0, "error": str(exc)[:500]}

    # Score however the experiment defines success — turn count, a Scorer LLM call,
    # game-specific exit reason, etc. Keep `combined_score` in [0, 1].
    score = 1.0 if result["exited"] else result["turns"] / 12
    return {"combined_score": score, "turns": result["turns"]}
```

#### Step 4 — Run evolution

A minimal config file for OpenEvolve, pointing at OpenRouter for the mutation LLM:

```yaml
# oe-config.yml
max_iterations: 50
llm:
  api_base: "https://openrouter.ai/api/v1/"
  api_key: ${OPENROUTER_API_KEY}
  models:
    - name: "google/gemini-2.5-flash-lite"
      weight: 1.0
evaluator:
  timeout: 600
  parallel_evaluations: 2
```

Then launch evolution from the OpenEvolve CLI against the running engine:

```bash
dcs run --config path/to/my/dcs-run-config.yml &&
python openevolve-run.py initial_program.py evaluator.py --config oe-config.yaml --iterations 50
```

> The comprehensive and complete default OpenEvolve config file can be found at OpenEvolve's GitHub page regarding the configs – [page link](https://github.com/algorithmicsuperintelligence/openevolve/blob/main/configs/default_config.yaml).


### Example Unity Integration

Unity or other custom clients can use the engine API directly to send player input and receive simulation state updates. This makes it possible to build bespoke visuals, controls, or interaction loops without relying on the default React frontend.

```plaintext
[Client Application (Unity / VR / AR)]
   - Player input
   - 3D rendering
   - Voice / UI / controllers
          │
          │ WebSocket / HTTP
          ▼
[Simulation Engine API]
   - Simulation state
   - Character decisions
   - World logic
   - Game rules
```

⸻