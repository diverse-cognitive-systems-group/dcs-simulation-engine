# Baseline Performance Evaluations

Contains game play performance evaluations of baseline cognitive systems (human and AI agents static and learning).

## Baseline Evaluations

### AI Static Condition (no learning)
Run DCS-SE using foundational models as players. 

We aim to include assessments for latest models from major LLM families ((e.g. OpenAI - GPT, Anthropic - Claude, Google - Gemini, Meta - LLaMA) as well as models that report better relational intelligence? world modeling? role-playing? rule following? TBD

```sh
# Run all games for one character remotely
dcs run --config static-condition.yaml --deploy

# Check status
dcs status

# Stop when all games played for that character
dcs stop
```

### Human Static Condition (no learning)
Assign each participant one game + character combination and don't display evaluation results.

```sh
# Run all games for one character remotely
dcs run --config static-condition.yaml --deploy

# Check status
dcs status

# Stop when all games played for that character
dcs stop
```


### AI Learning Condition

### Human Learning Condition
Assign each participant one game and let them play X characters.

- display evaluation results after each game

