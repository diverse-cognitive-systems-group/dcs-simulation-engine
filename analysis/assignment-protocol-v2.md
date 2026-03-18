# Assignment Protocol Investigation

## Scope

This document investigates how to add a run-level "assignment protocol" to the current codebase. It synthesizes findings from all files under `analysis/`, the four `.docx` study documents, and a review of the current runtime surfaces that would need to change.

Reviewed analysis materials:
- All YAML run configurations and their header comments
- `analysis/assignment-protocol-investigation.md` (the prior investigation)
- `analysis/yaml-comments.md`
- `analysis/character-assignment-filtering-inventory.md`
- All helper modules, notebooks, and JSON assets
- `DCS-SE Character Development Study.docx`
- `DCS-SE Simulation Quality Study.docx`
- `DCS-SE Usability Study.docx`
- `DCS-SE Evaluating Understanding of Diverse Cognitive Systems.docx`

Reviewed current runtime surfaces:
- `dcs_simulation_engine/core/game_config.py`
- `dcs_simulation_engine/core/session_manager.py`
- `dcs_simulation_engine/api/routers/play.py`
- `dcs_simulation_engine/api/models.py`
- `dcs_simulation_engine/dal/base.py`
- `dcs_simulation_engine/dal/mongo/async_provider.py`
- `dcs_simulation_engine/dal/mongo/const.py`

---

## What the Analysis Folder Is Asking For

Every YAML under `analysis/` fails against the current `GameConfig` parser. They use run-level keys (`assignment`, `games`, `players`, `ui_settings`, `post-play-form`) and omit required game-level fields. These files describe a future feature, not existing behavior.

The four `.docx` study documents each reinforce the same architectural need from a different angle:

- **Character Development** — explicit representational limits; careful matching between what is modeled and what is evaluated requires a protocol that can fix a character across games and track coverage gaps.
- **Simulation Quality** — expert matching and balanced coverage require assigning domain experts to characters based on their declared expertise and prioritizing underrepresented combinations.
- **Usability** — low-friction onboarding requires dynamic consent forms per run, not a fixed registration schema.
- **Benchmark (Diverse Cognitive Systems)** — standardized but extensible protocols, supporting both static (fixed assignments, controlled conditions) and open-ended (player-driven, learning) evaluation modes.

### Assignment patterns across all analysis YAMLs

| Config | Strategy | Stop Condition |
|--------|----------|----------------|
| `eval-one-character.yaml` | Fixed character; player chooses game | None |
| `performance-eval-learning-ai.yaml` | Fixed character; player chooses game | None |
| `performance-eval-learning-human.yaml` | Each combo played N times; post-play form after each | All combinations done |
| `performance-eval-static-human.yaml` | Least-played-first; max 4 per player | All assignments completed |
| `performance-eval-static-ai.yaml` | Exhaustive: every game × character per AI player | All assignments completed |
| `expert-eval.yaml` | Expertise-matched; no repeats; keep char across games | All char × game combinations covered ≥ 1 |
| `usability-ca.yaml` | Random unique; max 1 game per player | 5 unique players per game |

---

## Current Runtime State

### 1. No run-level config model

`GameConfig` is game-scoped: metadata, access settings, data collection, stopping conditions, `game_class`. It does not model multi-game runs, participants, assignment protocols, post-play forms, or aggregate stop conditions.

### 2. Assignment is random fallback only

`SessionManager.create_async()` does: access gating → valid pool lookup → choice validation → random fallback pick. There is no protocol engine, no persistence of assignment history, no balancing or quota awareness.

### 3. The API is game-centric

`GET /api/play/setup/{game_name}` and `POST /api/play/game` are the only session-creation surfaces. There is no run identity, no "next assignment" concept, and no run-level registration endpoint.

### 4. Registration is hard-coded

`RegistrationRequest` is a fixed schema. It cannot render protocol-specific intake forms or require different expertise fields per study.

### 5. No persistent run or assignment state

The database has `characters`, `players`, `sessions`, and `session_events`. There is no concept of runs, assignment records, assignment claims, or stop-condition progress. Without persistent assignment state, balanced or quota-aware scheduling cannot be made safe under concurrency.

### 6. No existing `assignment/` module

There is no `assignment/` directory or `run_config.py` anywhere in the codebase. The referenced helper files (`helpers/expert-eval-assignment.py`, `helpers/static-human-assignment.py`, etc.) are all empty or missing.

---

## Design Options

### Option A: Pure Python Strategy Plugins

The `assignment` field in the YAML points to a Python file path. That file implements some strategy and is imported at run time. This is what the existing analysis YAMLs imply — they all use `assignment: "helpers/X.py"`.

