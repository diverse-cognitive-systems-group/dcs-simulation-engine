# Usability Analysis

Contains
- thematic user analysis
- system performance analyses (latency, failures, etc.)

## Purpose
Reduce usability related confounds prior to downstream experimental usage.

## Workflow

*NOTE: this workflow is for DCS Usability Study: Component A (GUI). For component B (CLI + API), the workflow is specified in the Study document.*

Rerun if codebase changes impact the interfaces or system process/performance.

1) Execute run

This run config produces results for reproducibility + analysis. It specifies:
- require participant/player consent
- an assignment protocol: assign games + characters using random unique assignment (no player-game repeats)
- allow each player to play 1 game max
- stop when each game has 5 unique players

```sh
# Run dcs-se with usability run config
dcs run --run-name usability-ca --game-name "infer intent" --deploy

# Check status (# players, games, etc.)
dcs status

# Stop when each game has 5 unique players
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
