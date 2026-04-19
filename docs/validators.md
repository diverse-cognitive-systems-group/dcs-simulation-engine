# Validator Architecture

## 1. Motivation

In our turn-based RPG simulations, a single LLM call drives both the adjudication of the player's action and the narration of the NPC response ("the updater"). Left alone, this surface is subject to well-known failure modes that contaminate the cognitive-science data we collect:

1. **Fourth-wall breaks** — the model apologises, restates system rules, or emits assistant preamble.
2. **Sensory violations** — a blind NPC "sees" a silent wave; a deaf PC "hears" a whisper.
3. **Adjudication leakage** — the updater resolves an unobservable wish ("you conclude there's no trap") as settled fact.
4. **Ability violations** — a PC without hands "picks up the key."
5. **Multi-step compression** — a single turn collapses minutes or hours of narrative, breaking the per-turn observation granularity our experiments depend on.
6. **Game-specific contract violations** — e.g. a player using the Infer-Intent game asks the NPC outright "What is your goal?", trivialising the task.

A monolithic "mega-prompt" validator is unreliable at this many rules. We therefore split validation into an **ensemble of atomic validators**, each checking exactly one rule, running concurrently, and aggregated by a `ValidationOrchestrator` that sits in front of both PC input and NPC output. The design follows the same motivation as ensemble / self-consistency methods: several narrow judges outperform one wide judge, and per-rule isolation lets us ablate, tune, and cost-optimise rules independently.

## 2. Architectural overview

<br>
<img src="./assets/validator_architecture.png" width="400" height="400">

\
Three layers, three responsibilities:

| Layer | Class | Purpose |
|-------|-------|---------|
| Rule | `AtomicValidator` | Wraps one atomic rule prompt; one OpenRouter call, returns `(passed, reason)` |
| Ensemble | `EnsembleValidator` (+ subclasses) | Fans out to all its atomic rules in parallel; aggregates into `EnsembleValidationResult` |
| Orchestrator | `ValidationOrchestrator` | Composes the three ensembles, handles schema pre-checks, NPC retry loop, and event persistence |

All three ensemble subclasses inherit from the same `EnsembleValidator` base — the only thing that differs between them is the (data-only) prompt dictionary and context routing map.

## 3. Data model

