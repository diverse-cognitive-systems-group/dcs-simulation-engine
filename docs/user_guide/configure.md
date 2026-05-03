# Configure an engine run

⚠️ Note: This page is incomplete and/or missing information.

A run configuration specifies how the engine should be run including:

- what players (human and/or AI) are participating
- what forms they see and when (e.g. consent, pre-game, post-game, after all gameplay sessions, etc.)
- what gameplay scenarios they should encounter (games + characters)

---

## Example Configs

These examples are provided in `examples/run_configs` of the main repository and can be used as templates for your own configurations.

| Example File | Description | Use Case |
|---|---|---|
| `benchmark-ai.yml` | Runs the engine with specified AI models (e.g. GPT-4o, Claude, your own custom models) so users can see how well they perform across various scenarios. | Used by AI researchers to examine how well their models engage with various simulated diverse cognitive systems. |
| `benchmark-humans.yml` | Runs the engine so humans can play and users can see how they perform across various scenarios. | Used by psychology researchers to examine how well humans engage with various simulated diverse cognitive systems. |
| `evaluate-batches.yml` | Runs the engine so that humans can evaluate batches of characters across scenarios based on player expertise. | Used by AI researchers and DCS maintainers to evaluate the quality of simulated characters by having experts evaluate them. |
| `evaluate-specific.yml` | Runs the engine for humans to play with specific scenarios. | Used by AI researchers and DCS maintainers to conduct targeted evaluations of individual characters. |
| `training.yml` | Runs the engine so that human players can learn how to engage with divergent humans. | Used in leadership training and other training contexts to expose neurotypical huamn players to individuals with diverse abilities, cognitive profiles, etc. (i.e. neurodivergence). |
| `usability.yml` | Runs the engine so human players can evaluate the usability of the system. | Used by DCS maintainers to evaluate the usability of the GUI. |

---

## Configurations

***Run configurations include only the minimal parameters needed to support DCS use cases. The goal is not maximum configurability, but enabling the engine to run across different players (AI and human) and scenarios (games and characters), with data captured at defined points so users can evaluate performance, analyze behavior, and iterate on experiments.***

## Specify metadata
This captures the identity of the run and what its for.
- **`name`** — unique identifier used in API routes
- **`description`** — human-readable summary

## Define who the **players** are
This controls whether GUI is launched in addition to the API. If only AI players are listed, no GUI is launched for the run.

- **`players`** — list of players allowed to participate in the run (e.g. `human`, `gpt-4o`, `claude-2`, etc.)

### Define what forms players see and when
Forms are used for showing surveys, questionnaires, consent forms, and instructions at different events during the run. They are configured in the run config rather than being hard-coded into registration.

Events include:

- before_all_assignments
- before_assignment
- after_assignment
- after_all_assignments

### Define what games should be included
Games listed are the ones that the assignment strategy (below) will pull from when creating assignments. It includes the game and any game-specific configurations exposed in that game definition. Omitting games list will pull from all core games with default configurations.

### Define how players get to gameplay sessions (**assignment strategy**)

Assignment strategy controls which game + player-character + simulator-character triplets come up for players and how much control they have over what they play next.

You can write your own assignment strategy and point to it or use provided ones.
- random_unique_game: assign allowed game triplets in deterministic random order while ensuring each player receives each configured game at most once
- ...