**Pros:**
- Fastest to prototype
- Matches what the YAMLs already express
- Maximum flexibility — any logic is expressible

**Cons:**
- No schema validation; silent misconfiguration is easy
- Each strategy invents its own semantics with no shared contract
- No built-in persistence discipline — each script must roll its own atomicity and state
- The referenced helper files are all empty or missing; this option requires implementing all strategies from scratch
- Hard to inspect, compare, or migrate protocols across studies

**Verdict:** Good for a short-term proof of concept. Not a long-term interface.

---

### Option B: Declarative Built-Ins With Optional Python Escape Hatch

Define a `RunConfig` schema with a first-class `assignment_protocol` section that names a built-in strategy with typed params. Provide a `custom` strategy type that accepts a class path for edge cases.

```yaml
name: static-human
games:
  - infer intent
  - goal horizon
  - foresight
  - teamwork
assignment_protocol:
  strategy: least_played_first
  params:
    max_assignments_per_player: 4
    avoid_repeat_keys: [player, game, character]
stop_conditions:
  - strategy: all_assignments_completed
new_player_form:
  questions: [ ... ]
post_play_form:
  questions: [ ... ]
```

Built-in strategies covering all patterns present in the analysis folder:
- `open_choice` — no protocol; player selects freely (usability study)
- `fixed_character` — one character ID pinned for all players; player selects game (eval-one-character, learning protocols)
- `exhaustive_combinations` — enumerate all game × character combos per player (static-ai)
- `least_played_first` — claim the combo with the lowest play count; supports per-player cap (static-human)
- `random_unique` — random assignment without repeating player + game + character (usability-ca)
- `expertise_balanced` — match player expertise tags to character descriptors, then balance by coverage (expert-eval)
- `custom` — load a Python class by dotted path; must implement the `AssignmentStrategy` protocol

**Pros:**
- All recurring patterns get validated, documented, and testable implementations
- Config is readable and inspectable without running code
- Custom escape hatch preserves full flexibility
- Common contract means shared persistence and atomicity across all strategies
- Schema enables migration, documentation, and cross-study comparison

**Cons:**
- More upfront schema design work
- Need to agree on which patterns deserve built-in status (the analysis folder settles this)

**Verdict:** Best fit for the repo as it exists today.

---

### Option C: Materialized Assignment Queue (as an implementation technique)

Rather than computing the next assignment dynamically, compile the run config into explicit assignment records at run-start time, then have each session atomically claim the next eligible record.

This is not a competing interface design — it is the right *implementation* for strategies like `exhaustive_combinations` and `least_played_first`, which can be precomputed. For expertise-based matching, the queue is filtered at claim time but not fully precomputed.

**Pros:**
- Deterministic, auditable, inspectable
- Atomic claim via `findOneAndUpdate` with `status: pending → claimed` transition
- Stop conditions are trivially checkable (count unclaimed records)
- Easy to test in isolation with seed data

**Cons:**
- Awkward for open-ended protocols where combinations are not known ahead of time
- Expertise matching still needs a dynamic filter at claim time

**Verdict:** Use Option B at the interface layer, Option C under the hood for strategies that can be materialized.

---

## Recommended Direction

Option B at the config and API layer, with Option C as the internal implementation for materializable strategies.

External interface: a new `RunConfig` schema with declarative `assignment_protocol`, optional custom Python class, `stop_conditions`, `new_player_form`, and `post_play_form`.

Runtime: an `AssignmentStrategy` protocol with a small explicit contract, an `AssignmentStore` backed by Mongo, materialized assignment records where possible, dynamic strategy evaluation where needed.

Session integration: the assignment service resolves the next assignment, which is then passed into the existing `SessionManager.create_async()`. Existing game-level access checks and valid-character checks still run. The new layer sits above the game layer.

---

## Concrete Codebase Changes

### 1. `dcs_simulation_engine/core/run_config.py` (new)

Models:
- `RunConfig` — name, description, games (list of game names), assignment_protocol, stop_conditions, new_player_form, post_play_form, ui_settings, seed
- `AssignmentProtocolConfig` — strategy name, params dict, optional custom class path
- `StopConditionConfig` — strategy name, params

Reuse existing `Form` and `FormQuestion` from `game_config.py` for form fields. `RunConfig` does not replace `GameConfig`; it references games by name and the engine looks up the matching `GameConfig` separately.

### 2. `dcs_simulation_engine/assignment/` (new module)

- `base.py` — `AssignmentStrategy` Protocol; `AssignmentContext` and `AssignmentDecision` dataclasses
- `models.py` — `AssignmentRecord`, `AssignmentClaim`, `AssignmentOutcome`
- `strategies/` — one file per built-in strategy
- `factory.py` — maps strategy name to class; handles `custom` class loading