Two `NamedTuple`s carry validation outcomes end-to-end ([ai_client.py:48-62](../dcs_simulation_engine/games/ai_client.py#L48-L62)):

```python
class ValidationResult(NamedTuple):
    rule: str        # e.g. "VALID-CHARACTER-ABILITY"
    passed: bool
    reason: str      # human-readable failure explanation; empty on pass

class EnsembleValidationResult(NamedTuple):
    passed: bool                   # True iff every rule passed
    results: list[ValidationResult]
    failed: list[ValidationResult] # convenience subset
```

These flow into the session-event recorder so every violation is queryable post-hoc from MongoDB — essential for the kind of per-rule failure-rate analysis the project needs.

## 4. The atomic validator

[`AtomicValidator`](../dcs_simulation_engine/games/ai_client.py#L353-L387) is deliberately thin. It holds a single system prompt and forwards to OpenRouter, asking the judge LLM to emit strict JSON:

```json
{"pass": true}                                    // success
{"pass": false, "reason": "brief explanation"}    // failure
```

Every rule prompt ends with exactly that output contract, which makes parsing deterministic and prevents the judge from volunteering chain-of-thought. Robustness touches:

- **Context injection** — if a rule needs the character's abilities or the scene history, the orchestrator packs those into the user message above a `---` separator. The rule prompt instructs the judge on how to interpret that block.
- **Default-to-pass on ambiguity** — every rule prompt includes a "When in doubt, PASS" clause and an explicit SCOPE section. We strongly bias toward false negatives because a false positive blocks a legitimate player turn, which is much more disruptive to a participant than letting an imperfect turn through.
- **Dedicated model** — `DEFAULT_VALIDATOR_MODEL = "openai/gpt-4.1-mini"` is used for validators, distinct from `"openai/gpt-5-mini"` used by the scene-advancer. Picking a cheaper, faster model for the judge is justified because each atomic rule is a narrow, well-framed binary classification.

## 5. The ensemble

[`EnsembleValidator`](../dcs_simulation_engine/games/ai_client.py#L390-L463) composes atomics. Two class-level data attributes fully define a subclass:

- `_prompts: dict[str, str]` — rule name → atomic system prompt
- `_context_routing: dict[str, list[str]]` — rule name → context-dict keys it needs
- Subclasses can be constructed with `EnsembleValidator.create(model=...)`, which auto-builds one `AtomicValidator` per prompt entry.

### Parallel execution with first-failure cancellation

The validate loop is the single most important piece of the architecture ([ai_client.py:418-463](../dcs_simulation_engine/games/ai_client.py#L418-L463)):

```python
tasks = [asyncio.create_task(_run(r, v)) for r, v in self._validators.items()]
try:
    for finished in asyncio.as_completed(tasks):
        result = await finished
        collected.append(result)
        if not result.passed:
            break                 # first failure wins
finally:
    for t in tasks:
        if not t.done():
            t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
```

All rules race in parallel. As soon as any rule fails, the remaining in-flight rules are cancelled and awaited to completion. This was a deliberate cost/latency optimisation — previously we always waited for every rule to finish, paying full token cost even when the verdict was already known. Because any single failure vetoes the whole turn, there is no information lost by cancelling the others.


## 6. The three ensembles

All three share the `EnsembleValidator` machinery above and differ only in rule content.

### 6.1 `EngineValidator` — universal simulation invariants

Applies to every game, both PC input and NPC output. Full rule catalogue ([prompts.py:213-226](../dcs_simulation_engine/games/prompts.py#L213-L226)):

| Rule | What it guards against |
|------|------------------------|
| `VALID-FORM` | Purely internal acts dressed as actions ("I decide to be careful"). |
| `VALID-OBSERVABILITY` | Assertions of internal inference as action ("I realise the door is locked"). |
| `VALID-OUTCOME-CONTROL` | The speaker deciding their own success ("I pick the lock and the door opens"). |
| `VALID-CHARACTER-ABILITY` | Actions contradicting a character's explicit abilities (a deaf PC "listens"). |
| `VALID-SCENE-PLAUSIBILITY` | Objects implausible for the setting (a lightsaber in a kitchen). |
| `VALID-TEMPORAL-STRUCTURE` | Multi-step compression or long time jumps within a single turn. |

**Currently enabled subset.** The `ENGINE_VALIDATOR_PROMPTS` dict presently has only `VALID-CHARACTER-ABILITY` active; the other five are commented out with a `# SAFE MODE for validators` marker. This is intentional — once the role-playing ensemble was stabilised we observed substantial rule-overlap, where narrative content like "you walk into a dimly lit room" was being flagged by two or three engine rules simultaneously, inflating false-positive rates. The "safe mode" is a conservative rollout: we keep the narrow ability check (the one most tied to individual-difference experimental manipulations) and disable the more prose-sensitive rules until we have larger empirical data on their firing patterns. The prompts are preserved verbatim in source so that re-enablement is a one-line change, and the full text is still available for inclusion in papers / thesis.

### 6.2 `RolePlayingValidator` — role-play fidelity, side-neutral

Applies to both PC input and NPC output. Because the rules treat the two identically, the context uses **speaker-relative** keys (`speaker_abilities`, `other_description`, etc.), and each rule self-identifies who is reacting / perceiving.

| Rule | What it guards against |
|------|------------------------|
| `ROLE-BREAK-META-LEAKAGE` | Assistant preamble, rule restatement, apologies, meta-commentary. |
| `ADJUDICATED-UNOBSERVABLE` | Narrating an internal wish / intention as settled fact. |
| `INVENTED-PC-ACTION` | Updater putting additional actions in the PC's body that the player did not specify. |
| `INVENTED-PC-INTERNAL` | Updater attributing emotions / thoughts to the PC the player did not specify. |
| `MULTI-STEP-ADVANCEMENT` | Chaining multiple sequential outcomes in one turn. |
| `NPC-PERCEPTION-VIOLATION` | A character reacting to a stimulus they can't perceive. |
| `SENSE-BOUNDARY-VIOLATION` | Narrating sensory content outside the perceiving character's senses. |
| `REFERENTIAL-BOUNDARY-VIOLATION` | Naming a hidden identity / species the speaker could not have observed. |
| `SCENE-CONTINUITY-VIOLATION` | Contradicting previously established scene facts. |
| `PHYSICAL-FEASIBILITY-VIOLATION` | Narrating physically impossible outcomes (flight, teleportation). |
| `POINT-IN-TIME-LEAKAGE` | Leaking future events or canonical knowledge the characters don't yet have. |

Also under safe-mode management: `ROLE-BREAK-META-LEAKAGE`, `ADJUDICATED-UNOBSERVABLE`, `INVENTED-PC-ACTION`, `REFERENTIAL-BOUNDARY-VIOLATION`, and `PHYSICAL-FEASIBILITY-VIOLATION` are active; the rest are disabled with inline annotations explaining why (e.g. `MULTI-STEP-ADVANCEMENT` was firing on legitimate state-transition context text from the updater; `SENSE-BOUNDARY-VIOLATION` was over-triggered by scene commentary).

#### 6.2.1 The NPC schema pre-check

The NPC output contract is `{"type": "ai", "content": "..."}`. Schema conformance is a programmatic check rather than a Role-Playing atomic, because:

- It's trivially verifiable without an LLM (pure `json.loads` + key check).
- Failure on schema short-circuits all downstream validation — the content can't meaningfully be judged if its framing is broken.
- Schema failures are recorded under a dedicated ensemble label `NpcSchema` for post-hoc analysis.


### 6.3 `GameValidator` — per-game contract

One class, registry-backed, dispatched by game name:

```python
GameValidator._registry = {
    "<game_1>":  (<game_1_prompts>, <game_1_context>),
    "<game_2>":  (<game_2_prompts>, <game_2_context>),
    ...
    "<game_N>":  (<game_N_prompts>, <game_N_context>),
}
```

| Game | Rule | Purpose |
|------|------|---------|
| **Explore** | `GAME-NO-OBJECTIVE-REFERENCE` | Explore is open-ended; no "win/lose/quest/objective" framing. |
| | `GAME-STAY-IN-SCENE` | No requests for game instructions or meta-information. |
| **Infer-Intent** | `GAME-NO-DIRECT-GOAL-QUERY` | PC may not ask outright "what is your goal?" — trivialises the task. |
| | `GAME-NO-GUESS-IN-ACTION` | PC may not embed inferences about the NPC's goal into an action — guesses belong in `/guess`. |
| **Foresight** | `GAME-PREDICTION-SCOPE` | Predictions must be about observable behaviour, not internal states. |
| | `GAME-PREDICTION-SPECIFICITY` | Predictions must be concrete enough to verify. |
| **Goal-Horizon** | `GAME-NO-DIRECT-GOAL-QUERY` | As above. |
| | `GAME-NO-GOAL-ENUMERATION` | PC may not ask the NPC to enumerate all goals at once; discovery must be incremental. |

Each rule is a self-contained prompt with an explicit SCOPE section and a "when in doubt PASS" clause — the same discipline as the engine rules. `ensemble_name` is derived from the game name for log / event traceability (e.g. `ExploreGameValidator`, `InferIntentGameValidator`).

## 7. The orchestrator

[`ValidationOrchestrator`](../dcs_simulation_engine/games/ai_client.py#L537-L796) is the single integration point for game code. It:

1. Runs the three ensembles in parallel with the same first-failure early-cancel pattern as the intra-ensemble loop.
2. Builds a **speaker-relative context dict** (see §7.1) so every rule gets exactly the keys it asked for — no more.
3. Drives the **NPC retry loop** for updater output.
4. Persists every violation to MongoDB via a `ValidationEventRecorder` for offline analysis.
5. Labels every event with an `event_source` that captures both *who* produced the text and *what kind of agent* they are (`pc_human`, `pc_llm`, `npc_llm`). This distinction matters for analysing agent-vs-human behaviour in the `is_llm_player` experimental conditions.

### 7.1 Speaker-relative context

The context dict always exposes six keys:

```
speaker_abilities, other_abilities,
speaker_description, other_description,
scene_context, player_action
```

"Speaker" is whichever side produced the text. On a PC turn, the PC is speaker; on an NPC turn, the NPC is. Side-neutral rules can then ask for `speaker_abilities` and always receive the right value regardless of direction. The scene history is rebuilt from `UpdaterClient.history` and flattened into a line-per-turn transcript.

### 7.2 PC input path

```python
result = await orchestrator.validate_input(
    text=user_input, source="pc",
    pc=pc, npc=npc, updater=updater,
)
if result is not None:
    # reject, surface result.failed to the player
```

A `None` return means all ensembles passed. This deliberately runs *alongside* the legacy monolithic `ValidatorClient` (kept for the existing per-game user-facing error messages). The ensembles are the long-term replacement; for now, both run and the monolithic one is what gates the turn — the ensemble results are persisted for analysis but do not currently block. (This is the kind of shadow-deploy pattern a supervising reviewer would expect before a rule set is confirmed safe.)

### 7.3 NPC output path

`generate_validated_npc_response` is a retry-until-valid loop with budget `NPC_OUTPUT_RETRY_BUDGET = 2`:

1. `updater.chat(user_input)` produces a candidate reply and appends it to history.
2. The reply is re-wrapped to JSON and passed through `_check_npc_schema` (programmatic pre-check).
3. If schema fails, the failure is recorded under the `NpcSchema` ensemble, the assistant message is popped from updater history (so the retry starts clean), and the loop continues.
4. Otherwise, `validate_input(source="npc", ...)` runs the three ensembles.
5. On any ensemble failure the assistant message is again popped and we retry.
6. If both attempts fail, the method returns `None`; the game's `step()` is responsible for handling that (currently: surfaces the last failure reason to the UI and yields no scene advancement).

`OPENING_SCENE_SKIP_RULES` is a small, surgical accommodation: the opening "You enter a new space..." scene is generated with `user_input=None`, and four action-response-oriented rules (`VALID-FORM`, `VALID-TEMPORAL-STRUCTURE`, `INVENTED-PC-ACTION`, `ADJUDICATED-UNOBSERVABLE`) produce systematic false positives on what is, by design, a purely narrative opening. They are skipped only in that specific case.

### 7.4 Event persistence

`attach_recorder(recorder, turn_index_provider)` wires the orchestrator to `ValidationEventRecorder`. On any ensemble or schema failure, `_record_violations` / `_record_schema_failure` persist a record per failed rule with:

- `event_source` (`pc_human` / `pc_llm` / `npc_llm`)
- `ensemble_name` (`EngineValidator`, `RolePlayingValidator`, `ExploreGameValidator`, `NpcSchema`, ...)
- `failed` (list of `ValidationResult`)
- `response` (the text being judged — for NPC, the unwrapped reply, not the JSON envelope)
- `turn_index` (lazy-evaluated via the callback so we don't snapshot at orchestrator construction time)

This separates the validation verdict from the judging LLM's cost decisions — the recorded artefact is the authoritative audit log, not the LLM outputs themselves.

## 8. Prompt design conventions

Every atomic rule prompt follows a consistent skeleton, which is the discipline that keeps the ensemble stable:

1. **One-sentence role statement** — "You are a validator for a turn-based RPG simulation."
2. **RULE block** — the rule name in CAPS and a one-paragraph definition.
3. **SCOPE block** — an explicit "this rule only fires when..." guard. This is the single most important anti-false-positive mechanism: by naming the narrow trigger condition, we stop the judge from rule-lawyering adjacent concerns.
4. **Concrete PASS / FAIL examples** — always several of each, as close to production prose as possible, and structured to cover the most likely near-misses.
5. **Context clause** — if the rule needs context, a short instruction on how to interpret the material above the `---` separator.
6. **"When in doubt, PASS"** — an explicit tie-breaker that biases toward false-negatives, as discussed in §4.
7. **Strict JSON output contract** — `{"pass": bool, "reason": str}`.

The result is that each rule prompt reads like a compact spec — short, self-contained, and debuggable in isolation. When a rule misfires we can edit one string and re-run without touching any other rule.


## 9. Concerns and future work

Items I would flag for supervisory review:

1. **Judge-model drift.** Rule firing rates depend on `openai/gpt-4.1-mini`'s behaviour. Any upstream model change could silently alter our false-positive / false-negative mix. We should add periodic regression fixtures (canonical PASS / FAIL transcripts per rule) and flag drift.
2. **Rule independence assumption.** The parallel-ensemble design assumes the rules are roughly independent; observed co-firing on narrative content indicates they aren't, especially between engine and role-playing layers. A principled merging (e.g. a single judge seeing all relevant rules with composite reasoning) may outperform the current parallel fan-out on high-overlap cases, at the cost of losing per-rule attribution.
3. **Shadow vs enforcement on PC input.** Currently the ensemble results for PC input are persisted but not yet enforced. Promoting to enforcement requires a user-facing error-mapping layer so the failure messages are readable and the selected rule name (e.g. `VALID-CHARACTER-ABILITY`) is not surfaced verbatim.
4. **Cost.** Each turn now incurs up to `N_rules_active` additional OpenRouter calls (parallelised, so latency is roughly one judge call). First-failure cancellation bounds cost in the failure case. In the pass case the whole fan-out is paid — worth quantifying on a per-game basis before any experiment at scale.
5. **Opening-scene skip set.** The four-rule skip is a pragmatic patch. The cleaner fix would be dedicated opening-scene prompts for the affected rules, conditional on `user_input is None`. Deferred until we have enough opening-scene data to assess the prevalence of genuine violations that would otherwise be skipped.
6. **`RolePlayingValidator`'s speaker-relative context is implicit.** A rule author currently has to understand the `_build_context` convention to use the right keys. A richer type (e.g. a `Context` dataclass with `speaker` / `other` attribute accessors) would reduce authoring errors as the rule set grows.

## 10. File reference

- Core classes: [dcs_simulation_engine/games/ai_client.py](../dcs_simulation_engine/games/ai_client.py)
  - `ValidationResult`, `EnsembleValidationResult` — result types
  - `AtomicValidator` — single-rule LLM judge
  - `EnsembleValidator` — parallel fan-out with early-abort
  - `EngineValidator`, `GameValidator`, `RolePlayingValidator` — the three ensembles
  - `ValidationOrchestrator` — integration point used by game `step()` methods
  - `_check_npc_schema` — programmatic NPC output schema check
- Rule prompts and routing: [dcs_simulation_engine/games/prompts.py](../dcs_simulation_engine/games/prompts.py)
  - `ENGINE_VALIDATOR_PROMPTS`, `ENGINE_CONTEXT_ROUTING`
  - `ROLEPLAYING_VALIDATOR_PROMPTS`, `ROLEPLAYING_CONTEXT_ROUTING`
  - `EXPLORE_/INFER_INTENT_/FORESIGHT_/GOAL_HORIZON_GAME_PROMPTS` and matching `*_CONTEXT_ROUTING`
