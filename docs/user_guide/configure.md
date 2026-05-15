# Configure an engine run

A run configuration specifies how the engine should be run including:

- what players (human and/or AI) are participating
- what forms they see and when (e.g. consent, pre-game, post-game, after all gameplay sessions, etc.)
- what gameplay scenarios they should encounter (games + characters)

---

## Detailed Configuration Option Reference

> Note: Simpler example configurations are provided in `examples/run_configs` and can be used directly or adapted as templates for your own runs.

```yml
# Human-readable run name. Used as the run identity in stored run metadata.
name: Example Run

# Optional longer description shown in run/admin contexts.
description: |
  A short explanation of what this run is for.

# Optional deterministic seed used by assignment strategies that need stable ordering and LLMs that support seeding.
seed: 42

# User-interface behavior for human players.
ui:
  # true: players must register/authenticate before play.
  # false: anonymous/free-play style access.
  registration_required: true

# Games included in this run. If empty, no assignments can be created by the
# built-in assignment strategies, so real configs should list at least one.
games:
  - name: Explore # Must match a registered game name.
    overrides:
      # Common overrides supported by every game.
      max_turns: 50 # 1-500; hard turn limit for a session.
      max_playtime: 1800 # 1-3600 seconds; wall-clock session limit.
      player_retry_budget: 10 # 0-10; invalid player actions allowed before exit.
      simulator_recovery_budget: 3 # 1-10; simulator recovery attempts.
      max_input_length: 350 # 1-350 characters per player input.

      # Character filter names used to restrict allowed PCs/NPCs.
      # PCs allow: pc-eligible, human-normative, divergent, hypersensitive,
      # hyposensitive, neurotypical, neurodivergent, physical-divergence.
      pcs_allowed: pc-eligible
      # NPCs may use any registered character filter, including all, divergent,
      # neurodivergent, neurotypical, hypersensitive, and hyposensitive.
      npcs_allowed: all

      # Game-specific overrides supported by Infer Intent, Foresight,
      # Goal Horizon, and Teamwork. Explore has no additional overrides.
      show_npc_details: false # Show hidden NPC details in the UI/setup flow.
      show_final_score: true # Show the final scoring/evaluation output.

# Assignment policy for choosing the next game + PC + NPC triplet.
next_game_strategy:
  strategy:
    # Built-in strategy ids:
    # - full_character_access
    # - unplayed_combination_choice
    # - expertise_matched_character_choice
    # - next_incomplete_combination
    # - least_played_combination_next
    # - progressive_divergence_assignment
    # - max_contrast_pairing
    # - expertise_matched_character_next
    # - expertise_matched_character_batch
    # - random_unique_game
    id: full_character_access

    # Optional shared strategy settings.
    quota_per_game: null # Positive integer quota per configured game, or null for open-ended.
    max_assignments_per_player: 3 # Positive integer cap; defaults to 3 when omitted.
    seed: 42 # Optional strategy-specific seed; falls back to top-level seed/name.
    pc_eligible_only: false # Restrict PC choices to characters marked PC-eligible.
    allow_choice_if_multiple: true # Let the UI expose multiple eligible choices when available.
    require_completion: false # true: finish active assignment before receiving another.

# Forms shown at lifecycle trigger points. Use null or [] when no forms are needed.
forms:
  - name: intake # Normalized to lowercase snake_case; must be unique.
    trigger:
      # Supported events:
      # - before_all_assignments
      # - before_assignment
      # - after_assignment
      # - after_all_assignments
      event: before_all_assignments
      match: null # Must be null for current built-in triggers.
    questions:
      - key: experience_level # Optional; auto-generated from prompt if omitted.
        prompt: How familiar are you with DCS-SE?
        # Supported answer types:
        # string, bool, single_choice, multi_choice, number, email, phone.
        answer_type: single_choice
        options: # Required for single_choice and multi_choice; invalid otherwise.
          - New to it
          - Some experience
          - Experienced
        required: true

      - key: extra_context
        prompt: Anything else you want the researchers to know?
        answer_type: string
        required: false
```