Key interface (intentionally small):

```python
class AssignmentStrategy(Protocol):
    async def next_assignment(self, context: AssignmentContext) -> AssignmentDecision | None: ...
    async def record_completion(self, outcome: AssignmentOutcome) -> None: ...
```

`AssignmentContext` carries: run_id, player_id, player data including expertise, available game × character pairs, existing assignment history for this player in this run.

### 3. DAL extensions

New collections:
- `runs` — run metadata, config snapshot, created_at
- `assignments` — run_id, player_id, game, pc_hid, npc_hid, status (`pending | claimed | completed | abandoned`), claimed_at, completed_at, session_id

Changes to:
- `dcs_simulation_engine/dal/base.py` — new abstract methods: `create_run`, `get_run`, `claim_next_assignment` (atomic), `complete_assignment`, `get_assignment_history`
- `dcs_simulation_engine/dal/mongo/async_provider.py` — implement the above using `findOneAndUpdate` for atomic claim
- `dcs_simulation_engine/dal/mongo/const.py` — new collection names and index definitions

Indexes needed: `(run_id, player_id, game, pc_hid)` for no-repeat enforcement; `(run_id, status)` for queue queries.

### 4. `dcs_simulation_engine/core/run_manager.py` (new)

Orchestration above `SessionManager`:
- Loads `RunConfig`
- Resolves the next assignment for a player via the strategy
- Claims the assignment atomically in the database
- Passes resolved `(game, pc_choice, npc_choice)` into `SessionManager.create_async()`
- On session completion: records the outcome, updates assignment status, checks stop conditions

`SessionManager` stays unchanged.

### 5. API extensions

New router (e.g., `dcs_simulation_engine/api/routers/runs.py`):
- `GET /api/runs/{run_name}` — run metadata and current status
- `GET /api/runs/{run_name}/setup` — new-player form schema for this run
- `POST /api/runs/{run_name}/players` — register a player against a run (replaces fixed `RegistrationRequest`)
- `POST /api/runs/{run_name}/assignments/next` — claim next assignment for a player; returns `(game, pc, npc)` or a `done` signal
- `POST /api/runs/{run_name}/sessions` — create a session for a claimed assignment
- `POST /api/runs/{run_name}/sessions/{session_id}/complete` — mark session done, trigger post-play form

Existing `/api/play/*` endpoints remain for unprotocolized sessions.

New models in `api/models.py`:
- `ClaimAssignmentRequest(run_name, player_id)` → `ClaimAssignmentResponse(assignment_id, game, pc, npc)` or `RunCompleteResponse`
- `RunStatusResponse(name, total_assignments, completed, claimed, pending, is_complete)`

### 6. Dynamic forms

Replace the fixed `RegistrationRequest` with a dynamic form renderer that reads `RunConfig.new_player_form`. The server returns the form schema at `GET /api/runs/{run_name}/setup`; the client renders it. PII fields go to the existing `pii` collection; non-PII fields go to `PlayerRecord.data`. Expertise fields are stored under a normalized key so `expertise_balanced` can query them.

### 7. UI updates

- Assignment banner (from `ui_settings.assignment_banner`)
- Hide character/game selectors when assignment is forced by the protocol
- Post-play form display after session completion
- Optional progress indicator

---

## Testing Strategy (Isolated Component)

The assignment layer can be tested without booting the full simulator or running any games.

### Parser tests

- Valid `RunConfig` documents for each analysis YAML pattern
- Invalid strategy names, invalid custom class paths, invalid repeat counts, missing required fields
- Confirm `Form` / `FormQuestion` validation reuses the same rules as `GameConfig`

### Strategy contract tests

For each built-in strategy, use in-memory fake data only (no database):
- First assignment returned is correct
- Repeat prevention fires correctly
- Balancing order is correct under `least_played_first`
- Exhaustion returns `None` when all combinations are claimed
- Fixed seed produces deterministic output
- Expertise matching scores and ranks correctly

### Store / claim tests

Test atomic claim logic with a real or containerized Mongo instance:
- Claiming the same assignment twice from concurrent callers: exactly one succeeds
- Completion updates aggregate progress correctly
- Abandoned assignments can be reclaimed
- Stop condition reflects persisted state

These are where concurrency bugs will surface. Use pytest-asyncio + motor + mongomock or a local Mongo.

### Session handoff tests

- Resolved `(game, pc, npc)` flows correctly into `SessionManager.create_async()`
- Forced choices cannot be overridden by user-supplied values
- Session completion writes back to the assignment record
- Use the existing `patch_llm_client` fixture in `tests/conftest.py`; no real LLM needed

