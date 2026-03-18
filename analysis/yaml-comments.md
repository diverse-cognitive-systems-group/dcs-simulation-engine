# YAML File Header Comments

Extracted top-level comments from all YAML files in the `analysis/` directory.

---

## `analysis/baseline-evaluations/performance-eval-learning-ai.yaml`

```
# ================================================================
#  Run Configuration — Baseline Performance Evaluation (Learning)
# ================================================================
#
# This configuration specifies:
#
#   • No participant consent required
#   • No expertise requirement
#   • No pre-play form or onboarding flow
#
#   • Assignment protocol:
#       - Single fixed character ID
#       - Player may select any valid game
#       - No character reassignment
#
#   • No automatic stop condition
#
# ================================================================
```

---

## `analysis/baseline-evaluations/performance-eval-learning-human.yaml`

```
# ================================================================
#  Run Configuration — Baseline Performance Evaluation (Learning Human)
# ================================================================
#
# This configuration specifies:
#
#   • Player consent and expertise is required
#
#   • Assignment protocol:
#       - Each player plays a game + character combination 3x
#.      - Display evaluation result + feedback form after each playthrough
#
#   • Stop run when all games + character combinations are done
#
# ================================================================
```

---

## `analysis/baseline-evaluations/performance-eval-static-ai.yaml`

```
# ================================================================
#  Run Configuration — Baseline Performance Evaluation (Static AI)
# ================================================================
#
# This configuration specifies:
#
#   • No participant consent required
#   • No expertise requirement
#   • No pre-play form or onboarding flow
#
#   • Assignment protocol:
#       - Each AI player model plays a all game + character combinations
#
#   • Stop when all assignments are completed
#
# ================================================================
```

---

## `analysis/baseline-evaluations/performance-eval-static-human.yaml`

```
# ================================================================
#  Run Configuration — Baseline Performance Evaluation (Static Human)
# ================================================================
#
# This configuration specifies:
#
#   • Player consent and expertise is required
#
#   • Assignment protocol:
#       - Each player plays a single game + character combination
#
#   • Stop when all games + character combinations are done
#
# ================================================================
```

---

## `analysis/character-development/eval-one-character.yaml`

```
# ================================================================
#  Run Configuration — One Character Evaluation
# ================================================================
#
# This configuration specifies:
#
#   • No participant consent required
#   • No expertise requirement
#   • No pre-play form or onboarding flow
#
#   • Assignment protocol:
#       - Single fixed character ID
#       - Player may select any valid game
#       - No character reassignment
#
#   • No automatic stop condition
#
# ================================================================
```

---

## `analysis/quality/behaviorial/expert-eval.yaml`

```
# ================================================================
#  Run Configuration — Expert Evaluation
# ================================================================
#
# This configuration specifies:
#
#   • Player consent and expertise is required
#
#   • Assignment protocol
#       - Assign characters based on player expertise
#       - No repeated character + game + player combinations
#       - Don't allow player selection (games + chars) assign randomly
#
#   • The run stops when each player + character + game combination >= 1
#
# ================================================================
```

---

## `analysis/usability/usability-component-a.yaml`

```
# ================================================================
#  Run Configuration — Usability Study Component A (GUI)
# ================================================================
#
# This configuration specifies:
#
#   • Player consent is required
#     (new player consent form must be completed)
#
#   • Games and characters are assigned using
#     random unique assignment custom fn
#     (no player-game repeats allowed)
#
#   • Each player may play a maximum of 1 game
#
#   • The study stops when each game has
#     5 unique players
#
# ================================================================
```

---

## Summary of Functional Requirements

Based on all YAML run configurations in the analysis directory, the simulation engine must support:

### Player & Consent Management
- Optional or required participant consent flows, configurable per run
- A `new_player_form` with support for: text, email, phone, textarea, and checkbox field types
- PII field flagging on form questions
- Optional expertise requirement gates before a player can participate
- Electronic consent signature capture

### Assignment Protocol
- **Fixed character assignment**: pin a single character ID to all players in a run
- **Exhaustive combination assignment**: enumerate and assign all game + character combinations across players
- **Expertise-based assignment**: match players to characters based on declared expertise
- **Custom assignment functions**: plug in arbitrary `AssignmentStrategy` implementations with parameters (e.g., `random_unique_assignment` with `per_game`, `one_game_per_player`, `seed`)
- Prevention of repeated player + game + character combinations within a run
- Optional player-driven game selection (vs. forced assignment)
- Configurable repeat count per assignment (e.g., play the same combination N times)

### AI Player Support
- Run configurations that substitute AI model players in place of humans
- Player entries identified by model ID (e.g., `openrouter:openai-gpt-4o`)
- AI players should support the same game + character assignment logic as human players

### Stop Conditions
- **No stop condition**: run continues indefinitely
- **All combinations completed**: stop when every game + character (+ player) combination has been played at least once
- **Per-game player quota**: stop when each game reaches N unique players
- **Threshold-based**: stop when each combination meets a minimum play count

### Post-Play Forms & Triggers
- Event-driven trigger system (e.g., fire a form on `lifecycle.COMPLETE`)
- Post-play quality/feedback forms with free-text questions
- Display evaluation results and feedback forms after each playthrough (for learning protocols)

### Run Metadata
- Named runs (`name` field) for identification and reporting
- Reproducible randomness via configurable seeds

### Character Management
- Characters identifiable by ID (e.g., `human-asd1`)
- Characters span multiple games/tasks within a single run
