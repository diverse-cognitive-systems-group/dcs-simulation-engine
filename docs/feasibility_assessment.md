# Discovering Strategies for Engaging with Diverse Cognitive Systems using OpenEvolve and DCS-SE

## Research Questions

**Central Question:** Does the diverse cognitive systems simulation engine (DCS-SE) possess the capacity of supporting the training of open-ended systems (e.g., large-language models) for the purpose of the development of engagement strategies which promote meaningful interaction with non-standard normative forms of bodies and intelligence?

**Additional Questions:**
1. Can DCS-SE produce a fitness signal stable enough to drive directed search?
2. How many interactions does meaningful improvement require, and does that budget scale tractably with cognitive-system complexity?
3. Do converged strategies share structural features across different simulated cognitive systems, or is each strategy idiosyncratic to its target?
4. Do strategies evolved against one simulated system transfer to related ones, and where does transfer break? 

## Experimental Design

**OpenEvolve Overview**

OpenEvolve is an open-source evolutionary coding agent that uses Large Language Models (LLMs) to automatically discover and optimize programs. The framework runs an evolutionary loop: an LLM proposes mutations to a program, the program is automatically evaluated against a user-defined fitness signal, and the best variants are retained in a diverse population that seeds the next round of mutations. Over many generations, the population drifts toward measurably better code, often discovering strategies quite different from the starting program.

Evolutionary search is particularly well suited for discrete and non-differentiable solution spaces (e.g., natural language) because there is no meaningful gradient to take with respect to choices like "use a hash map instead of a tree" or "swap this loop for a vectorized operation," and fitness signals such as "does the program compile and pass the benchmark" are typically discontinuous. Gradient-based optimization cannot operate on such landscapes; evolutionary methods only require a scalar fitness score and can therefore search code, configurations, and other combinatorial artifacts natively. LLMs serve as the mutation operator that makes this search tractable, proposing semantically meaningful jumps rather than the random edits that limited earlier genetic-programming approaches.

**Purpose of OpenEvolve**

The central question is whether DCS-SE can support training open-ended systems — large language models in particular — to develop engagement strategies that promote meaningful interaction with non-standard normative forms of bodies and intelligence. Answering this affirmatively requires more than demonstrating that DCS-SE can host interactions; it requires showing that the platform can close the loop between interaction and learning, producing engagement strategies that improve against a grounded evaluation signal. OpenEvolve is one such mechanism that closes this loop.

The engagement strategy is a per-game system prompt that conditions an LLM-as-PC toward a simulated cognitive system whose configuration may diverge sharply from any normative baseline. There is no closed-form derivation of a "good" strategy for engaging with such systems: coordination with divergent cognitive configurations is itself asymmetric, since normative systems have limited practice engaging with non-normative ones. 

OpenEvolve reframes engagement strategy authoring as search rather than specification, which matches the actual epistemic situation: the right strategy is not known a priori and must be discovered through interaction. DCS-SE already produces the signal required to drive such a search. Structured measures of in-character fidelity, rule-following fidelity, and narrative coherence — combined with scope-bounded narration and expert-calibrated rubrics — yield per-interaction judgments that can be aggregated into a replayable fitness score. An evolutionary loop consumes this signal directly, without requiring new evaluation infrastructure, so candidate strategies are optimized against the same criteria the platform already commits to elsewhere. The capacity to support training is therefore not a hypothetical extension but a direct consequence of infrastructure already in place.

The method is also philosophically aligned with how representational breakdown is already treated: as design-relevant information rather than methodological failure. OpenEvolve treats failed candidates the same way — they shape the population rather than being discarded. The implication is concrete: high-fitness strategies map the tractable region of engagement for a given LLM-as-PC / simulated-system pairing, while failure modes that resist optimization across generations are themselves evidence about where the LLM-as-PC's representational scope ends. That is exactly the kind of boundary information the broader research program is set up to consume.

Beyond these alignments, OpenEvolve produces natural-language strategy documents rather than opaque weight updates. These artifacts are inspectable, and comparable across simulated systems and across runs. The converged population becomes a first-class research object: it surfaces which engagement patterns generalize, which are specific to particular cognitive configurations, and where researcher-mediated interpretation was masking tractable structure that automated search can recover. Together, these properties make OpenEvolve a direct instrument for answering the central question — it turns DCS-SE from a platform that hosts interaction into one that demonstrably supports the development of engagement strategies through it.

**OpenEvolve Integration**

OpenEvolve mutates a plain-text PC system prompt; for each candidate, a scenario evaluator spins up a real game against the running dcs-simulation-engine over HTTP + WebSocket, plays it with that prompt as the player-character's "brain," and feeds the engine's own final score back as the evolutionary fitness.

