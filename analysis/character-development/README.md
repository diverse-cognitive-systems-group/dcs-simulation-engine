# Character Development

Contains individual character analysis including per character metrics like 'divergence'.

## Character Creation and Evaluation Workflow

### Step 1: Primary Research
Perform primary research (character interviews, reading primary sources, etc.) and character sheet creation

### Step 2: Add Character Sheet to Database 
Assign dimensions (species, origin, divergence, etc. according to the following definitions) and add the character to the seed data json files

### Step 3: Run DCS-SE and evaluate character quality metrics
Run DCS-SE with `eval-one-character.yaml` and report quality metrics: In-Character (IC) fidelit,  Rule-Following (RF) fidelity and narrative coherence.

```sh
# Run all games for one character locally
dcs run --config eval-one-character.yaml

# Play the games and report feeback in game (e.g. 'out of character', 'doesn't make sense', etc.)

# Stop when all games played for that character
dcs stop
```

**If IC, RF, NC are below the quality threshold, identify failure modes and update the character sheet json in seeddata file and rerun DCS-SE until the character sheet and metrics are above the quality threshold. (Note: track changes over time in a doc to identify which changes led to improvements in the metrics to inform future character development efforts).**
