# UI Tests

## Running

```sh
cd ui
bun run test        # single run
bun run test:watch  # watch mode
```

Or from the repo root: `make test-ui`.

## Stack

- **Vitest** — test runner. Reuses the Vite config, so no separate transform setup.
- **jsdom** — DOM environment.
- **React Testing Library** — for component tests, asserting on visible/ARIA state rather than internals.
- `tests/helpers/mock-websocket.ts` — a controllable fake `WebSocket`, stubbed globally in
  `tests/setup.ts`. Tests inject server frames directly, so no API server is needed.

## Backlog

Status key: `[x]` covered · `[~]` partially covered (see note) · `[ ]` not yet written.

### Play page — input gating

- [ ] Players can draft text while a game is loading.
- [ ] Players cannot submit text with the Send button until the game has loaded and it is their turn.
- [ ] Players cannot submit text with Enter until the game has loaded and it is their turn.
- [ ] Players cannot submit slash commands before the game has loaded.
- [ ] Slash command autocomplete cannot use Enter before the game has loaded.
- [~] Resumed sessions stay submit-disabled during replay and enable after replay completes.
  — hook side covered (`isReplaying` flips on `replay_start` / `replay_end`); the component's
  disabled state is not asserted yet.
- [~] Input submission is disabled while waiting for the simulator response.
  — hook side covered (`waiting` set on `sendTurn`, cleared on `turn_end`); the component's
  disabled state is not asserted yet.

### Session lifecycle

- [~] Interrupted or errored games can't be resumed.
  — hook side covered (an `error` frame carrying `failure_type` closes the socket and sets
  `exited`); the route-level guard is not asserted yet.
- [~] Refreshing a completed, interrupted, or errored play page restores the ended read-only
  transcript instead of restarting gameplay.
  — hook side covered (`enabled: false` never opens a socket); the reconstruction render is not
  asserted yet.
- [~] Resumed sessions show the correct message/events.
  — replay events are appended to `messages`; ordering against a full transcript is not asserted yet.
- [ ] Refresh button doesn't change anything — just reloads current session/state.
- [ ] Opening the same live play session in a second tab shows that the session is already open
  elsewhere.

### Run assignments

- [ ] Completed, interrupted, and errored run assignments display Done.
- [ ] Interrupted run assignments show their status without a Start, Continue, or Resume action.
- [ ] Errored or closed saved game session IDs are cleared instead of showing Resume Game.

### Auth modes

- [ ] Directly opening a play URL in anonymous mode creates anonymous auth before connecting the
  WebSocket.
- [ ] Directly opening a play URL in registration-required mode gates on sign-in instead of
  creating anonymous auth.

### Deferred

- Back button — behavior unspecified in this backlog.
- Fwd button — behavior unspecified in this backlog.

## Covered by `use-session-websocket.test.ts`

These are the hook-level state-machine behaviors the play page derives its gating from:

- [x] `wsState` transitions `connecting → auth → ready` across the handshake, and `session_meta`
  populates `pcHid` / `npcHid`.
- [x] `sendTurn` emits an `advance` frame and sets `waiting`; `turn_end` clears it and updates `turns`.
- [x] `replay_start` sets `isReplaying`, `replay_end` clears it and applies the replayed turn count.
- [x] `turn_end` carrying `exited: true` sets `exited` and `exitReason`.
- [x] An `error` frame with `failure_type` closes the socket, sets `exited`, and surfaces the detail
  message.
- [x] An `error` frame without `failure_type` moves to `error` state without marking the session exited.
- [x] `enabled: false` never opens a socket and reports `closed`.
