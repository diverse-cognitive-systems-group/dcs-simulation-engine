# UI Test Backlog

When frontend tests are added, include tests for:

- Players can draft text while a game is loading.
- Players cannot submit text with the Send button until the game has loaded and it is their turn.
- Players cannot submit text with Enter until the game has loaded and it is their turn.
- Players cannot submit slash commands before the game has loaded.
- Slash command autocomplete cannot use Enter before the game has loaded.
- Resumed sessions stay submit-disabled during replay and enable after replay completes.
- Input submission is disabled while waiting for the simulator response.
- Interruped or errored games cant be resumed
- Resumed sessions show the correct message/events
- Refresh button doesn't change anything - just reloads current session/state
- Back button ...
- Fwd button ...