### Golden round-trip tests

Once the `RunConfig` schema is finalized, parse each analysis YAML (after minor syntax fixes) as a fixture and verify:
- `eval-one-character.yaml` → `fixed_character`, no stop condition
- `performance-eval-static-human.yaml` → `least_played_first`, `all_assignments_completed`
- `performance-eval-static-ai.yaml` → `exhaustive_combinations`, `all_assignments_completed`
- `expert-eval.yaml` → `expertise_balanced`, `all_char_game_combos_covered`
- `usability-ca.yaml` → `random_unique`, `per_game_unique_player_quota`

These act as living specification tests that prevent the implementation from drifting away from the design intent already expressed in the analysis folder.

---

## Critiques of the Existing Plans

### 1. The `assignment: "helpers/X.py"` pattern is not a design

Every current analysis YAML uses a bare file path as the assignment protocol. All referenced files are either empty or missing. This defers atomicity, balancing, stop-condition tracking, and expertise matching to individual scripts with no shared contract. It is a reasonable way to express design intent in a placeholder file, but it cannot be implemented as-is without solving each of those hard problems from scratch in every strategy file. Treating the file-path approach as a design choice would result in a fragmented implementation that is difficult to test, extend, or compare across studies.

### 2. The prior investigation understates the complexity of the schema design

`assignment-protocol-investigation.md` recommends Option 2 (Declarative Built-Ins) correctly, but leaves several critical design questions unanswered. Specifically:

- **The unit of assignment is unresolved.** The investigation asks "is it game + character, or game + pc + npc?" without answering. The analysis YAMLs treat PC as the assignment unit (NPC is game-default), but `expert-eval.yaml` implies the full session context matters. This must be settled before the schema can be written.

- **Expertise matching is underspecified.** The investigation mentions `expertise_balanced` as a built-in strategy but does not describe how player expertise fields map to character attributes. The current character data has `common_descriptors` and `anthronormal_divergence`. Without a defined matching algorithm, the strategy cannot be implemented.

- **Forms are reinvented unnecessarily.** `GameConfig` already has working `Form` and `FormQuestion` models. `RunConfig` should reuse them. The investigation treats forms as a new problem, which adds complexity without benefit.

### 3. Option C (Materialized Queue) is a peer option in the investigation but it shouldn't be

The investigation lists the materialized assignment queue as a top-level alternative alongside Options 1 and 2. But it is not an interface choice — it is an implementation technique for specific strategies. Presenting it at the same level as the interface options creates a false three-way choice. It belongs under "how to implement `exhaustive_combinations` and `least_played_first`," not as a separate path.

### 4. AI player scheduling is glossed over

The investigation notes that AI players should not be a "totally separate path" but does not explain how they interact with the protocol. The static-ai YAML defines players as model IDs (`openrouter:openai-gpt-4o`). The following product questions must be resolved before implementing AI player support:
- Does an AI player claim assignments the same way a human does (pull model), or does the run manager drive batch scheduling (push model)?
- Does `expertise_balanced` make sense for AI players? (Probably not.)
- If an AI session fails mid-run, does the assignment go `abandoned` or auto-retry?

### 5. Stop conditions are listed but not traced back to each study

The investigation lists four stop conditions but does not verify that they cover all patterns. The tracing is:

| Study Config | Stop Condition Required |
|--------------|------------------------|
| eval-one-character | none |
| learning-ai | none |
| learning-human | all_combinations_done (with repeat_count = N) |
| static-human | all_assignments_completed |
| static-ai | all_assignments_completed |
| expert-eval | min_count_per_combination (≥ 1 for each char × game) |
| usability-ca | per_game_unique_player_quota (5 per game) |

The four listed conditions do cover this set. But `min_count_per_combination` is the correct name for what `expert-eval` needs, not `all_assignments_completed` — these are subtly different when a run is populated dynamically rather than from a precomputed queue.

---

## Open Questions (Prioritized)

**Must settle before schema design:**
1. What is the assignment unit? Game + character (PC only), or game + PC + NPC pair?
2. How does player expertise map to character attributes for `expertise_balanced`? What field on the character record is used, and what algorithm computes the match score?

**Must settle before API design:**
3. Can a player hold multiple active claimed assignments in one run (parallel sessions)?
4. Do post-play forms live at run level, game level, or both?

**Can defer to implementation:**
5. Do AI players claim assignments the same way humans do, or does run_manager schedule them in batch?
6. Is assignment progress visible in the UI from day one, or deferred to a later iteration?
7. Do we want per-assignment audit events for debugging, or just final status transitions?
