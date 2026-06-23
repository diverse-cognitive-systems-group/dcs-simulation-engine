# Load Test Failure Modes

This page catalogues the failure modes that surface when running the DCS-SE load
test under concurrent load. It is a reliability reference: for each failure mode
it documents the trigger, a local reproduction, the engine code path responsible,
the symptom a client sees, the engine's current mitigation, and a recommendation.

The load test lives at [`scripts/load_test_and_report.py`](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/scripts/load_test_and_report.py).
Its standard profile is **10 clients × 10 games/client = 100 concurrent gameplay
sessions**, where each session runs an opening scene, 3 player turns, and a close.

## Running the load test locally

You do **not** need an `OPENROUTER_API_KEY` to exercise the harness. The server
accepts a `--fake-ai-response` flag that returns a fixed string for every AI call
instead of calling OpenRouter, which lets you run the full concurrency machinery
offline.

```sh
# 1. Start MongoDB only (devcontainer compose).
docker compose -f .devcontainer/dev.compose.yml up --detach

# 2. Start the engine in offline mock mode. The fake response is valid JSON that
#    matches the model output contract: {"type": "ai"|"info"|"warning", "content": <non-empty str>}.
dcs server \
  --mongo-seed-dir database_seeds/dev \
  --config examples/run_configs/load-test.yml \
  --dump ./runs \
  --fake-ai-response '{"type":"ai","content":"A calm beat passes as the scene settles."}'

# 3. In another terminal, run the standard 100-session profile.
uv run python scripts/load_test_and_report.py --clients 10 --games 10 --turns 3
```

When the engine is stopped (so it dumps to `runs/<timestamp>/`) the script
generates a `system-performance` HTML report at
`docs/reports/load_test_results_report.html`. See
[Analyze Results](user_guide/analyze_results.md) for the reporting flow.

