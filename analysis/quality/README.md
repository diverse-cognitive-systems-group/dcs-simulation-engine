# Quality Analysis

Contains simulation **coverage and behavioral quality analyses**.

## Coverage Quality
Coverage analysis include **dimensional coverage analyses** (e.g. species, origin, etc.) and **clustering analyses** to identify character groupings and gaps in coverage.

Run this when new characters are added/removed. They use the character seed data json files and don't require running DCS-SE.

## Behavioral Quality
Behavioral quality analyses examine **failure modes of role-playing models** (e.g. hallucinations, contradictions, etc.) and highlight specific features, patterns of the simulator. 

It includes a manual evaluation of IC, RF, and narrative coherence by DCS researchers. Followed by an external expert evaluation.

### Workflow

Rerun if codebase changes impact the simulation graph models or character sheets.

1) Execute run

This run config produces results for reproducibility + analysis. It specifies:
- require player expertise + consent
- assignment protocol: assign character based on player expertise (assign games for characters that fit expertise; randomized order; no repeats character+game+player combination)
- stop when each game has 5 unique players

```sh
# Run dcs-se with usability run config
dcs run --config qa-expert-eval.yaml --deploy

# Check status (# players, games, etc.)
dcs status

# Stop when ...
dcs stop
```

Outputs:
- results/ → full run data (ignored; may contain PII)

⸻

2) Move results to secure storage

If results contain sensitive data (PII, human consent forms, etc.), move them to secure storage.

Perform analysis from secure storage mount.

4) Analyze results

Run analysis notebooks from results


### Metric Definitions

Key insights from literature in this area include: make state explicit, retrieve only what matters, validate before committing. Together these eliminate a large fraction of hallucination, drift, and contradictions without changing the underlying model.

## In-Character (IC) Fidelity
*How well does it stay in character?*

- pct responses out of character (per turn or game)
- style drift score

## Rule-Following (RF) Fidelity
*How well does it obey explicit rules and constaints?*

- validator pass rate
- post validation regeneration rate
- hard constraint violation rate

## Narrative Coherence (world consistency)
*Does the story make sense over time?*

- canon contradiction rate
- invalid world state transition rate
- entity consistency

### Workflow

