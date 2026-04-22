# Discovering Strategies for Engaging with Diverse Cognitive Systems using OpenEvolve and DCS-SE

## Research Questions

**Central Question:** Does the diverse cognitive systems simulation engine (DCS-SE) possess the capacity of supporting the training of open-ended systems (e.g., large-language models) for the purpose of the development of engagement strategies which promote meaningful interaction with non-standard normative forms of bodies and intelligence?

**Additional Questions:**
1. TODO: 



## Experimental Design

**OpenEvolve Overview**
TODO: High-level introduction to OE

**OpenEvolve Integration**
TODO: How OE integrates with DCS-SE
Mention fitness function construction, what is being evolved / define engagement strategy...
TODO: Setups – Description of game + character configurations

**Purpose of OpenEvolve**
TODO: Why use OE with DCS-SE? Ensure to tie it back as a hypothesis to the "Central Question".


## Results
TODO: Example initial and final prompts with corresponding setups + final fitness scores

**Resource Costs**
TODO: Cost per simulation run, latency and factors of latency

**Observations**
TODO: What patterns can be extracted from the simulations at both the per step level and overall? Behaviors, convergence speed, paths taken, ideas generated, pitfalls, mistakes, blockers, etc.


## Takeaways

**Limitations**
TODO: Scenarios where OE performed poorly

**Advantages**
TODO: Scenarios where OE shined

**Considerations**
TODO: What would a researcher who wants to use the DCS-SE need to know by inferring the considerations from OE results?

**Expected Model Learnings from playing the DCS-SE**
TODO: 


## Supplementary Materials
TODO: OpenEvolve primer – Detailed primer on OpenEvolve – how it works, load-bearing mechanisms for evolution, why it was created, confiurations

LLM-driven mutation, program database, selection loop, config choices

Evolution Configuration: which LLM(s) drive mutation, prompt template structure, program database type (MAP-Elites / island / generational), population size, number of generations, stop conditions. Includes any non-default choices and why.

Cascading Evaluation: The staged evaluator design — cheap filters early, expensive full-rollout evaluation later. Specifies what each stage checks for (compilability, basic sanity, partial-horizon performance, full fitness) and the thresholds that gate promotion between stages.


TODO: Connection to AlphaEvolve academic paper
TODO: opensource repo link


----








# OLD

---

Research Questions  – simple language about the main question we wanted to answer with additional questions to follow up on in future experiments.

**Primary Research Question**
The central claim this experiment will support/refute

**Additional Research Questions**
Secondary questions that arise naturally from the primary but aren't load-bearing for the claim verdict: ablation-style questions (what does the LLM contribute vs. the evolutionary loop?), generalization questions (do strategies transfer across scenarios?), and diagnostic questions (what kinds of strategies emerge?).

---


# Experimental Design

Experimental Design – what + how + why of using OpenEvolve with DCS-SE (description and reasoning of high-level design choices such as LLM model, cascading evaluation, etc.)

**Problem Description**
Operational definition of the task: What is being simulation through OE and DCS-SE, what "representation" OpenEvolve evolves, What an "engagement strategy" is in this context.

**Fitness Function**
The signal that drives selection. Specifies what the simulation emits as an performance metric (across different scenarios), whether fitness is scalar or multi-objective, and what safeguards do/don't exist against obvious reward hacking.


---


Results – What was observed (final prompts/engagement strategy, resource costs, final fitness scores) + why the observations were not surprising / surprising

## Results

**Scenario 1: ...**
Setup: Game and character settings, simulation parameters, and any scenario-specific fitness adjustments.
Outcome: Best strategy found, convergence speed, fitness trajectory over generations, comparison against baseline, and a brief note on strategy character (what it actually does).

**Scenario 2: ...**
Setup:
Outcome:

**Scenario 3: ...**
Setup:
Outcome:

**Scenario 4: ...**
Setup:
Outcome:

---

## Discussion

**Observations and Findings**
Cross-scenario patterns: where OpenEvolve consistently outperformed, where it didn't, what kinds of strategies emerged, any reward hacking or degenerate solutions observed, and surprises worth flagging.

**Feasibility Assessment**
Explicitly answers the primary research question with a verdict — proceed, proceed with modifications, or abandon — and states the conditions or evidence that would flip the verdict.

**Next Steps**
Concrete follow-on work conditional on the verdict: scope expansions, ablations worth running, infrastructure improvements, or alternative methods to evaluate if the verdict is negative.
 