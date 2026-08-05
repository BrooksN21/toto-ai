# Fresh Prospective Collection Design

## Context

The first live API-Sports collection exposed two operational constraints:

- the existing cache has no freshness expiry, so repeating the CLI can reuse
  old schedule and odds payloads instead of observing the market again;
- the free API-Sports plan allows ten requests per minute, while drawing 4945
  required fifteen requests for schedules and matched-event odds.

A fresh test on drawing 4945 took 3.06 seconds for the first ten requests and
produced 8/15 consensuses. Repeating with the same isolated cache after 65
seconds took 2.79 seconds, made five new requests, reused ten cached responses,
and produced the expected 13/15 consensuses. The complete process took about
71 seconds.

## Goal

Make one CLI invocation collect a fresh, deadline-adjacent prospective sample
without silently reusing an older run or losing already fetched responses when
the minute quota requires another pass.

The operator protocol is to start the command about 15 minutes before the
drawing deadline. The command does not place bets and external probabilities
remain audit-only until the existing prospective gate passes.

## CLI

Extend `collect-external-odds` with:

```text
--fresh / --reuse-cache        default: --fresh
--max-passes INTEGER           default: 3
--retry-delay-seconds FLOAT    default: 65
--cache-root PATH              default: data/external-cache/api-sports
```

`--fresh` creates a unique cache-session directory below `cache-root`. All
passes in that invocation share that directory. A later fresh invocation gets
a different directory and therefore cannot consume an old prospective sample.

`--reuse-cache` preserves the current shared-cache behavior for diagnostics and
reproducibility. It is never the default for prospective collection.

The final CLI summary adds pass count, total requests, total cache hits, elapsed
time, and the retry stop reason. Existing final-snapshot metrics remain.

## Orchestration

Add a provider-neutral prospective collection orchestrator with injectable
provider factory, clock, and sleeper for deterministic tests.

One invocation:

1. Resolves and fetches the open TotoBrief drawing once.
2. Pins that exact drawing and target payload for every pass. A deadline change
   cannot make a retry collect the next drawing.
3. Creates a new provider client for each pass, using the same cache-session
   directory. This resets transient in-memory minute-quota state while retaining
   successful schedule and market responses.
4. Builds and append-only stores every complete 15-disposition snapshot.
5. Retries only while at least one event has a retryable operational fallback:
   `quota reserve reached`, `provider schedule failure`, or
   `provider odds failure`.
6. Sleeps for the configured delay before another pass.
7. Stops immediately when no retryable fallback remains or after `max-passes`.

Missing and ambiguous event matches, unknown sports, stale markets, semantic
market rejection, and insufficient bookmakers are not retry triggers. They
remain explicit TotoBrief BK fallbacks.

The last stored pass is the command result. Earlier passes remain immutable
provenance and the coverage audit continues to select the latest complete
snapshot per drawing.

## Failure Behavior

- API keys are never written to cache, SQLite, reports, or errors.
- A failed pass does not delete previous snapshots or cache responses.
- Retry exhaustion returns the final explicit-fallback snapshot and reports the
  stop reason; it does not manufacture external probabilities.
- Invalid CLI limits fail before provider access.
- `KeyboardInterrupt` stops immediately and never reports a partial operation
  as successful.
- Daily quota reserve remains unchanged. The orchestrator does not lower it to
  force completion.

## Tests

Tests must prove:

- fresh invocations use distinct cache sessions;
- all passes within one invocation share a cache session;
- one target drawing is pinned across retries;
- a ten-request first pass plus cached retry completes with only the missing
  requests;
- retryable and non-retryable fallback classification is exact;
- retry stops early when the snapshot has no retryable fallback;
- max-pass exhaustion is explicit;
- pass/request/cache/time summary values are correct;
- append-only storage retains intermediate and final snapshots;
- existing audit, matching, consensus, fallback, and `PLAY` behavior is
  unchanged.

## Non-Goals

This change does not:

- schedule the command automatically at T-15;
- choose a betting package;
- change probability, category, bank, consensus, or coverage-gate definitions;
- treat the 13/15 result from one drawing as proof that API-Sports passed the
  prospective gate.
