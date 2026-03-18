# Assignment Protocol Investigation

## Scope

This document investigates how to add a run-level "assignment protocol" to the current codebase.

I reviewed all files under `analysis/`, including:

- the root analysis docs and helpers
- all analysis YAML files
- all notebooks, including empty and WIP notebooks
- all helper modules and JSON assets
- the four `.docx` study documents

I also reviewed the current runtime surfaces that would need to change:

- `dcs_simulation_engine/core/game_config.py`
- `dcs_simulation_engine/core/session_manager.py`
- `dcs_simulation_engine/api/routers/play.py`
- `dcs_simulation_engine/api/routers/users.py`
- `dcs_simulation_engine/api/models.py`
- `dcs_simulation_engine/dal/base.py`
- `dcs_simulation_engine/dal/mongo/async_provider.py`
- `docs/character-assignment-filtering-inventory.md`

## Executive Summary

The analysis materials consistently treat assignment as a study-level orchestration problem, not a per-game character-picker problem.

Today the engine only supports:

- per-game access gating
- per-game character pool lookup
- optional user-provided `pc_choice` / `npc_choice`
- random fallback selection when choices are omitted

It does not yet support:

- a run/study config model
- assignment state that persists across sessions
- balancing or quota-aware scheduling
- expertise-based matching
- "no repeat" rules across player + game + character
- protocol-driven post-play flows
- run-level stop conditions
- run-level AI player scheduling

My recommendation is a hybrid design:

- add a new run-level YAML schema separate from `GameConfig`
- make `assignment_protocol` declarative for common cases
- allow an optional Python strategy class for custom logic
- persist assignments in the database so claims are atomic and testable

That gives us the flexibility implied by the analysis folder without making every protocol a bespoke script.

## Plan Updates After Reviewing `assignment-protocol-v2.md`

I agree with the strongest corrections in `analysis/assignment-protocol-v2.md`, and I would update the plan in these ways:

- treat the materialized assignment queue as an implementation technique, not a peer interface option
- explicitly reuse `Form` and `FormQuestion` from `game_config.py` inside the new run-level schema
- make "assignment unit" and "expertise matching algorithm" phase-0 decisions before writing the `RunConfig` schema
- trace stop conditions back to the concrete study configs rather than listing them abstractly
- call out AI player scheduling as a separate execution question rather than burying it inside the general assignment design

One useful nuance from the review: the study artifacts are not fully aligned on the usability protocol. The current `analysis/usability/usability-ca.yaml` says `assignment: null` with no auto-stop, while the README/comments elsewhere describe a random-unique assignment plus a per-game quota. That needs a product decision before I would freeze the built-in stop-condition set around usability.

## What The Analysis Folder Is Asking For

Across the analysis YAML comments, helper code, notebooks, and study docs, the same requirements show up repeatedly:

- assignment is protocolized at the run/study level, not inside one game
- a run may span multiple games and multiple characters
- assignments may depend on player expertise, prior participation, quotas, or coverage gaps
- some protocols allow player choice, while others must hide choice and assign automatically
- some protocols require repeat counts
- some protocols need balancing, such as "least played first"
- some protocols must avoid learning effects by preventing repeated combinations
- some runs are human-only, some are AI-only, and some conceptually support both
- stopping is defined over aggregate study progress, not just one session ending

The theory docs reinforce why this matters:

- the character development study emphasizes explicit representational limits and careful matching between what is modeled and what is evaluated
- the simulation quality study emphasizes expert matching, balanced coverage, and evaluation against real-world plausibility
- the usability study emphasizes low-friction flows and minimizing usability confounds
- the benchmark framing study emphasizes standardized but extensible protocols across static and open-ended evaluation modes

This combination points toward a protocol layer that sits above individual game sessions.

## Stop Condition Traceback By Study

The required stop-condition surface is best understood by tracing it back to each study config:

| Study Config | Stop Condition Needed | Notes |
|--------|----------|-------|
| `eval-one-character.yaml` | `none` | manual/internal workflow |
| `performance-eval-learning-ai.yaml` | `none` | fixed character, open-ended learning |
| `performance-eval-learning-human.yaml` | `all_combinations_done` with `repeat_count = N` | comments-only file today |
| `performance-eval-static-human.yaml` | `all_assignments_completed` | pairs naturally with a materialized queue |
| `performance-eval-static-ai.yaml` | `all_assignments_completed` | exhaustive grid per AI player |
| `expert-eval.yaml` | `min_count_per_combination` | each character x game combination covered at least once |
| `usability-ca.yaml` | ambiguous | current YAML says `none`; README/comments suggest `per_game_unique_player_quota` |

This is the set I would plan around for V1, with one open clarification on usability.

## Findings From The Reviewed Analysis Files

### Root analysis files

- `analysis/README.md` frames the whole folder as foundational analyses for character development, usability, simulation quality, and baseline benchmarking.
- `analysis/helpers.py` is shared analysis infrastructure for loading runs, players, transcripts, logs, and feedback into tabular form.
- `analysis/yaml-comments.md` is the clearest synthesis of assignment requirements. It explicitly lists fixed-character assignment, exhaustive assignment, expertise-based assignment, custom assignment functions, repeat counts, no-repeat constraints, AI player support, and aggregate stop conditions.
- `analysis/__init__.py` is empty.
- `analysis/.DS_Store` is irrelevant editor/OS metadata.

### Baseline evaluations

- `analysis/baseline-evaluations/README.md` describes static and learning protocols for both humans and AI.
- `analysis/baseline-evaluations/performance-eval-learning-ai.yaml` uses `players` plus `assignment_protocol`, which is run-level configuration not supported by `GameConfig`.
- `analysis/baseline-evaluations/performance-eval-learning-human.yaml` is comments only. It describes repeated playthroughs plus post-play feedback after each run.
- `analysis/baseline-evaluations/performance-eval-static-ai.yaml` describes exhaustive play of all game + character combinations by AI players.
- `analysis/baseline-evaluations/performance-eval-static-human.yaml` describes a balanced "least played first" protocol plus optional post-play feedback and UI assignment messaging.
- `analysis/baseline-evaluations/helpers/oe_assignment_strategy.py` is empty.
- `analysis/baseline-evaluations/helpers/oe_player.py` is an incomplete code fragment and is not importable as-is.
- `analysis/baseline-evaluations/helpers/oe_default_config.yaml` is an OpenEvolve config, not a DCS run config.
- `analysis/baseline-evaluations/Foundational Model Performance.ipynb` is empty.
- `analysis/baseline-evaluations/Human Performance.ipynb` is empty.
- `analysis/baseline-evaluations/helpers/__init__.py` is empty.

### Character development

- `analysis/character-development/README.md` describes an iterative one-character workflow.
- `analysis/character-development/eval-one-character.yaml` describes a fixed-character protocol across multiple games.
- `analysis/character-development/helpers.py` contains substantive analysis code for divergence calculations and visualization.
- `analysis/character-development/hsn-abilities.json` defines the standard normative ability baseline used for divergence framing.
- `analysis/character-development/HSN Divergence Calculator.ipynb` is substantive and uses the helper code and HSN taxonomy.
- `analysis/character-development/Pairwise Divergence Calculator.ipynb` is minimal and mostly placeholder.

### Quality

- `analysis/quality/README.md` separates coverage analysis from behavioral quality analysis.
- `analysis/quality/behaviorial/expert-eval.yaml` is the strongest study-driven assignment example:
  - assign based on expertise
  - prioritize underplayed characters
  - keep one character across all games before switching
  - avoid repeats
  - stop when all character + game combinations have been covered
- `analysis/quality/behaviorial/In-Character Fidelity.ipynb` is WIP.
- `analysis/quality/behaviorial/Narrative Coherence.ipynb` is WIP.
- `analysis/quality/behaviorial/Rule-Following Fidelity.ipynb` is WIP.
- `analysis/quality/coverage/Cluster Coverage Analysis.ipynb` is partial and focused on database coverage rather than runtime assignment.
- `analysis/quality/coverage/Dimensional Coverage Analysis.ipynb` is partial and also focused on dataset coverage.

### Usability

