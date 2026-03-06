# Engine Requirements

Derived from legacy game configs and run configuration analysis. Organized by layer.

---

## Layer 1: Game Config

What a single game definition needs to express. This is what the new simplified YAML format must support.

### NPC / AI Agent
- System prompt (inline text or file reference)
- LLM client and model selection (e.g., `open_router`, `gpt-4o`)
- Per-game behavior injection: additional rules that shape NPC responses ("goal-aligned", "collaborative", etc.)
- Per-game validation rules: additional rules that shape what user input is considered valid

### Sequence / Turn Structure
- Configurable turn order (who goes first, loop structure)
- Multiple named sequences with transitions between them

### Stopping Conditions (per-session)
- Max turns
- Max runtime (seconds)

### Lifecycle States
The engine must support at minimum: `ENTER`, `UPDATE`, `COMPLETE`, `EXIT`
- `ENTER`: first turn — show welcome message, then begin interaction
- `UPDATE`: normal turn loop
- `COMPLETE`: player triggered end (e.g., `/guess`) — show completion form or message
- `EXIT`: session ended abnormally or by `/exit` — show exit message

### Slash Commands
- `/help` — display help text (configurable per game)
- `/exit` / `/quit` — trigger EXIT lifecycle
- Game-specific commands (e.g., `/guess` → COMPLETE, `/abilities`, `/predict`)
- Commands return an info message and/or trigger a lifecycle transition

### Welcome / Exit / Completion Messages
- Configurable templated messages shown at lifecycle transitions
- Templates support interpolation of game/character context (e.g., `{{ pc.short_description }}`)

### Post-Game Completion Form
- Triggered on `COMPLETE` lifecycle
- Free-text questions (e.g., "What was the NPC's goal?")
- Collected responses saved with the session

### NPC Character
- NPC referenced by character ID (pulled from character registry)
- Character selection rules (e.g., exclude characters already played by this player in this game)

### PC Character
- PC referenced by character ID or selected from a filtered set
- Display format for character selection UI

---

## Layer 2: Run Config

A run is a study or evaluation that orchestrates one or more games across a set of players. The engine currently has no run-level concept.

### Run Metadata
- Name
- Optional random seed for reproducibility


### Assignment Protocol
The engine must support pluggable assignment strategies:
- **Fixed**: pin a single character ID to all players
- **Exhaustive combinations**: assign all game + character combinations across players
- **Expertise-based**: match players to characters based on declared expertise
- **Custom function**: arbitrary `AssignmentStrategy` with parameters (e.g., `random_unique_assignment` with `per_game`, `one_game_per_player`, `seed`)
- Prevention of repeated player + game + character combinations within a run
- Optional player-driven game/character selection vs. forced assignment
- Configurable repeat count per assignment (play same combination N times)

### AI Player Support
- Run configs can substitute AI model players in place of humans
- AI players identified by model ID (e.g., `openrouter:openai/gpt-4o`)
- AI players use the same assignment logic as human players

### Run Stop Conditions
- No stop condition (run continues indefinitely)
- All combinations completed (every game + character + player combination played ≥ N times)
- Per-game player quota (stop when each game reaches N unique players)
- Threshold-based (stop when each combination meets a minimum play count)

### Post-Play Triggers
- Event-driven: fire a form or action on lifecycle events (e.g., `on: lifecycle.COMPLETE`)
- Display evaluation results and feedback forms after each playthrough

---

## Layer 3: Engine Capabilities

What the engine itself must implement to support the above configs.

### Currently Implemented
- Turn-based game loop with AI integration (WebSocket)
- User registration and authentication (bcrypt + API keys)
- Session creation and in-memory management with TTL
- Message logging to database
- Multiple UI frontends (CLI, TUI, Gradio)
- Character model in DB (hid, abilities, descriptions, traits)

### Must Build

| Capability | Required By |
|---|---|
| Enforce stopping conditions (turns, time) | Game config |
| Lifecycle state machine (ENTER/UPDATE/COMPLETE/EXIT) | Game config |
| Slash command parsing and dispatch | Game config |
| Configurable welcome/exit/completion messages | Game config |
| In-game completion form (post-COMPLETE survey) | Game config |
| Per-game system prompt injection (NPC behavior/validator rules) | Game config |
| Character registry with query/filter support | Game config + Run config |
| YAML game config loader (replace hardcoded Python game classes) | Game config |
| Run-level orchestration layer | Run config |
| Assignment strategy engine (fixed, exhaustive, expertise, custom) | Run config |
| AI player support (model as participant) | Run config |
| Run stop conditions (quota, combination completion) | Run config |
| Consent and onboarding form flow (pre-play) | Run config |
| Post-play trigger system (event → form or action) | Run config |