!!! note "Use the load-test run config"
    The load-test client always registers a player, so it must run against a
    config with `ui.registration_required: true`. Use
    `examples/run_configs/load-test.yml`. Running against a config with
    `registration_required: false` (such as `demo.yml`) produces a blanket
    `409 Conflict` — see [Config coupling](#config-coupling) below.

## Failure mode summary

| Failure mode | Trigger | Client symptom | Engine mitigation |
|---|---|---|---|
| [Defective / empty provider response](#defective-or-empty-provider-response) | Provider returns non-JSON, contract-violating, or empty output | `Server error: Session is closed` | 1 automatic retry, then session teardown |
| [Rate limiting](#rate-limiting) | Provider returns HTTP 429 / quota errors under load | Provider error message, or session close | 1 retry for retryable provider errors |
| [Request stalling under concurrency](#request-stalling-under-concurrency) | Many concurrent sessions contend for engine/provider capacity | Slow turns; long tail latency | None (bounded only by client/provider timeouts) |
| [Config coupling](#config-coupling) | Load test run against a `registration_required: false` config | `409 Conflict`, 0 completions | N/A (operator error) |

## Defective or empty provider response

**Trigger.** The provider returns output that does not satisfy the engine's
contract — non-JSON text, an empty/whitespace `content`, or a `type` outside
`{ai, info, warning}`.

**Reproduce.** Start the server with a contract-violating fake response and run a
small load test:

```sh
dcs server ... --fake-ai-response 'I am not valid JSON at all.'
uv run python scripts/load_test_and_report.py --clients 3 --games 2 --turns 1
```

Observed result — every session fails:

```
Total games completed: 0
Total game failures:   6
Errors: client N game M: Server error: Session is closed   (×6)
```

**Code path.**

- [`ai_client.py`](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/dcs_simulation_engine/games/ai_client.py)
  validates the response in `_call_json_prompt`. A non-JSON body is coerced to
  `{"type": "error", ...}` by `_parse_json_response`, and an empty or wrong-typed
  `content` is rejected, raising `ModelOutputContractError`
  (see [`errors.py`](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/dcs_simulation_engine/errors.py)).
- The opener/updater retries the prompt **once** with corrective feedback. When
  the second attempt also fails, the error propagates and
  `core/game.py` fails the opening scene, which closes the session.

Server-side log for the reproduction above:

```
ai_client.py | Model output contract failed: component=opener ... attempt=1 will_retry=True  detail=response was not valid JSON
ai_client.py | Model output contract failed: component=opener ... attempt=2 will_retry=False detail=response was not valid JSON
game.py      | Opening scene failed due to model provider error: ... OpenRouter returned unusable output ...
```

**Mitigation.** One corrective-feedback retry on contract failure.

**Recommendation.** The client only ever sees the generic
`Server error: Session is closed`, which hides the underlying
`ModelOutputContractError`. Consider surfacing a failure category (e.g.
`provider_contract_error`) on the close/error frame so operators can distinguish
defective-output failures from other session closures.

## Rate limiting

**Trigger.** Under high concurrency the provider returns HTTP 429 (or other
quota/credit errors) instead of a completion.

**Reproduce.** Not reproducible in `--fake-ai-response` mode, since no real
provider calls are made. To observe it, run against a live `OPENROUTER_API_KEY`
with a high client count and a rate-limited key/model.

**Code path.**

- `_call_openrouter` raises a `ModelProviderError` carrying the provider
  `status_code` ([`errors.py`](https://github.com/diverse-cognitive-systems-group/dcs-simulation-engine/blob/main/dcs_simulation_engine/errors.py)).
- `_call_openrouter_with_retry` retries **once** when
  `_should_retry_llm_error` is true — i.e. for retryable `ModelProviderError`s
  and `httpx.HTTPError`s. A non-retryable error (or a second failure) propagates
  and fails the session.

**Mitigation.** A single retry for retryable provider/transport errors. There is
no backoff or jitter, so a burst of 429s under load can still exhaust the retry
immediately.

**Recommendation.** When measuring rate-limit behavior, record the count of
retryable vs non-retryable provider errors per run and the provider
`status_code` distribution. Exponential backoff with jitter on 429 would reduce
correlated retry storms.

## Request stalling under concurrency

**Trigger.** Many concurrent sessions contend for engine and provider capacity,
inflating per-turn response latency.

**Reproduce.** Run the standard 100-session profile in mock mode and read the
per-phase latency in the summary:

```sh
uv run python scripts/load_test_and_report.py --clients 10 --games 10 --turns 3
```

Observed result — all sessions complete, but latency fans out sharply even
though the mock model is effectively instant:

```
Total games completed: 100 / 100   (0 failures)
Wall time: ~7.2s
Per-game duration (ms):              min=29   mean=333   max=1083
Wait-for-response (turn phase, ms):  min=8    mean=164   max=922
```

A ~100× spread between the min and max turn-phase wait, with the provider removed
from the equation, indicates **engine-side contention/serialization** rather than
provider latency. With a real provider this contention stacks on top of network
and model latency.

**Code path.** The harness measures wait-for-response per phase in
`_play_single_game` and aggregates it in `_print_summary`. The contention itself
is in the engine's per-session request handling.

**Mitigation.** None specific; sessions are bounded only by client and provider
timeouts.

**Recommendation.** Use the load test's tail-latency numbers (max / mean
wait-for-response) as the reliability signal, not just the completion count — a
run can report 100/100 completed while still exhibiting a poor latency tail.

## Config coupling

**Trigger.** Running the load test against a run config with
`ui.registration_required: false`.

**Reproduce.** Start the server with `--config examples/run_configs/demo.yml`
and run any load test.

Observed result — every client fails at registration:

```
409 Conflict for POST /api/player/registration
detail: "Player registration is disabled for this run."
```

**Code path.** `api/routers/users.py` returns `409 Conflict` from the
registration endpoint when `run_config.registration_required` is false, but the
load-test client always calls `register_player`.

**Mitigation.** N/A — this is an operator/config mismatch, not an engine fault.

**Recommendation.** Always run the load test against
`examples/run_configs/load-test.yml` (or another `registration_required: true`,
`forms: null` config). This is easy to mistake for an engine bug.