- `analysis/usability/README.md` describes a low-friction protocol intended to uncover interface problems, not enforce strict study balancing.
- `analysis/usability/usability-ca.yaml` uses `assignment: null`, meaning "default runtime behavior is acceptable" for this study.
- `analysis/usability/helpers.py` contains substantial thematic feedback analysis and plotting utilities.
- `analysis/usability/System Performance Analysis.ipynb` is a partial notebook for run metadata, performance, and log analysis.
- `analysis/usability/Thematic Player Feedback Analysis.ipynb` is a partial notebook for classifying feedback themes.
- `analysis/usability/__init__.py` is empty.

### Load testing

- `analysis/load_test/analyze_load_test_results.py` is unrelated to assignment strategy logic, but it does show that system-level metrics are expected to be analyzed independently from gameplay.

### Study documents

- `analysis/DCS-SE Character Development Study.docx` argues for explicit representational boundaries and treating breakdowns as design-relevant findings.
- `analysis/DCS-SE Simulation Quality Study.docx` motivates expert matching and structured evaluation against representational plausibility.
- `analysis/DCS-SE Usability Study.docx` motivates minimizing workflow and UI confounds.
- `analysis/DCS-SE Evaluating Understanding of Diverse Cognitive Systems.docx` frames DCS-SE as a standardized but extensible benchmark that supports both static and open-ended protocols.

## Important Validation Notes

The analysis configs are currently design inputs, not executable runtime configs.

I verified that every YAML file under `analysis/` fails against the current `GameConfig` parser for at least one of these reasons:

- it uses run-level keys such as `assignment`, `assignment_protocol`, `games`, `players`, `ui_settings`, or `post-play-form`
- it omits required game-level fields such as `version` and `game_class`
- it contains invalid YAML syntax in unquoted strings with colons

In other words, these files are describing the target feature, not using an already-existing feature.

## Current Runtime State

### 1. The engine only has a game config model, not a run/study config model

`GameConfig` currently models:

- game metadata
- access settings
- data collection settings
- stopping conditions
- one `game_class`

It does not model:

- multi-game runs
- run-level participants
- run-level assignment protocols
- post-play forms
- run-level UI settings
- run-level stop conditions

This is visible in `dcs_simulation_engine/core/game_config.py`, where the schema ends at `game_class`, and character lookup currently just returns all characters.

### 2. Assignment today is just choice validation plus random fallback

`SessionManager.create_async(...)` does four assignment-like things:

- checks whether the player can access the game
- asks the game config for valid PC/NPC pools
- validates any provided choices
- randomly picks from the valid pools when choices are missing

That is not yet a protocol engine. It is just session setup.

### 3. The API is game-centric, not protocol-centric

The current API flow is:

- `GET /api/play/setup/{game_name}` returns allowed PCs and NPCs
- `POST /api/play/game` starts a session for a single game

The request model has:

- `game`
- `pc_choice`
- `npc_choice`

There is no run identifier, assignment identifier, or "give me my next assignment" concept.

### 4. Registration is hard-coded

`dcs_simulation_engine/api/routers/users.py` maps a fixed `RegistrationRequest` into stored player data.

That means the current runtime cannot yet:

- render protocol-specific intake forms
- require different expertise fields per study
- reuse the analysis YAML form definitions directly

### 5. Persistence lacks run and assignment state

The database currently stores:

- players
- sessions
- session events

There is no persistent concept of:

- run metadata
- assignment queue
- assignment claim
- assignment completion
- aggregate coverage
- stop-condition progress

Without persistent assignment state, balanced or quota-aware scheduling will not be safe under concurrency.

### 6. Post-play flows are currently bespoke inside games

The engine does support some game-specific completion flows. For example, Infer Intent already has a built-in completion interaction tested in `tests/functional/test_infer_intent_simulation_flow.py`.

But that is different from a generic run-level post-play form or protocol trigger.

### 7. The existing assignment inventory doc is partly stale

`docs/character-assignment-filtering-inventory.md` is still useful as a survey of runtime touchpoints, but parts of it describe structures that are not present in the current `GameConfig` implementation anymore.

That means we should use it as a change checklist, not as a source of truth for current behavior.

## Design Constraints That Follow From The Above

Any assignment protocol implementation should satisfy these constraints:

- it must be run-level and not overload `GameConfig`
- it must work for human and AI players
- it must persist enough state to avoid duplicate assignment claims
- it must integrate with existing game setup rather than replacing game-level validation
- it should preserve the possibility of "no protocol" or "default runtime behavior"
- it should let us test assignment logic without spinning up full games

## Option 1: Pure Python Strategy Plugins

### Idea

Add a new run-level config model whose `assignment_protocol` points directly to a Python class, and let that class decide the next assignment.

Example shape:

```yaml
name: expert-eval
games:
  - infer intent
  - goal horizon
assignment_protocol:
  class: dcs_simulation_engine.assignment.strategies.ExpertiseBalancedStrategy
  params:
    keep_character_across_games: true
    avoid_repeats: true
    balance_by: character
    seed: 42
```

### Pros

- fastest path to flexibility
- closest to what some analysis YAMLs already imply
- easy to prototype strange protocols

### Cons

- weak validation in YAML
- hard to inspect protocol behavior from config alone
- easy for each strategy to invent its own semantics
- harder to compare or standardize protocols across studies

### Fit

Good for an internal prototype, but I would not make it the long-term primary interface.

## Option 2: Declarative Built-Ins With Optional Python Escape Hatch

### Idea

Define a first-class run config schema with built-in strategy types for the recurring cases, plus an optional custom class hook for edge cases.

Example shape:

```yaml
name: static-human
games:
  - infer intent
  - goal horizon
assignment_protocol:
  strategy: least_played_first
  params:
    repeat_count: 1
    max_assignments_per_player: 4
    allow_early_stop_after: 1
    disallow_repeat_keys:
      - player
      - game
      - character
stop_conditions:
  strategy: all_assignments_completed
new_player_form:
  ...
post_play_form:
  ...
```

And for custom logic:

```yaml
assignment_protocol:
  strategy: custom
  class: dcs_simulation_engine.assignment.strategies.MyLabSpecificStrategy
  params:
    seed: 42
```

### Pros

- standardizes the common study patterns already present in `analysis/`
- supports validation, documentation, and migration
- still allows custom strategies
- easier to test because built-ins can share a common contract

### Cons

- more up-front schema work
- we have to decide which patterns deserve built-in status

### Fit

This is the best fit for the repo as it exists today.

It matches the analysis folder, keeps the configuration readable, and still leaves room for Python-backed custom protocols.

## Option 3: Materialized Assignment Queue (Implementation Technique)

### Idea

Compile a run config into explicit assignment records ahead of time, then have a scheduler claim the next eligible record for each player.

This works especially well for:

- exhaustive combination protocols
- balanced least-played protocols
- repeat counts
- quota-driven stop conditions
- AI batch runs

### Pros

- deterministic and auditable
- easy to inspect study progress
- atomic claim/update semantics are straightforward
- easy to test in isolation

### Cons

- some dynamic strategies are awkward to precompute
- expertise-based matching may still need a dynamic filter before claim

### Fit

This is not really a third interface option. It is the right internal implementation for several Option-2 strategies, especially `exhaustive_combinations` and `least_played_first`.

My preferred direction is:

- Option 2 at the config/API layer
- use a materialized queue under the hood for strategies that can be precomputed

## Recommended Direction

I recommend this architecture:

### External interface

- new `RunConfig` or `StudyConfig` model separate from `GameConfig`
- declarative `assignment_protocol`
- optional custom strategy class

### Runtime implementation

- `AssignmentStrategy` interface with a small, explicit contract
- `AssignmentStore` abstraction backed by Mongo
- materialized assignment records when possible
- dynamic strategy evaluation when needed

### Session integration

- assignment service resolves the next assignment
- resolved assignment is then passed into existing session creation
- existing game-level access checks and valid-character checks still run

This keeps the new feature above the game layer instead of tangling it into game internals.

## Concrete Codebase Changes

### 1. Add a run-level config model

Add a new module, for example:

- `dcs_simulation_engine/core/run_config.py`

This should model:

- run metadata
- included games
- player definitions for AI protocols
- new-player form
- post-play form
- UI settings
- assignment protocol
- stop conditions
- optional seed

This should not replace `GameConfig`. It should reference games by name.

