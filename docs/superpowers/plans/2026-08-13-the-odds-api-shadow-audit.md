# The Odds API Shadow Audit Implementation Plan

## Boundary

Implement the approved The Odds API audit from
`docs/superpowers/specs/2026-08-13-sports-analytics-probability-design.md`.
The provider is read-only, shadow-only, and always `NOT_ACTIVATED`. It cannot
change BK probabilities, package selection, scheduler eligibility, `PLAY`, or
operator exports.

Only `THE_ODDS_API_KEY` from the protected environment is used. The secret is
never logged, cached, hashed into request fingerprints, reported, committed,
or included in exceptions. No external LLM or agent is used.

## Task 1 — Provider contract and fail-closed parsing

**Files:**

- add `src/toto_ai/external_odds/the_odds_api.py`;
- add `tests/test_the_odds_api_provider.py`.

Write failing tests first for:

- missing key before transport;
- `/sports` catalog parsing into football/hockey keys only;
- `/events` schedule parsing with exact event ID, participants, orientation,
  kickoff, league title, endpoint identity, request fingerprint, and payload
  hash;
- football `h2h` with exactly home/draw/away;
- hockey EU `h2h` accepted only when a draw outcome exists;
- hockey two-way moneyline, missing/duplicate/unknown outcomes, reversed price
  labels, invalid decimal prices, malformed timestamps, and malformed JSON
  fail closed;
- `onexbet`, `pinnacle`, and all other EU bookmakers remain separately
  identifiable.

Use existing `ProviderEvent`, `ProviderMarket`, matching, and consensus types.
Add provenance fields only where the current domain cannot represent the
approved source endpoint and request fingerprint.

## Task 2 — Quota-safe transport and immutable raw captures

Implement a sanitized client for `https://api.the-odds-api.com/v4`:

1. `/sports` and `/sports/{sport_key}/events` are discovery calls and use the
   documented zero-credit endpoints.
2. Fetch paid odds once per matched sport key, not once per event, using
   `regions=eu`, `markets=h2h`, `oddsFormat=decimal`, and the target time
   window. Reuse that response for every matched event in the league.
3. Track `x-requests-remaining`, `x-requests-used`, and `x-requests-last`.
   Stop before an optional paid call when remaining credits are at or below
   the configured reserve.
4. Retry only bounded transient transport/status failures. Provider failure,
   timeout, malformed data, and quota reserve become typed missing evidence;
   they never block the BK control path.
5. Store append-only raw response envelopes under
   `data/external-cache/the-odds-api/`. Envelopes contain only sanitized
   endpoint/parameters, retrieval time, quota metadata, response hash, and raw
   public payload. The API key is excluded from paths and bytes.
6. Cache the free sports catalog for one hour and event discovery for ten
   minutes. Paid odds are reused only in-memory inside one snapshot so a later
   checkpoint cannot silently consume an older market observation.

Tests cover cache use, duplicate raw capture idempotency, quota reserve,
429/5xx retry, no-events zero-cost handling, and secret absence from files,
fingerprints, exception text, and fake transport diagnostics.

## Task 3 — Provider-neutral collection provenance

Extend the existing external-odds collection without changing API-Sports
semantics:

- bind matcher version `the-odds-api-v1` for this provider while preserving
  `api-sports-v4` as the default;
- persist generic quota limit/remaining/used/last-cost separately from the
  legacy API-Sports daily/minute fields;
- persist schedule and market endpoint identity plus request fingerprint;
- preserve exact target orientation and swap 1/2 only for a validated reversed
  match;
- retain all 15 event dispositions, with explicit TotoBrief-BK fallback for
  missing/ambiguous/invalid rows;
- filter storage/audit by provider so API-Sports and The Odds API observations
  cannot be mixed.

Add migration tests for an existing SQLite database and byte-stability tests
for the unchanged API-Sports path.

## Task 4 — Current-drawing shadow command and reports

Add:

```bash
python -m toto_ai.cli collect-the-odds-api-shadow \
  --open \
  --db data/toto.db \
  --quota-reserve 50
```

The command resolves the exact open target, makes one shadow snapshot, saves
the immutable collection, and writes JSON/CSV/Markdown under
`reports/the-odds-api-shadow/<drawing-number>/`.

Each event report shows target identity, match disposition, orientation,
freshness, BK probabilities, de-vigged 1xBet probabilities, de-vigged Pinnacle
probabilities, broader eligible-bookmaker consensus, bookmaker/update counts,
and explicit fallback reasons. The report also shows request count, credit
cost, remaining quota, source hashes, and `NOT_ACTIVATED`.

The CLI must be usable independently of the production scheduler. A missing
key or provider outage returns a sanitized nonzero result and cannot mutate a
production plan or package.

## Task 5 — Prospective checkpoints and evaluation readiness

After the current live probe succeeds, add an uninstalled candidate command
that writes at most morning, control, and T-10 observations. It skips an
optional checkpoint rather than crossing the quota reserve and is idempotent
for the same drawing/checkpoint/input hash.

The audit remains pending until at least 30 completed drawings and 450 events.
Post-draw evaluation compares coverage/freshness/quota and then log loss,
Brier, calibration, and unchanged-package shadow replay against frozen BK.
No source is activated by this plan.

## Verification

Run focused tests after every task, then:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m ruff check .
PYTHONPATH=src .venv/bin/python -m toto_ai.cli \
  collect-the-odds-api-shadow --help
git diff --check
git status --short
```

The first live call is allowed only after all fake-transport tests pass and the
environment check confirms the key exists without displaying its value. The
live output must be inspected for secret leakage before any commit containing
generated reports is considered; generated live data remains untracked unless
the project policy explicitly permits that artifact class.