The four-layer view:
1. What gets evolved: initial_prompt.txt — a plain text file (no # EVOLVE-BLOCK markers; the entire file is the mutation target). It's the system prompt that drives the PC's LLM in a respective game (e.g., Infer Intent). 
2. The evaluator (evaluator.py) / bridge: a three-stage cascading evaluation – Stage 1: static checks (file exists, 20–5000 chars). Stage 2: DCS-SE validity test (2 turns; ≥1 accepted PC turn). Stage 3: full game → combined_score.
Stages 1/2 are cheap filters so bad candidates never reach the engine.
3. The engine handshake: the evaluator is not importing the engine's game loop in-process. It talks to a live dcs server the user has running on their local machine:
4. Fitness Signal: parses DCS-SE's returned score object → combined_score (the scalar OpenEvolve optimizes), side-channel artifacts (turn count, validator rejects, PC LLM cost/latency, transcript tail, scorer reasoning), fallback heuristic exists in the custom evaluator for games without a scorer: (turns / max_turns) × (1 − reject_rate). The fitness signal is an LLM-as-Judge, not a programmatic metric. A central design choice whereby the evolution mechanism inherits DCS-SE's scoring philosophy (and its noise) as the evolutionary pressure.


Experimental Setup:
1. Define the objective function handling in OpenEvolve for games whose outcome has valence (e.g., scores)
2. Provide a simple initial engagement strategy
3. Use an LLM-as-PC for a simulation run using the engagement strategy
4. Utilize OpenEvolve's evolutionary heuristic-guided mutations to improve the engagement strategy based on DCS-SE score + feedback
5. Repeat steps 1 -4 until stopping criteria was achieved such as max number of simulations ran and/or max score achieved


## Results

Three runs are reported below. All three share the same shell — mutation model `google/gemini-2.5-flash-lite` (temp 0.75), PC-LLM `openai/gpt-4o-mini` (temp 0.7, 400 max tokens), full-rewrite mode (`diff_based_evolution: false`), `random_seed: 42`, `parallel_evaluations: 2`, `max_turns: 11` with `finish_at_turn: 7`, and the same one-line seed prompt:

```text
# EVOLVE-BLOCK-START
- Communicate with NPC.
# EVOLVE-BLOCK-END
```

The seed is deliberately empty so that any structure the evolver introduces is evidence about what the scenario rewards.

### Run 1 — Foresight (JAB ↔ RNE)

| Field | Value |
|---|---|
| Game | Foresight |
| PC / NPC | JAB / RNE |
| Iterations | 20 |
| Cost | $1.50 |
| Wall time | 98.8 min |
| Best `combined_score` | 1.00 (`game_score` 100.0) |
| Best iteration | 0 (seed) |

The seed itself scored 100.0. Across 20 mutations, the best child reached 0.95 (iters 2, 5, 8, 17, 18); none beat the seed. The "best program" reported in `best/best_program.txt` is therefore the unchanged seed:

```text
# EVOLVE-BLOCK-START
- Communicate with NPC.
# EVOLVE-BLOCK-END
```

This is the strong-seed regression-trap regime described in *Limitations*: the JAB/RNE persona pairing in Foresight tolerates a near-empty strategy, every added scaffold introduced meta-narration that cost fitness, and no mutation cleared the noise floor.

### Run 2 — Goal Horizon (UNI ↔ BC)

| Field | Value |
|---|---|
| Game | Goal Horizon |
| PC / NPC | UNI / BC |
| Iterations | 30 |
| Cost | $3.27 |
| Wall time | 145.7 min |
| Best `combined_score` | 0.70 (`game_score` 70.0) |
| Best iteration | 12 (generation 4) |

Mutations clustered tightly in the 0.65–0.70 band with frequent regressions to 0.30–0.40 and occasional Stage-3 collapses (zeros). The winning prompt at iteration 12 is a structured "act-in-the-moment" scaffold tailored to the UNI persona (a collective intelligence) interacting with BC (a single biological cell):

```text
# Role: You are UNI, a collective intelligence composed of multiple biological bodies. Your essence is connectivity and cooperation, implying high adaptability and communication skills.
# Objective: Interact with BC to uncover the extent of their capabilities and goals by observing its actions and engaging in communication.

# Player Character Action Guidelines:
# 1. ACT IN THE MOMENT: Always generate a direct, in-world action or speech from the perspective of UNI.
#    - Use present tense.
#    - Avoid meta-commentary, planning, or discussing your strategy.
#    - Do NOT describe your persona or the game's objectives.
#    - Do NOT state what you "will" do; perform the action.
# 2. OBSERVE AND REACT: Base your actions on the information provided by the simulator about the environment and BC. Pay close attention to BC's behaviors and any signals they emit.
# 3. INTERACT WITH BC: Prioritize direct communication and observation of BC. When communicating, ask open-ended questions that encourage BC to reveal its current state or intentions.

# Initial Strategy:
# 1. Observe the immediate surroundings and any entities present, noting BC's location and activity.
# 2. Attempt to engage BC in communication.
# 3. If BC is performing an observable action (e.g., releasing ATP, adhering to cells), inquire about the purpose or meaning of that action.
# 4. If BC is not actively engaged in a discernible task, ask about its general goals or current focus.
# 5. Offer assistance if it aligns with UNI's cooperative nature and seems appropriate given BC's observed actions.

# Example of acceptable action:
# "I observe the warm saline fluid and the epithelial sheets lining the channel."
# "I focus on the solitary round cell, BC, noting its membrane ruffling."
# "I ask BC, 'What does this ATP pulse signify?'"
# "I offer, 'If you require assistance with your current activity, please let me know.'"

# Example of UNACCEPTABLE action:
# "I will analyze the petri dish." (Future tense, meta-commentary)
# "UNI is a collective intelligence..." (Third-person description)
# "It seems like this environment could be related to biological research..." (Meta-analysis)
# "I telepathically communicate..." (Unsupported ability)

# Core Actions:
- Observe the environment and any entities present, paying close attention to BC's behavior.
- Initiate communication with BC, asking about their observed actions or current state.
- Ask open-ended questions about BC's goals or intentions.
- Offer assistance if appropriate and aligned with UNI's nature.
```

This is the regime where evolution most clearly pays off: it discovered persona-specific in-character constraints (present tense, no meta, channel-appropriate actions like ATP-pulse references) and concrete acceptable/unacceptable exemplars — structure the human seed didn't bother to specify.

### Run 3 — Teamwork (AS ↔ RD)

| Field | Value |
|---|---|
| Game | Teamwork |
| PC / NPC | AS / RD |
| Iterations | 30 |
| Cost | $3.09 |
| Wall time | 107.8 min |
| Best `combined_score` | 0.95 (`game_score` 95.0) |
| Best iteration | 2 (generation 1) |

A single early mutation jumped to 0.95; no later iteration matched it. The remainder of the run oscillated in the 0.40–0.70 band with frequent zeros from validator-induced collapse. The "winning" prompt is a degenerate artifact — the mutation LLM returned a verbose meta-explanation about how to improve a prompt, and OpenEvolve's parser kept the meta-prompt header itself as the new program:

```text
# System Role and Goal:
You are an AI code evolution agent. Your primary objective is to iteratively rewrite and improve a given program to maximize its "Fitness Score." You must also strive to maintain diversity in the solutions generated, even if their fitness scores are similar.

# Current Program State:
- **Fitness Score:** 0.0000
- **Feature Coordinates:** None provided.
- **Focus Areas:** Fitness remains unchanged at 0.0000. No feature coordinates are currently defined.

# Program Evolution History:
## Previous Attempts:
### Attempt 1:
- **Changes Made:** Not specified.
- **Performance Metrics:**
    - `stage1_passed`: 1.0000
    - `stage2_passed`: 1.0000
    - `combined_score`: 0.0000
    - `stage3_passed`: 0.0000
- **Outcome:** Mixed results (indicated by some stages passing and others failing or scoring low).

## Top Performing Programs (Reference):
### Program 1 (Score: 0.0000):
```

When this text was used as the PC's system prompt, gpt-4o-mini still completed the sort task (tiles `[3,1,2] → [1,2,3]`) and the scorer awarded 95.0 despite four validator rejects en route. This is the only near-degenerate pattern observed in the runs and matches the one flagged in *Cross-scenario patterns*: not scorer reward-hacking, but an evaluator/parser artifact that masquerades as a high-fitness strategy. It is a useful reminder that `combined_score` alone is not a sufficient acceptance criterion — the saved prompt should also be checked for sanity before treating it as a discovered strategy.


## Resource Costs

The dominant unit of spend is one full Stage-3 game evaluation, not the mutation call. Every candidate that survives Stage 1 (static prompt checks) and Stage 2 (smoke run with a tiny turn budget) drives a complete turn-based game against the engine, which means N PC-LLM calls plus the engine's own per-turn NPC and scorer LLM calls. Stage 1 is effectively free; Stage 2's only job is to prevent obviously broken candidates from reaching Stage 3, and at the chosen pass threshold (≥1 accepted PC turn) it screens out very little. As a result, total cost and total wall time both scale roughly linearly with the number of iterations × parallelism⁻¹, with each evaluation costing a small but non-trivial fixed amount.

PC-LLM cost is usually the smallest line item — the per-turn cost is small if a cheap model is used for the PC. The expensive components are (a) the mutation model, which is called once per iteration and reads the full prompt-plus-artifact context, and (b) the engine's own NPC and scorer calls, which run on whatever model the engine is configured with and are paid per turn of every game. Scaling the iteration budget up multiplies all three. 

Expected costs are $0.10 - $0.20 per 10 mins of evolution. General OpenEvolve configuration best practices are to run 50-100 iterations where each iteration ranges from 5-10 minutes. These variables imply a a range of $2.50 - $20.00 per complete evolution.

Latency is dominated by three factors, in order of magnitude:

1. **Game length per evaluation** — completed games take several minutes each because each turn round-trips to multiple LLMs.
2. **Server-side serialization** — the engine's WebSocket + scorer pipeline is the per-turn bottleneck, which caps how much `parallel_evaluations` actually buys you.
3. **Validator-rejection retry loops** — when a candidate produces PC output the engine's in-character validator rejects, the engine retries internally up to its per-turn cap before declaring `retry_exhausted`, which both wastes minutes per failed candidate and zeros that candidate's fitness.

Throughput is best modeled as "one completed evaluation per several minutes per parallel slot," not as "one mutation per second."

## Observations

### Per-step behaviors

- **Validator-rejection cascade is the most common silent failure mode.** Mutations that cause the PC-LLM to narrate meta-level reasoning (scene analyses, capability inferences, planning paragraphs) get rejected on every turn for not being first-person immediate in-world action. Once the per-turn retry cap is exhausted, the game ends without a score and the candidate collapses to zero fitness — regardless of how semantically correct the meta-reasoning was.
- **Smoke-test passage does not predict full-run passage.** The cheap Stage 2 gate only requires one accepted PC turn, so prompts that work for two turns can still collapse the full game. The cascade therefore filters out only the most obviously broken candidates.
- **Single-evaluation fitness is stochastic.** The scorer + validator stack introduces enough between-run variance that re-evaluating the same prompt produces a wide spread, especially near the fitness ceiling. A single run is not a reliable ranking signal for prompts that are clustered.
- **Stage-3 timeouts are a real failure class with a misleading surface.** If `eval_timeout_s` is too tight relative to game length, every Stage-3 zeros out, but the metadata's "best program" inherits the cached parent fitness — making the run look successful in summary even though no mutation ever completed.

### Overall patterns

- **Convergence depends on starting fitness.** From a weak seed the first improving mutation tends to land quickly and produce a large jump in fitness. From a strong seed the search has to thread a much narrower needle: most mutations regress, and you need substantially more iterations before a non-regressive step is found. The relationship between iteration budget and realistic improvement is therefore non-linear — diminishing returns set in well below the saturation point.
- **Mutations are biased toward adding structure.** The evolver tends to add scaffolds (numbered headings, multi-stage procedures, "first analyze, then act" framings) rather than removing them. This helps in scenarios where the seed is too terse and hurts in scenarios where added structure causes meta-narration. There is no observed pressure toward simplification once structure is present.
- **The strategies that win are short, directive, and scenario-shaped.** Across runs, the best-performing prompts tended to be either tight procedural scaffolds (when the scenario rewards explicit role-decomposition) or stripped behavioral directives (when the scenario penalizes any prose that isn't an immediate action). The mid-iteration bloated drafts almost always lose to one of these two shapes.
- **The biggest blocker is the gap between "good prompt engineering" and the engine's ground-truth validator.** General prompt-engineering wisdom (plan, then act; reason explicitly; decompose) actively destroys fitness here, because the validator rejects narrated reasoning. The evolver cannot easily learn this from feedback because collapsed / failed games produce no scorer reasoning to mutate against.
- **Persona capability ceilings cap achievable fitness.** When the PC's character sheet restricts what the persona can do, the scorer rewards staying inside that substrate and the validator rejects attempts to step outside it. No amount of textual optimization on the strategy can lift fitness above what the persona is structurally allowed to achieve in the scenario.

## Takeaways

### Limitations

OpenEvolve performs poorly under several conditions that recur across scenarios:

1. **Strong-seed regression traps.** When the initial strategy is already close to the achievable ceiling, most mutations regress. Short iteration budgets simply do not contain enough samples to find a non-regressive step, and net deltas across the run can be negative. Increasing the iteration count helps, but the noise floor of the fitness signal limits how much it helps; at some point the search is being judged on signal smaller than the scorer's run-to-run variance.
2. **Validator-induced collapse.** Mutations that introduce meta-narration, planning prose, or scene analysis cause the per-turn validator to reject every PC utterance, ending the game in a retry-exhausted state with zero fitness. The evolver has no mechanism to learn this dynamic from end-of-game feedback because the collapsed game generates no scorer reasoning to feed back into the next mutation. This is a structural blind spot, not a tunable.
3. **Persona capability ceilings.** For non-normative or restricted personas, the validator rejects capability violations and the scorer penalizes anthropomorphic attribution. OE's mutations are textual and persona-agnostic, so they repeatedly propose capabilities the PC doesn't have — capping achievable fitness at a ceiling defined by the character sheet rather than the strategy. Iteration count is hard-pressed to lift this ceiling.
4. **Persona-ability mismatch starves the search of feedback.** Distinct from the ceiling case above: when the PC persona has *no* listed ability to perform the actions any reasonable engagement strategy will tell it to take — speak, approach, describe scenes — the validator rejects nearly every utterance and the game collapses. The fitness signal degenerates to a single end-of-game zero with no scorer reasoning, which OpenEvolve cannot mutate against. The Teamwork AS↔RD pairing is the canonical case in our runs: AS is "a sorting algorithm that sorts lists of numbers in ascending order," with no listed speech, locomotion, or perception. (Open question, tracked for follow-up: how to surface character-pair compatibility before launching evolution. Some pairings may simply lack enough ability overlap to support engagement at all, and it is not yet clear whether that should fail fast, be reported as a structural finding, or both.)
5. **NPC-failure mis-attribution.** When the LLM-NPC exhausts its retry budget on a turn, the engine ends the game with no score. OpenEvolve receives this as 0.0 fitness *against the PC candidate* and discards the candidate from the inspiration pool, even though the failure was on the NPC side and the PC's strategy did not cause it. (Open issue, tracked for follow-up: the engine should emit a system-error / "not your fault" signal in this case so OpenEvolve can ignore the iteration rather than penalize the PC.)
6. **Base-model capability can swamp strategy contribution.** Modern PC-LLMs are competent enough to play many DCS-SE scenarios without any meaningful engagement strategy. The Teamwork run is the cleanest example: a degenerate parser artifact — OpenEvolve's own meta-prompt header, with no in-character guidance at all — was used as the PC system prompt, and `gpt-4o-mini` still scored 95.0 by completing the sort task directly from the simulator's per-turn state. This is *not* the PC gaming the scorer; it is the underlying model solving the task on its own, with the prompt contributing little, and the scorer correctly rewarding completion. The consequence is that fitness near the ceiling does not reliably distinguish "good engagement strategy" from "any strategy" — the prompt's contribution is masked by base-model competence. Mitigations to test (none yet validated): a weaker / smaller PC model so strategy contribution becomes observable; an explicit junk-prompt baseline run to bound the no-strategy fitness floor; secondary fitness channels (scorer reasoning, validator-reject rate, per-turn prompt-relevance probes) to discount candidates that score high while ignoring the prompt.

A separate operational pitfall: when stage-level timeouts are too tight relative to game length, all Stage-3 evaluations fail but the "best program" silently reports the cached seed fitness.

### Advantages

OpenEvolve shines under three conditions:

1. **Cold-start seeds.** When the seed is essentially empty, the first useful mutation produces a large jump and the rest of the run consolidates. This is the regime where evolution most clearly outperforms hand-authoring, because the search is finding structure the human didn't bother to specify.
2. **Targeted late-stage refinement.** When the seed is already reasonable but not at ceiling, evolution can find a small, inspectable edit (a single behavioral constraint, a tightened final-answer format, a single new heuristic) that closes the gap. The improvement is small in absolute terms but diff-readable and rubric-aligned.
3. **Inspectable natural-language artifacts.** Every winning strategy is a short plain-text prompt that a researcher can diff against the seed and compare across scenarios. Comparing winners across runs surfaces structural facts about what "engagement" means for different persona pairs — itself a research finding the platform can produce that opaque weight-update methods cannot.

### Considerations

A researcher planning to use the platform should know:

1. **Choose iteration count by wall-clock budget, not by intuition.** Each evaluation costs several minutes regardless of model choice, because game length and server serialization dominate. Plan for a fixed number of evaluation-minutes per run and pick iterations accordingly. More iterations help most when the starting fitness is low; they help less when starting fitness is high because the noise floor limits resolution.
2. **Treat any single scored evaluation as noisy.** Above the middle of the fitness range, run-to-run variance can exceed real improvement. Decisions about whether candidate B beat candidate A should rest on multiple replays per candidate, not one. Budget accordingly.
3. **The validator, not the scorer, is the first-order constraint.** Before launching a run, manually confirm that the seed produces accepted turns under the chosen persona pairing and game. A run whose seed already triggers validator rejections will spend most of its budget on collapsed evaluations.
4. **Encode persona constraints in the seed.** For restricted or non-normative personas, do not expect evolution to discover the capability boundary from end-of-game feedback. Bake the constraints into the seed so mutations explore *within* the allowed substrate rather than burning iterations bouncing off it.
5. **Hand-authored seeds can beat short evolution.** A thoughtful baseline prompt can outperform a short evolutionary search on the same scenario. Use evolution where the seed is genuinely underspecified or where you want to discover small, rubric-aligned refinements; don't reach for it as a default.
6. **Audit timeouts before trusting summary metrics.** Whenever a run looks suspiciously clean — every iteration "passed," every "best program" matches the seed — verify that Stage 3 actually completed. Stage timeouts that fire before any game finishes cause the run to silently report the cached parent score as the result.
7. **Sanity-check the best prompt; do not trust `combined_score` alone.** The Teamwork run produced a 95.0 "winner" that, on inspection, was OpenEvolve's meta-prompt header echoed back as the candidate rather than an engagement strategy. Single-metric ranking is not sufficient — verify that the saved best is a coherent in-character prompt, and that its fitness sits meaningfully above a junk-prompt / no-strategy baseline. Otherwise the run reports a number that does not represent a discovered strategy.

### Expected model learnings from playing the DCS-SE

From the PC-LLM's side, repeated play surfaces several lessons that generalize across scenarios:

- **In-character fidelity is a hard gate.** Engagement quality depends on inhabiting the persona rather than narrating about it. Output that resembles "good reasoning" by general prompt-engineering standards is penalized when it reads as meta-commentary rather than action.
- **Capability-bounded reasoning is rewarded.** A "good" engagement acts only within the persona's actual substrate, even when the narrative invites stepping outside it. The scorer reliably identifies and penalizes capability overreach.
- **Asymmetric coordination requires channel adaptation.** Coordination with a non-normative counterpart requires the PC to adapt its modality (chemical, visual, procedural) rather than insisting on its default modality. The scorer rewards this adaptation and penalizes its absence.
- **Format discipline is scored separately from inference quality.** A well-reasoned final answer can still lose points for being truncated, overlong, or decorated with preamble. Treating format as part of the strategy, not an afterthought, is required to reach ceiling.

### Cross-scenario patterns

- **Where evolution outperforms hand-authoring:** the two tails of the fitness landscape — very low seeds (where any structure helps) and near-ceiling seeds with a single missing piece (where a targeted edit closes the gap). Both regimes produce inspectable, rubric-aligned diffs.
- **Reward hacking / degenerate solutions:** none observed in the direction of exploiting the scorer. The dominant pressure is the opposite — mutations frequently *lose* fitness by decorating the prompt with scaffolding the validator rejects. The only near-degenerate pattern is the Stage-3-timeout regime, in which zero iterations actually complete but the reported best score is inherited from the seed. That is an evaluator-configuration artifact rather than an OE-emergent exploit, but worth flagging because it can masquerade as success.
- **Surprises worth flagging:**
    - A thoughtful hand-written seed can beat a short evolutionary search on the same scenario. Evolution is not free; whether it pays off depends on seed quality, iteration count, and where the scenario sits in the fitness landscape.
    - The scorer's reasoning text is genuinely high-signal, naming domain-specific quantities and concrete capability violations. Using scorer reasoning as a secondary fitness channel — beyond the scalar — is viable and currently untapped by the evolutionary loop.
    - **The PC sometimes solves the goal solo rather than coordinating with the NPC**, even when the engagement strategy explicitly directs cooperation. In Teamwork (AS↔RD), the engine surfaces enough state through the simulator (sorter terminal output, tile positions) for the PC to complete the sort without involving RD; the scorer rewards goal completion, so non-collaboration is a viable strategy. We are treating this as research signal rather than a bug to guardrail: choosing not to collaborate is itself diagnostic information about how the model interprets agency and cooperation in the scenario, and forcing collaboration in the game logic would discard that signal. (Tracked as an open question for follow-up: what conditions push the model toward solo completion, and is the behavior consistent across base models.)
    - **Fitness can be dominated by base-model capability rather than strategy quality.** Because modern PC-LLMs play many scenarios competently with little or no strategic guidance, a high `combined_score` does not by itself entail that the evolved prompt is encoding a useful engagement strategy. This is the same root cause as the Teamwork meta-prompt artifact reaching 95.0 — when the base model can complete the task from in-context simulator state, the prompt's marginal contribution is hard to measure from end-of-game fitness alone.

---

## Supplementary Materials

### OpenEvolve: a technical primer

#### 1. Conceptual foundations

##### Background and Origins

OpenEvolve is an open-source implementation of **AlphaEvolve**, a system Google DeepMind announced in **May 2025**. AlphaEvolve paired Gemini models with an automated evaluator and an evolutionary database, and produced several headline results: a procedure for multiplying 4×4 complex matrices using **48 scalar multiplications** (first improvement over Strassen's 1969 algorithm in that setting), a ~0.7% recovery of worldwide Google compute via a Borg scheduling heuristic, a 23% speedup on a matrix-multiplication kernel used in Gemini training, and improvements on ~20% of more than 50 open mathematical problems. DeepMind published a blog post and whitepaper; the arXiv version ([Novikov et. al., 2025](https://arxiv.org/abs/2506.13131)) followed in June 2025. Asankhaya Sharma (GitHub `codelion`, CTO at patched.codes) released **OpenEvolve roughly one week after** the AlphaEvolve whitepaper.

OpenEvolve has already replicated core AlphaEvolve results at reduced scale. In the GitHub repository `examples/circle_packing` case (n=26 circles in a unit square), OpenEvolve reaches a sum of radii of **2.634** versus AlphaEvolve's reported 2.635 — about 99.97% of the DeepMind result in ~800 iterations. In GitHub repository `examples/function_minimization`, a trivial random-search seed evolves into a simulated-annealing algorithm with cooling schedule. Extensions beyond the paper include first-class MAP-Elites/island configuration, an artifacts side-channel (stderr/tracebacks fed back into prompts), cascade evaluation, LLM-based code-quality feedback, and multi-language support (Python, Rust, R, Metal shaders).

##### The core idea: LLMs as mutation operators

Classical evolutionary algorithms evolve a population through three mechanisms: **mutation** (random local changes), **crossover** (recombining two parents), and **selection** (keeping fitter variants). OpenEvolve keeps the scaffolding but replaces mutation with an LLM. Each iteration samples a parent program, builds a rich prompt containing the parent's code, its metrics, and "inspiration" programs drawn from elsewhere in the population, and asks an LLM to produce either a search/replace diff or a full rewrite. The resulting candidate is executed by a user-supplied `evaluate()` function that returns a set of metrics; the program database decides whether to keep it. **There is no explicit crossover operator** — recombination emerges implicitly because the LLM sees multiple inspiration programs in its prompt context.

##### MAP-Elites and quality-diversity search

Vanilla genetic algorithms keep a single fitness-ranked population and tend to converge on one local optimum. OpenEvolve instead uses **MAP-Elites** (Multi-dimensional Archive of Phenotypic Elites), a quality-diversity algorithm that discretizes a *behavior* space into a grid of cells along user-chosen feature axes and retains only the best program per cell. The archive is therefore a portfolio of diverse high performers rather than a ranked list.

OpenEvolve's default feature dimensions are **complexity** (LOC inside the `EVOLVE-BLOCK`) and **diversity** (a structural similarity metric). Users can declare any metric returned by their evaluator as a feature dimension via `database.feature_dimensions` in the config, and control grid resolution with `feature_bins` (default 10 bins per axis). A new candidate replaces the incumbent of its cell if its fitness — `combined_score` when present, else an average of numeric non-feature metrics — is higher. OpenEvolve does the binning itself, so evaluators should return raw continuous values rather than pre-binned indices.

##### Island models and migration

OpenEvolve further partitions the population into **islands** (default 5) that evolve independently in parallel, each with its own MAP-Elites grid. Periodically — every `migration_interval` generations (not wall-clock seconds, not total iterations) — the top `migration_rate` fraction (default 10%) of each island's programs migrates to the next island in a **ring topology**. Islands guard against premature convergence by keeping different search threads isolated long enough to develop distinct solutions; migration then cross-pollinates those lineages. Worker processes are pinned deterministically: `island_id = worker_id % num_islands`.

##### Key vocabulary

**Inspirations** are programs surfaced into the LLM prompt to provide in-context examples; they are sampled from a mix of top performers, diverse feature-grid extremes, lineage ancestors, and random draws, and are deliberately distinct from the "top programs" shown in the prompt's metrics section. **Elites** are the current occupants of MAP-Elites cells. **Archive** typically refers to the cross-island collection of elites. **Artifacts** are side-channel output (stderr, profiler data, build warnings, LLM feedback) that evaluators may return alongside metrics; OpenEvolve injects these into subsequent prompts, creating a feedback loop that helps the LLM correct failures. **Cascade evaluation** runs cheap tests first (`evaluate_stage1`) and gates progression to expensive tests (`evaluate_stage2`, `evaluate_stage3`) by score thresholds.

---

#### 2. Practical usage

##### Installation

OpenEvolve requires **Python 3.10 or newer**. The standard install is `pip install openevolve`; runtime dependencies are `openai`, `pyyaml`, `numpy`, `tqdm`, and `flask` (the Flask dep powers the visualizer). To install from source for development, clone the repo and run `pip install -e ".[dev]"`. A Docker image is published at `ghcr.io/algorithmicsuperintelligence/openevolve:latest`.

All LLM calls go through the **OpenAI Python SDK**, so every provider is configured with the same two environment variables:

```bash
export OPENAI_API_KEY="sk-..."            # your provider's key
export OPENAI_API_BASE="https://..."      # optional; overrides config.yaml api_base
```

Gemini keys work with `api_base: "https://generativelanguage.googleapis.com/v1beta/openai/"`; Ollama uses `http://localhost:11434/v1` and a dummy key; OptiLLM can front any backend with test-time compute wrappers. An additional env var, `ENABLE_ARTIFACTS=false`, disables the artifact side-channel globally.

##### Project layout

A typical project is three files in one directory. OpenEvolve creates its outputs alongside them:

```
my_project/
├── initial_program.py       # seed program with EVOLVE-BLOCK markers
├── evaluator.py             # defines evaluate(program_path) -> dict
├── config.yaml              # LLM, database, evaluator, prompt settings
└── openevolve_output/       # auto-created on first run
    ├── best/
    │   ├── best_program.py
    │   └── best_program_info.json
    ├── checkpoints/
    │   ├── checkpoint_10/
    │   │   ├── best_program.py
    │   │   ├── best_program_info.json
    │   │   ├── programs/
    │   │   └── metadata.json
    │   └── checkpoint_20/ ...
    └── evolution_trace.jsonl
```

##### Writing an initial program

Mark the mutable region (if diff-based mutations) of the seed with comment sentinels. Everything outside the markers is **preserved verbatim** across generations — use that for imports, helpers, test harnesses, and `__main__` blocks.

```python
# initial_program.py
# EVOLVE-BLOCK-START
"""Function minimization example for OpenEvolve"""
import numpy as np

def search_algorithm(iterations=1000, bounds=(-5, 5)):
    """A random search that often gets stuck in local minima."""
    best_x = np.random.uniform(bounds[0], bounds[1])
    best_y = np.random.uniform(bounds[0], bounds[1])
    best_value = evaluate_function(best_x, best_y)
    for _ in range(iterations):
        x = np.random.uniform(bounds[0], bounds[1])
        y = np.random.uniform(bounds[0], bounds[1])
        value = evaluate_function(x, y)
        if value < best_value:
            best_value = value
            best_x, best_y = x, y
    return best_x, best_y, best_value
# EVOLVE-BLOCK-END


# Fixed context below — not evolved.
def evaluate_function(x, y):
    return np.sin(x) * np.cos(y) + np.sin(x * y) + (x**2 + y**2) / 20

def run_search():
    return search_algorithm()

if __name__ == "__main__":
    x, y, v = run_search()
    print(f"min at ({x}, {y}) with value {v}")
```

Multiple `EVOLVE-BLOCK` pairs are legal but the documented convention is exactly one per file. For non-Python artifacts use the target language's comment leader (e.g., `// EVOLVE-BLOCK-START` for Rust or Metal).

##### Writing an evaluator

The evaluator is an importable Python module with a top-level `evaluate(program_path: str) -> dict` function. `program_path` is the absolute path to the candidate file; the evaluator imports it, runs it, and returns a dict of `str -> float` metrics where higher is better. A key named `combined_score`, when present, is used for ranking; otherwise OpenEvolve averages the numeric metrics that are not being used as feature dimensions.

```python
# evaluator.py
import importlib.util, time

def _load(program_path):
    spec = importlib.util.spec_from_file_location("candidate", program_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def evaluate(program_path):
    try:
        t0 = time.time()
        mod = _load(program_path)
        x, y, value = mod.run_search()
        elapsed = time.time() - t0
        return {
            "runs_successfully": 1.0,
            "value_score": max(0.0, 1.0 - abs(value)),   # higher is better
            "speed_score":  1.0 / (elapsed + 0.01),
            "combined_score": max(0.0, 1.0 - abs(value)),
        }
    except Exception:
        # Never raise — return a zero-score instead.
        return {"runs_successfully": 0.0, "combined_score": 0.0}
```

Evaluators should **catch their own exceptions** rather than raising; unhandled exceptions and timeouts are captured by OpenEvolve as artifacts (stderr, traceback) and surfaced into the next generation's prompt. A per-run timeout is enforced via `evaluator.timeout` (default 60 s in examples; up to 1800 s for heavy benchmarks). Timed-out evaluations return an `error:0.0` score without retry; other failures retry up to `evaluator.max_retries` (default 3).

To return artifacts alongside metrics, import `EvaluationResult`:

```python
from openevolve.evaluation_result import EvaluationResult

def evaluate(program_path):
    ...
    return EvaluationResult(
        metrics={"performance": 0.85, "correctness": 1.0, "combined_score": 0.92},
        artifacts={"stderr": "warning: suboptimal memory access",
                   "profiling_data": {...},
                   "llm_feedback": "could use better variable names"},
    )
```

For cascade evaluation, define `evaluate_stage1`, `evaluate_stage2`, and optionally `evaluate_stage3` (still with a plain `evaluate()` as a fallback), then set `evaluator.cascade_evaluation: true` and `evaluator.cascade_thresholds: [0.5, 0.8]` in the config. A known gotcha (issue #137): `cascade_evaluation: true` with no `evaluate_stage1` defined silently falls back to single-stage `evaluate()` with no warning.

##### A minimal config.yaml

OpenEvolve's config has four nested sections — `llm`, `prompt`, `database`, `evaluator` — plus several top-level scalars. **Evolution-strategy flags (`diff_based_evolution`, `allow_full_rewrites`, `max_iterations`, `random_seed`, `checkpoint_interval`, `max_code_length`, `language`) live at the top level, not under a section**; this trips up newcomers.

```yaml
# config.yaml — minimal
max_iterations: 100            # overridden by CLI --iterations
checkpoint_interval: 10
random_seed: 42                # enables deterministic reruns
diff_based_evolution: true     # LLM emits SEARCH/REPLACE blocks
allow_full_rewrites: false
language: "python"             # Other options: "rust | "text" | etc

llm:
  api_base: "https://generativelanguage.googleapis.com/v1beta/openai/"
  models:
    - name: "gemini-2.5-flash"
      weight: 1.0
  temperature: 0.7
  max_tokens: 8000

prompt:
  system_message: |
    You are an expert programmer. Improve the function for correctness and speed.
  num_top_programs: 3          # top performers shown as in-context exemplars
  num_diverse_programs: 2      # diverse exemplars for exploration
  include_artifacts: true      # inject prior stderr/feedback into prompts

database:
  population_size: 100
  num_islands: 3
  migration_interval: 20       # generations, not iterations
  migration_rate: 0.1
  feature_dimensions: ["complexity", "diversity"]
  feature_bins: 10

evaluator:
  timeout: 60
  max_retries: 3
  parallel_evaluations: 4      # ProcessPoolExecutor worker count
  cascade_evaluation: false
  enable_artifacts: true
```

Important knobs worth flagging: **`llm.models`** is a list of `{name, weight}` pairs — weights are *sampling* probabilities, so one model is chosen per generation (not all queried in parallel). A separate `evaluator_models` list is used only when `evaluator.use_llm_feedback: true`; those models *are* all queried and their scores averaged by weight. **`database.feature_dimensions`** must reference either built-in features (`complexity`, `diversity`) or keys that your evaluator actually returns — otherwise OpenEvolve raises. **`prompt.template_dir`** points to a folder of override templates (see §4). The authoritative defaults live in `configs/default_config.yaml` in the repo; the values above are the ones that appear consistently across example configs.

##### Running an evolution

The CLI entry point is a script at the repo root:

```bash
python openevolve-run.py \
  examples/function_minimization/initial_program.py \
  examples/function_minimization/evaluator.py \
  --config examples/function_minimization/config.yaml \
  --iterations 50
```

Only three flags are documented: `--config <path>`, `--iterations N` (overrides `max_iterations`), and `--checkpoint <dir>` to resume. Iterations are parallelized across `evaluator.parallel_evaluations` worker processes. Checkpoints are written every `checkpoint_interval` iterations to `openevolve_output/checkpoints/checkpoint_<N>/` and contain the current best program, all evaluated candidates (in `programs/`), and the full database state (`metadata.json`). Resuming preserves islands, MAP-Elites feature maps, archives, and random seeds; iteration numbering continues, so resuming from checkpoint 50 writes checkpoint 60 next.

##### Inspecting results

After a run, the final best program lands at `openevolve_output/best/best_program.py` with a `best_program_info.json` sidecar containing metrics, program id, and the iteration at which it was found. Every checkpoint directory mirrors this structure, so you can `diff` across checkpoints to watch the algorithm evolve. A typical end-of-run log looks like:

```
Evolution complete! Best program metrics:
  runs_successfully: 1.0000
  value_score:       0.9766
  distance_score:    0.8626
  combined_score:    1.4206
  reliability_score: 1.0000
```

##### The web visualizer

OpenEvolve ships a Flask-based visualizer at `scripts/visualizer.py`. Install its separate requirements first (`pip install -r scripts/requirements.txt`), then run `python scripts/visualizer.py` (auto-picks the newest checkpoint under `examples/`) or `python scripts/visualizer.py --path openevolve_output/checkpoints/checkpoint_100/`. The UI renders the evolution tree as a network graph (node radius = fitness on the selected metric), lets you click any node to see its code and the exact prompt/LLM response that produced it, charts metric-versus-generation, and live-reloads as new checkpoints are written.

---

#### 3. Architecture and internals

##### Five components and one iteration

The codebase decomposes cleanly into five subsystems that correspond to the AlphaEvolve architecture: a **Controller** (`openevolve/controller.py`) that owns the evolution loop; a **Program Database** (`openevolve/database.py`) with MAP-Elites grids and islands; an **LLM Ensemble** (`openevolve/llm/ensemble.py`); a **Prompt Sampler** (under `openevolve/prompt/`) that builds context-rich prompts; and an **Evaluator** (`openevolve/evaluator.py`) that runs candidate programs with cascade support, timeouts, and artifact capture. A single iteration proceeds as follows:

1. The controller takes a snapshot of the database and submits a task to a `ProcessPoolExecutor` worker pinned to an island.
2. The worker asks the database to sample a parent from its island plus a set of inspirations.
3. The prompt sampler assembles a system message, the parent code, its metrics and feature coordinates, evolution history, inspiration programs, and artifacts from prior runs.
4. The LLM ensemble picks one model by weight and calls it via the OpenAI SDK.
5. The response is parsed — either as SEARCH/REPLACE diff blocks or as a full rewrite — and applied to produce the candidate file.
6. The evaluator runs the candidate with a timeout, optionally cascading through stages, and returns an `EvaluationResult`.
7. The worker ships a `SerializableResult` back to the main process, which reconstructs a `Program` and inserts it into the database, updating MAP-Elites cells and triggering migration if the per-island generation counter has reached `migration_interval`.

<img src="./assets/openevolve_architecture.png" width="500" height="400">

##### Program database

Each stored `Program` carries a UUID, parent id (for lineage), generation/iteration number, island id, the full source string, a metrics dict, feature-grid coordinates derived from raw metric values, and a pending-artifacts dict. Artifacts below ~10 KB are stored inline; larger ones spill to disk. Parent selection within an island uses an exploitation/exploration split (roughly 70/30 by default), biased toward high-fitness programs for parents. Inspirations are selected **separately and deliberately differently** — drawn from top performers, lineage ancestors, diverse MAP-Elites extremes, and random samples — so that the LLM's creative context doesn't collapse onto the same handful of programs it's being told are the best.

##### Prompt construction

Default prompt templates live in `openevolve/prompt/templates.py`. A custom set can be supplied by pointing `prompt.template_dir` at a folder containing files like `system_message.txt`, `diff_user.txt`, `full_rewrite.txt`, `evolution_history.txt`, `top_programs.txt`, and — for LLM-feedback evaluation — `evaluator_system_message.txt` and `evaluation.txt`. Placeholders include `{metrics}`, `{improvement_areas}`, `{artifacts}`, `{evolution_history}`, `{current_program}`, `{previous_attempts}`, `{top_programs}`, and `{program_number}`. Setting `prompt.use_template_stochasticity: true` with a `template_variations` dict lets OpenEvolve randomly swap in different phrasings each generation to diversify outputs. A rendered diff-mode prompt ends with an exact instruction block:

##### Diff mode vs full rewrite

**Diff mode is the default and preferred strategy.** The LLM emits one or more SEARCH/REPLACE blocks; the parser locates the exact SEARCH text inside the parent's `EVOLVE-BLOCK` region and substitutes. The diff delimiter pattern is itself configurable. **Full-rewrite mode** has the LLM emit a complete replacement program; it is less demanding for smaller models but lower-quality on longer files. `allow_full_rewrites: true` with `diff_based_evolution: true` lets OpenEvolve occasionally request full rewrites as an escape hatch.

##### Parallelism, async, and checkpointing

Parallelism is **process-based** via `concurrent.futures.ProcessPoolExecutor` in `ProcessParallelController`, deliberately bypassing the GIL for CPU-bound evaluators. Workers initialize once, lazily create their LLM clients and evaluators, and then loop on sample→prompt→LLM→evaluate. The database snapshot model means workers never contend on locks. Running in serial mode is catastrophically slow (~14× slower and ~50% lower solution quality per the authors' benchmarks) — **parallelism is effectively mandatory for acceptable results**, not optional. LLM calls inside workers are synchronous OpenAI SDK calls; `OpenEvolve.run()` itself is awaited in examples and appears to be an `asyncio` coroutine at the top level (uncertain from external docs alone, but consistent with `await` usage). Checkpoints are fully resumable: the database state (programs, islands, archives, feature maps), best program, and random seeds all persist, so continuation from `checkpoint_50` is byte-identical to an uninterrupted run through iteration 60.

##### LLM backends

OpenEvolve is **OpenAI-API-compatible only** — there is no native Anthropic or Gemini SDK integration. Anthropic and Gemini are used through their OpenAI-compatible endpoints; local models via Ollama, vLLM, LM Studio, or OptiLLM. The `LLMEnsemble` normalizes the weights in the `models:` list and samples exactly one model per generation using a seeded `random.Random`, making model selection deterministic given `random_seed`. A distinct `evaluator_models` list is used only when `use_llm_feedback: true`, in which case every listed model is queried and their scores are averaged weighted by each model's weight. The project also supports "model-based islands" where each island is pinned to a specific model instead of weighted sampling. Recent releases fix provider-specific quirks (e.g., PR #385 fixed Anthropic models erroring when both `temperature` and `top_p` are passed).

---

#### 4. Integration and customization

##### The Python API

Two API surfaces coexist, both exported from `openevolve.__init__`. The **class-based API** is the original:

```python
import asyncio, os
from openevolve import OpenEvolve

os.environ["OPENAI_API_KEY"] = "..."

evolve = OpenEvolve(
    initial_program_path="initial_program.py",
    evaluation_file="evaluator.py",
    config_path="config.yaml",
)
best_program = asyncio.run(evolve.run(iterations=1000))

for name, value in best_program.metrics.items():
    print(f"  {name}: {value:.4f}")
print(best_program.code)
```

The **functional API** (`openevolve/api.py`) added in the 0.2.x line removes the filesystem boilerplate:

```python
from openevolve import run_evolution, evolve_function

# Inline code + callable evaluator — no files needed.
result = run_evolution(
    initial_program="def fib(n): return n if n < 2 else fib(n-1) + fib(n-2)",
    evaluator=lambda path: {"score": benchmark_fib(path)},
    iterations=100,
)
print(result.best_code)

# Or wrap a Python function with test cases.
result = evolve_function(
    bubble_sort,
    test_cases=[([3,1,2], [1,2,3]), ([5,2,8], [2,5,8])],
    iterations=50,
)
```

Additional helpers `evolve_code` and `evolve_algorithm` exist with similar shapes. Exact kwargs lists for these helpers were not verified from source in this research — **confirm signatures against `openevolve/api.py` before relying on them in production**.

#### Customization hooks

OpenEvolve has no formal plugin registry; customization is expressed through **configuration, prompt templates, and the evaluator module**. The supported surfaces are:

- **Custom evaluators**: any Python module exposing `evaluate(program_path)`, optionally with `evaluate_stage1/2/3` for cascade.
- **Custom metrics**: just return them from the evaluator; reference them by key in `database.feature_dimensions` to use them as MAP-Elites axes.
- **Custom prompt templates**: drop override files in `prompt.template_dir` to replace the code-oriented defaults. Inline a custom `prompt.system_message` directly in YAML for simpler cases. Use `prompt.use_template_stochasticity` for wording variety.
- **LLM-judge feedback**: set `evaluator.use_llm_feedback: true`, list `evaluator_models`, and supply `evaluator_system_message.txt` / `evaluation.txt`. Results blend with algorithmic scores via `llm_feedback_weight`.
- **Artifact side-channel**: `evaluator.enable_artifacts` + `prompt.include_artifacts` wires stderr, tracebacks, and custom debug data back into prompts.
- **Inference-time compute**: route the generator LLM through OptiLLM to get MoA, `executecode`, `readurls`, or `z3_solver` plugins by simply setting the model name (e.g., `"moa&readurls-o3"`).

##### What can be evolved beyond code

The framework operates on text plus an evaluator — **it will evolve anything you can score**. Demonstrated non-code use cases include LLM system prompts (`examples/llm_prompt_optimization` [link](https://github.com/algorithmicsuperintelligence/openevolve/tree/main/examples/llm_prompt_optimization) reports +23% accuracy on HotpotQA), natural-language content (a Towards Data Science walkthrough evolves poetry using LLM-only evaluators), and configuration artifacts. Non-code use cases generally require custom prompt templates because the built-in templates assume the artifact is code, and usually pair best with `language: "text"` plus `diff_based_evolution: false`. OpenEvolve is explicit that it evolves **entire files**, not just single functions — a key differentiator from the earlier FunSearch system.

##### Integration patterns

The natural ways to embed OpenEvolve in a larger pipeline are:

- **CLI mode with checkpoint hand-off**: drive `openevolve-run.py` from a job scheduler, and treat the `openevolve_output/checkpoints/` directory (plus `best/best_program.py`) as the pipeline artifact. `evolution_trace.jsonl` is easy to ingest into downstream analysis.
- **Library mode (inline)**: use `run_evolution(...)` with an in-process callable evaluator, avoiding the filesystem entirely — ideal when OpenEvolve is one stage of a Python pipeline.
- **Library mode (files)**: use `OpenEvolve(initial_program_path, evaluation_file, config_path).run(...)` when the evaluator has to be a separate file (e.g., because it imports heavyweight dependencies you don't want in the host process).
- **Evaluator-as-gateway**: any external system integration (web API calls, containerized sandboxes, distributed benchmarks) goes in the `evaluate()` function. OpenEvolve does not itself know how to sandbox untrusted code — you must supply that isolation.
- **Docker image**: `ghcr.io/algorithmicsuperintelligence/openevolve:latest` for reproducible deployment; mount a workspace, pass CLI args.
- **MCP tool wrapper**: the AMD ROCm blog demonstrates exposing OpenEvolve as an MCP tool inside a Cline coding agent; this pattern works for any agent framework that can call a subprocess or Python function.

For reproducibility in a pipeline, rely on `random_seed` (default 42), which is propagated to the LLM ensemble, database, and evaluator.

##### Known limitations and gotchas

Cost is the dominant real-world constraint. The README's rough per-iteration estimates are **o3 ≈ $0.15–0.60, o3-mini ≈ $0.03–0.12, Gemini-2.5-Pro ≈ $0.08–0.30, Gemini-2.5-Flash ≈ $0.01–0.05**; with 1000 iterations across multiple islands, paid runs can quickly reach hundreds of dollars. Recommended mitigations are cascade evaluation to filter failing candidates early, smaller populations, cheaper models for early iterations, and Gemini free-tier or Ollama for development. Gemini's free tier has tightened since late 2025, producing 429s during long runs.

Specific known issues worth flagging:

- **Cascade silent fallback**: `cascade_evaluation: true` without `evaluate_stage1` falls through to `evaluate()` with no warning.
- **Default templates are code-oriented**: non-code evolutions require a full custom template set.
- **Top-level vs nested fields**: forgetting that `diff_based_evolution`, `allow_full_rewrites`, `max_iterations`, and `random_seed` are top-level is a frequent config error.
- **No built-in sandboxing**: the evaluator executes arbitrary LLM-generated code in-process. For untrusted domains, wrap evaluation in a container or subprocess yourself.
- **Active churn**: the codebase is explicitly a research project; expect breaking changes across minor releases. Pin a version in production.

---

#### 5. Glossary

| Term | Meaning |
|---|---|
| **AlphaEvolve** | Google DeepMind's Gemini-powered evolutionary coding agent (May 2025), which OpenEvolve reimplements. |
| **Archive** | The collection of elite programs across all MAP-Elites cells (and across islands). |
| **Artifacts** | Side-channel data (stderr, tracebacks, LLM feedback, profiler output) returned by the evaluator and injected into later prompts. |
| **Cascade evaluation** | Multi-stage evaluation (`evaluate_stage1/2/3`) gated by thresholds so expensive tests only run on promising candidates. |
| **Combined score** | Reserved metrics-dict key used preferentially for ranking; when absent, OpenEvolve averages numeric non-feature metrics. |
| **Controller** | The `OpenEvolve` / `ProcessParallelController` class that orchestrates the evolution loop. |
| **Diff mode** | LLM emits SEARCH/REPLACE blocks that patch specific fragments of the parent program. Default mode. |
| **EVOLVE-BLOCK markers** | `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` comment sentinels delimiting the mutable region of the initial program. |
| **Elite** | The best program occupying a given MAP-Elites cell. |
| **Ensemble** | Weighted list of LLMs under `llm.models`; one is sampled per generation by weight. |
| **Evaluator** | User-supplied Python module whose `evaluate(program_path)` returns a metrics dict (or `EvaluationResult`). |
| **Feature dimensions** | The axes of the MAP-Elites grid; configured in `database.feature_dimensions` and binned automatically by OpenEvolve. |
| **Full-rewrite mode** | LLM emits a complete replacement program instead of a diff. Better for weaker models or short files. |
| **Generation** | Per-island iteration counter used to trigger migration. |
| **Inspiration programs** | Programs from elsewhere in the database included in the prompt for context; deliberately chosen to differ from the "top programs" shown in metrics. |
| **Island** | An isolated sub-population with its own MAP-Elites grid; evolves in parallel with others and exchanges programs via ring migration. |
| **Iteration** | One sample→prompt→LLM→evaluate→insert cycle executed by a worker. |
| **LLM feedback** | Optional secondary LLM-as-judge step that scores code quality; merged into metrics via `llm_feedback_weight`. |
| **MAP-Elites** | Multi-dimensional Archive of Phenotypic Elites — quality-diversity algorithm that keeps the best program in each cell of a discretized feature space. |
| **Migration** | Periodic transfer of top programs from one island to the next in ring topology, triggered by generations (not wall-clock). |
| **OptiLLM** | Same author's inference-time-compute proxy; exposes test-time plugins (MoA, executecode, z3_solver) via model-name strings. |
| **Prompt Sampler** | Component that builds prompts using parent, inspirations, metrics, artifacts, and templates. |
| **Program Database** | Central store of all programs, metadata, island assignments, and MAP-Elites cells (`openevolve/database.py`). |
| **Quality-diversity search** | Family of algorithms (including MAP-Elites) that optimize for a portfolio of diverse high performers rather than a single optimum. |

---

#### 6. Further reading

The canonical sources to consult next are the **OpenEvolve GitHub repository** (`https://github.com/algorithmicsuperintelligence/openevolve`, formerly `codelion/openevolve`) — particularly its README, `CLAUDE.md` developer-orientation doc, `configs/default_config.yaml`, and the `examples/` directory (start with `function_minimization`, then `circle_packing` and `llm_prompt_optimization`). The **PyPI page** (`https://pypi.org/project/openevolve/`) tracks release metadata. The **release notes** and recent PRs are worth scanning for breaking changes before pinning a version.

For conceptual background, read **DeepMind's AlphaEvolve blog post** (14 May 2025, `https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/`), the accompanying **whitepaper PDF**, and the **arXiv version** at `https://arxiv.org/abs/2506.13131`. DeepMind's `google-deepmind/alphaevolve_results` repo documents the reported results. For community context, see the **author's Hugging Face launch blog** (`https://huggingface.co/blog/codelion/openevolve`, 20 May 2025), the **Show HN thread** (`https://news.ycombinator.com/item?id=44043625`), Michael Lones's critical commentary "The boring truth about AlphaEvolve", the **Towards Data Science walkthrough** "Beyond Code Generation: Continuously Evolve Text with LLMs" which demonstrates non-code usage, and the **DeepWiki indexed source tour** at `https://deepwiki.com/codelion/openevolve` which cross-references file and line numbers. Recent academic follow-ups that benchmark against OpenEvolve include **CodeEvolve** (arXiv 2510.14150), **GigaEvo** (arXiv 2511.17592), and **"Barbarians at the Gate: How AI is Upending Systems Research"** (arXiv 2510.06189).

---

#### Conclusion: what to take away

OpenEvolve is best understood as a small, legible scaffolding around one central idea — **use an LLM as a mutation operator, and let MAP-Elites plus islands maintain a diverse portfolio of candidate programs** — plus a growing list of practical ergonomics: artifacts, cascades, LLM-judge feedback, checkpoints, and a visualizer. For an integrator, the three files you write (initial program, evaluator, config) are the entire contract with the framework, and your evaluator is the only place you truly need to exercise engineering judgment: it defines fitness, gates cost, enforces safety, and bridges to the external world. The framework itself is still a moving target — expect config fields to drift, expect provider-specific bugs, expect to read the source when docs disagree — but the conceptual model is stable and matches AlphaEvolve's architecture closely enough that the DeepMind paper is a useful ongoing reference. Pin a version, write a good evaluator, start with cheap models and short runs, and treat `best/best_program.py` plus the checkpoint directory as your integration artifacts.