`RunConfig` should reuse the existing `Form` and `FormQuestion` models from `dcs_simulation_engine/core/game_config.py` rather than inventing a second form schema.

### 2. Add assignment protocol abstractions

Add something like:

- `dcs_simulation_engine/assignment/base.py`
- `dcs_simulation_engine/assignment/models.py`
- `dcs_simulation_engine/assignment/strategies/*.py`
- `dcs_simulation_engine/assignment/factory.py`

Core models should likely include:

- `AssignmentRequest`
- `AssignmentDecision`
- `AssignmentRecord`
- `AssignmentContext`
- `AssignmentOutcome`

The key interface should be small, for example:

```python
class AssignmentStrategy(Protocol):
    async def next_assignment(self, context: AssignmentContext) -> AssignmentDecision | None: ...
    async def record_completion(self, context: AssignmentContext, outcome: AssignmentOutcome) -> None: ...
```

### 3. Persist run and assignment state

Extend the DAL with concepts such as:

- `runs`
- `assignments`
- maybe `assignment_events` if we want a detailed audit trail

Add provider methods for:

- create run
- get run
- claim next assignment atomically
- mark assignment completed
- mark assignment abandoned or expired
- compute run progress

This will require changes in:

- `dcs_simulation_engine/dal/base.py`
- `dcs_simulation_engine/dal/mongo/const.py`
- `dcs_simulation_engine/dal/mongo/async_provider.py`
- the Mongo admin/index setup

### 4. Add a protocol service above `SessionManager`

Keep `SessionManager` focused on one game session.

Add a coordinating layer, for example:

- `dcs_simulation_engine/core/run_manager.py`

That layer should:

- load the run config
- resolve the next assignment for a player
- lock forced game/character choices
- start the session
- handle completion and protocol progress updates

### 5. Extend the API

The API will need protocol-aware endpoints.

Likely additions:

- `GET /api/runs/{run_name}/setup`
- `POST /api/runs/{run_name}/register`
- `POST /api/runs/{run_name}/assignments/next`
- `POST /api/runs/{run_name}/sessions`
- `POST /api/runs/{run_name}/sessions/{session_id}/complete`

At minimum, the create-session request needs to become assignment-aware.

### 6. Make forms config-driven

Right now registration is fixed in `RegistrationRequest`.

To support the analysis protocols, we need:

- dynamic intake form rendering
- dynamic validation against run config
- PII-aware storage for config-defined fields
- reuse of the existing stored field shape used by access checks

This will change:

- `dcs_simulation_engine/api/models.py`
- `dcs_simulation_engine/api/routers/users.py`
- probably the UI generated models and forms

### 7. Update UI behavior

The analysis YAMLs imply UI behaviors such as:

- show assignment banners
- hide character choice when system-assigned
- allow game choice in some protocols
- show post-play forms
- potentially chain users into their next assignment

So the frontend will need protocol-aware setup and completion flows.

### 8. Keep `GameConfig` focused

I would avoid stuffing run-level protocol logic into `GameConfig`.

`GameConfig` should remain responsible for:

- game metadata
- game-specific access rules
- game-specific valid character pools
- game-specific stopping conditions

That separation will keep the assignment system easier to reason about.

## Testing Strategy For The Assignment Protocol As An Isolated Component

The good news is this can be tested very cleanly without booting the full simulator.

### 1. Parser tests

Create tests for:

- valid run configs
- invalid strategy names
- invalid custom class paths
- invalid repeat counts
- invalid stop-condition configs

These should live separately from game config tests.

### 2. Strategy contract tests

For each built-in strategy, test:

- first assignment selection
- repeat prevention
- balancing behavior
- exhaustion behavior
- deterministic behavior under fixed seeds

These tests should use fake players, fake characters, fake games, and fake history only.

### 3. Store tests

Test the persistence layer in isolation:

- claiming the same assignment twice is impossible
- completion updates aggregate progress correctly
- abandoned assignments can be reclaimed if intended
- stop conditions reflect persisted state

This is where concurrency bugs will show up, so atomic claim tests matter.

### 4. Expertise matching tests

For an expertise-based strategy, create small fixtures that map:

- player expertise tags
- character descriptors or divergence tags

