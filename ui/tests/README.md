# UI Test Backlog

When frontend tests are added, include tests for:

- Players can draft text while a game is loading.
- Players cannot submit text with the Send button until the game has loaded and it is their turn.
- Players cannot submit text with Enter until the game has loaded and it is their turn.
- Players cannot submit slash commands before the game has loaded.
- Slash command autocomplete cannot use Enter before the game has loaded.
- Resumed sessions stay submit-disabled during replay and enable after replay completes.
- Input submission is disabled while waiting for the simulator response.
- Interrupted or errored games can't be resumed.
- Completed, interrupted, and errored run assignments display Done.
- Interrupted run assignments show their status without a Start, Continue, or Resume action.
- Errored or closed saved game session IDs are cleared instead of showing Resume Game.
- Refreshing a completed, interrupted, or errored play page restores the ended read-only transcript instead of restarting gameplay.
- Opening the same live play session in a second tab shows that the session is already open elsewhere.
- Resumed sessions show the correct message/events
- Refresh button doesn't change anything - just reloads current session/state
- Back button ...
- Fwd button ...
