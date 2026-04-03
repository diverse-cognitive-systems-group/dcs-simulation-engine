# Configuration

A run configuration specifies how the engine should be run including:

- what players (human and/or AI) are participating
- what forms they see and when (e.g. consent, pre-game, post-game, after all gameplay sessions, etc.)
- what gameplay scenarios they should encounter (games + characters)

---

## Example Configs

These examples are provided in `examples/run_configs` of the main repository and can be used as templates for your own configurations.

| Example File | Description | Use Case |
|---|---|---|
| [`benchmark-ai.yml`](benchmark-ai.yml) | Runs the engine with specified AI models (e.g. GPT-4o, Claude, your own custom models) so users can see how well they perform across various scenarios. | Used by AI researchers to examine how well their models engage with various simulated diverse cognitive systems. |
| [`benchmark-humans.yml`](benchmark-humans.yml) | Runs the engine so humans can play and users can see how they perform across various scenarios. | Used by psychology researchers to examine how well humans engage with various simulated diverse cognitive systems. |
| [`evaluate-batches.yml`](evaluate-batches.yml) | Runs the engine so that humans can evaluate batches of characters across scenarios based on player expertise. | Used by AI researchers and DCS maintainers to evaluate the quality of simulated characters by having experts evaluate them. |
| [`evaluate-specific.yml`](evaluate-specific.yml) | Runs the engine for humans to play with specific scenarios. | Used by AI researchers and DCS maintainers to conduct targeted evaluations of individual characters. |
| [`training.yml`](training.yml) | Runs the engine so that human players can learn how to engage with divergent humans. | Used in leadership training and other training contexts to expose neurotypical huamn players to individuals with diverse abilities, cognitive profiles, etc. (i.e. neurodivergence). |
| [`usability.yml`](usability.yml) | Runs the engine so human players can evaluate the usability of the system. | Used by DCS maintainers to evaluate the usability of the GUI. |

---

## What's configurable and what's not

***Run configurations include only the minimal parameters needed to support DCS use cases. The goal is not maximum configurability, but enabling the engine to run across different players (AI and human) and scenarios (games and characters), with data captured at defined points so users can evaluate performance, analyze behavior, and iterate on experiments.***

### Run Metadata
This captures the identity of the run and what its for.
- **`name`** — unique identifier used in API routes
- **`description`** — human-readable summary

### Who the **players** are
This controls whether GUI is launched in addition to the API. If only AI players are listed, no GUI is launched for the run.

- **`players`** — list of players allowed to participate in the run (e.g. `human`, `gpt-4o`, `claude-2`, etc.)

### What forms players see and when
Forms are used for showing surveys, questionnaires, consent forms, instructions at different events during the run. 

Events include:

- before_all_gameplay_sessions
- after_all_gameplay_sessions
- before_each_gameplay_session
- after_each_gameplay_session

### What games should be included
Games listed are the ones that the assignment strategy (below) will pull from when creating assignments. It includes the game and any game-specific configurations exposed in that game definition. Omitting games list will pull from all core games with default configurations.

### How players get to gameplay sessions (**assignment strategy**)

Assignment strategy controls what games + characters come up for players and how much control they have over what they play next.

You can write your own assignment strategy and point to it or use provided ones.
- random_unique: assign game + player combinations randomly while ensuring uniqueness until quota is met, then allow repeats as needed
- ...