Then test:

- direct matches
- fallback behavior when no good match exists
- balancing across equally valid matches

The current character seed data already has useful metadata such as `common_descriptors` and `anthronormal_divergence` that could support an initial matcher.

### 5. Session handoff tests

Add focused integration tests that verify:

- resolved assignment choices are passed into `SessionManager.create_async(...)`
- forced choices cannot be changed by the user
- session completion records the assignment outcome

This can use a dummy or mocked game and does not need the full UI.

### 6. Golden tests using the analysis configs

Once the new run config schema exists, convert a few analysis YAMLs into valid fixtures and use them as golden tests for:

- one fixed-character protocol
- one balanced human protocol
- one exhaustive AI protocol
- one expertise-based protocol
- one null/default assignment protocol

That would keep the implementation aligned with the design intent already living in `analysis/`.

## Suggested Initial Built-In Strategies

These are the recurring patterns that appear often enough to justify first-class support:

- `default_open_choice`
- `fixed_character`
- `exhaustive_combinations`
- `least_played_first`
- `random_unique`
- `expertise_balanced`

And the recurring stop conditions:

- `none`
- `all_assignments_completed`
- `per_game_unique_player_quota`
- `min_count_per_combination`

## Revised Implementation Order

### Phase 0: Resolve schema blockers

- settle the assignment unit:
  - `game + character`
  - or `game + pc + npc`
- define the expertise matcher:
  - which player fields are authoritative
  - which character fields are authoritative
  - how a match score is computed
- resolve the usability protocol discrepancy:
  - current YAML behavior
  - or README/comment behavior

### Phase 1: Add the run-level schema and contracts

- implement `RunConfig`
- reuse `Form` / `FormQuestion`
- define `AssignmentStrategy`, `AssignmentContext`, `AssignmentDecision`, `StopConditionConfig`
- implement parser tests first

### Phase 2: Add persistence and queue semantics

- add `runs` and `assignments`
- implement atomic claim/update methods
- add indexes
- write concurrency-focused store tests

### Phase 3: Implement built-in strategies

- `open_choice`
- `fixed_character`
- `exhaustive_combinations`
- `least_played_first`
- `random_unique`
- `expertise_balanced`

### Phase 4: Add the run manager and API integration

- `run_manager.py`
- run-aware setup and registration endpoints
- assignment claim endpoint
- session completion callback

### Phase 5: Add UI support

- dynamic onboarding form
- assignment banners and locked selectors
- post-play forms
- optional progress display

## Risks And Gotchas

- The current analysis YAMLs mix executable intent with non-executable notes. We should not try to directly "just load them" without defining a real run schema first.
- Assignment claims must be atomic, or balanced studies will quietly accumulate duplicate work.
- Dynamic forms and assignment logic touch both API and UI, so schema drift is a real risk.
- AI players should not be treated as a totally separate path if we want one protocol system to cover both human and AI studies.
- Some analysis files are placeholders or invalid as code today, so they should guide design but not be treated as working reference implementations.

## Open Questions

### Must settle before schema design

- What is the assignment unit:
  - `game + character`
  - or `game + pc + npc`
- How does player expertise map to character attributes for `expertise_balanced`:
  - which player field(s) are used
  - which character field(s) are used
  - what scoring or ranking logic is expected

### Must settle before API design

- Can one player hold multiple active claimed assignments in the same run?
- Should post-play forms live at the run level, game level, or both?

### Can defer to implementation

- Do AI players claim assignments the same way humans do, or does `run_manager` schedule them in batch?
- If an AI assignment fails mid-run, should it become `abandoned`, `retryable`, or immediately retried?
- Do we want assignment progress visible in the UI and CLI from day one?
- Do we want per-assignment audit events, or are final status transitions enough for V1?

## Bottom Line

The analysis folder is already specifying a future run-orchestration layer.

The cleanest implementation is not to extend the current random character picker. It is to add:

- a new run-level config model
- a protocol engine for assignment selection
- persistent assignment state
- a small API layer that asks for "next assignment" before creating a game session

That design lines up with the analysis materials, keeps the current game runtime mostly intact, and gives us an isolated component that can be tested thoroughly before we wire it into the full study flow.
