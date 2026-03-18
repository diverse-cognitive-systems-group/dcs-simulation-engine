# Character Assignment & Filtering Inventory (Server + UI)

This document enumerates the current runtime surface area for PC/NPC assignment and filtering.
It is intended as the replacement checklist for the upcoming redesign.

## Server Inventory

- `dcs_simulation_engine/core/game_config.py`
  - `CharacterSettings`, `CharacterSelector`, `CharacterSelection`, and `GameConfig.character_selection`
  - `is_player_allowed(...)` access gate (consent-signature based)
  - `_select_characters(...)` legacy declarative filtering path (`descriptor`, `include_hids`, `exclude_hids`, `exclude_seen_for_game`)
  - `get_valid_characters(...)` active pool construction (currently global-bypass to all characters, then display formatting)
- `dcs_simulation_engine/api/routers/play.py`
  - `_build_setup_options(...)` setup construction flow
  - `GET /api/play/setup/{game_name}` setup entrypoint
  - `POST /api/play/game` session creation entrypoint (forwards `pc_choice` and `npc_choice`)
- `dcs_simulation_engine/core/session_manager.py`
  - `SessionManager.create(...)` choice validation against valid pools
  - random fallback assignment when no explicit `pc_choice`/`npc_choice` is provided
- `dcs_simulation_engine/dal/base.py` and `dcs_simulation_engine/dal/mongo/provider.py`
  - `get_characters(...)`
  - `list_characters(descriptor, exclude_hids)` backend filter capability
- `dcs_simulation_engine/api/routers/catalog.py`
  - `GET /api/characters/list` metadata feed used by UI description fallback
- `dcs_simulation_engine/api/models.py`
  - `CreateGameRequest.pc_choice` and `CreateGameRequest.npc_choice`
  - `CharacterChoice` and `GameSetupOptionsResponse.pcs/npcs/allowed/can_start/denial_reason`
- `dcs_simulation_engine/helpers/game_helpers.py`
  - `get_game_config(...)` controls which versioned YAML is loaded for selection behavior

## Game Config Sources (Server-Loaded)

- `games/infer-intent.yaml`
  - `character_settings.display_pc_choice_as`
  - `character_settings.display_npc_choice_as`
  - `character_selection` rules
- `games/foresight.yaml`
  - `character_selection` rules
- `games/goal-horizon.yaml`
  - `character_selection` rules
- `games/explore.yaml`
  - `character_settings.display_*`
  - `character_selection.pc.descriptor`

## UI Inventory

- `ui/src/routes/games/$gameName.tsx`
  - setup fetch from `/api/play/setup/{gameName}`
  - character metadata fetch from `/api/characters/list`
  - `parseCharacterLabel(...)` label parsing into display name + inline description
  - `withUsableDisplayNames(...)` display-name fallback for hidden/generic/duplicate labels
  - description resolution fallback from `/api/characters/list`
  - random default assignment (`defaultPc` / `defaultNpc`)
  - `resolvedPc` / `resolvedNpc` selection state and submission
  - create-session payload fields: `pc_choice` and `npc_choice`
  - blocked setup UI path for `allowed=false` or `can_start=false`
- `ui/src/api/http.ts`
  - authenticated request transport for setup and character metadata requests
- `ui/src/api/generated/model/createGameRequest.ts`
  - generated frontend type for `pc_choice` and `npc_choice`
- `ui/src/api/generated/index.ts`
  - generated endpoint bindings for `/api/play/setup/{gameName}` and `/api/characters/list`

## Scope Notes

- Scope here is runtime server + runtime UI.
- Test-only assumptions are intentionally excluded from this inventory.
- `_select_characters(...)` is listed because it remains defined even though current runtime path bypasses it.
