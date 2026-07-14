# API-Sports Coverage Audit Design

Date: 2026-07-14
Status: approved concept, written specification pending final user review

## Objective

Determine whether a lawful zero-cost external odds feed can improve TotoAI's
probability inputs without silently dropping BaltBet events. The first provider
is API-Sports because its free plan exposes football and hockey endpoints,
including pre-match odds, with separate daily quotas. TotoBrief bookmaker
probabilities remain the mandatory event-level fallback.

This phase measures data availability and matching quality. It does not change
`ev-package`, playable decisions, or the accepted EV mathematics.

## Constraints

- Monthly provider budget is zero for this phase.
- A paid plan up to 30 USD/month is considered only after a measured free-tier
  failure.
- Direct Pinnacle access and prohibited scraping remain out of scope.
- API keys come only from environment variables and never enter Git, SQLite,
  logs, reports, or exception messages.
- No draw, event, or package may disappear because external data is missing.
- Historical free-tier odds are not assumed. The experiment is prospective.

## Alternatives Considered

### 1. API-Sports with TotoBrief fallback - selected

API-Sports offers football and hockey APIs, pre-match odds, and a permanent
free tier. It is not assumed to have sufficient BaltBet coverage; the audit is
designed to establish that empirically.

### 2. The Odds API

The API has a simpler unified schema and historical snapshots on paid plans,
but its free league coverage may omit hockey and lower-tier competitions used
by BaltBet. It is the second adapter to test if API-Sports fails the gate.

### 3. Statistics-only probability model

Building probabilities from free results and team statistics would require a
separate modeling and calibration project. It is not an odds-provider fallback
and is deferred.

## Architecture

```text
TotoBrief open drawing snapshot
        |
        v
Provider-neutral target events (15)
        |
        +--> API-Sports football schedules/odds
        |
        +--> API-Sports hockey schedules/odds
        |
        v
Deterministic event matcher
        |
        v
Strict market-semantic validator
        |
        v
Per-bookmaker de-vig + robust consensus
        |
        v
Prospective snapshot store and coverage report
        |
        v
Future probability resolver
  external consensus OR explicit TotoBrief BK fallback
```

The provider contract returns provider events and bookmaker markets. It does
not expose API-Sports response shapes to the matcher, consensus calculator, or
EV engine. A later The Odds API adapter must implement the same contract.

## Provider Contract

Provider-neutral records contain:

- provider and provider event identifiers;
- sport, league, UTC start time, home team, and away team;
- market semantic identifier;
- bookmaker identifier and update timestamp;
- decimal prices for home, draw, and away;
- response fetch timestamp, payload hash, and quota metadata.

The API-Sports adapter uses `API_SPORTS_KEY` and the official football and
hockey hosts. It fetches schedules for only the dates and sports present in the
open drawing, caches those responses, performs event matching, then requests
odds only for candidate matches. Requests stop before exhausting a configurable
quota reserve. HTTP 429, quota exhaustion, malformed JSON, and provider errors
produce explicit audit failures and TotoBrief fallback, never partial silent
success.

## Event Matching

Matching is deterministic and fail-closed.

1. Convert timestamps to aware UTC values.
2. Normalize team names with Unicode NFKC, case folding, punctuation removal,
   and whitespace collapse.
3. Apply only versioned, reviewed aliases stored in project data.
4. Require the same sport, home/away orientation, both normalized team names,
   and a start-time difference no greater than three hours.
5. Use league names only to disambiguate, because provider league labels may
   differ.

Exactly one candidate becomes `matched`. Zero candidates become `missing`.
More than one candidate becomes `ambiguous`. Fuzzy similarity may be reported
as a diagnostic suggestion but can never authorize a match automatically.

Every TotoBrief event receives one match record, including missing and
ambiguous cases. Match decisions include algorithm version and reasons so a
future alias change cannot rewrite old evidence.

## Market Semantics and Probabilities

Only complete three-outcome decimal markets are eligible:

- football: full-time Match Winner (`1`, `X`, `2`);
- hockey: regulation-time Home/Draw/Away (`1`, `X`, `2`).

Two-outcome hockey moneyline markets that include overtime or shootouts are
rejected. Markets with missing draw prices, non-finite prices, prices not above
1.0, unknown settlement rules, or stale timestamps are stored for diagnostics
but are not used.

For each eligible bookmaker, remove the overround with multiplicative de-vig:

```text
raw_i = 1 / decimal_price_i
probability_i = raw_i / sum(raw_home, raw_draw, raw_away)
```

The initial consensus requires at least three eligible bookmakers. It takes
the component-wise median of their de-vigged probabilities and normalizes the
three medians to one. Coverage reports also show availability at one, two, and
three bookmakers so the threshold can be evaluated without changing it.

The default maximum odds age is 36 hours because the official API-Sports
hockey documentation states that hockey odds update once daily. Exact provider
timestamps and odds age are always retained and reported.

## Storage and Idempotency

Prospective records are append-only and store:

- immutable TotoBrief target-event identity and drawing deadline;
- provider event snapshot and canonical matching decision;
- normalized bookmaker odds and market rejection reasons;
- consensus probabilities when eligible;
- fetch time, provider update time, payload hash, and quota counters;
- fallback reason when no external consensus is usable.

Uniqueness keys make repeated collection idempotent. Raw payloads may be cached
locally by content hash, but secrets and authorization headers are excluded.
Collection never modifies historical TotoBrief inputs.

## Commands

```bash
python -m toto_ai.cli collect-external-odds \
  --open --provider api-sports --db data/toto.db

python -m toto_ai.cli audit-external-coverage \
  --db data/toto.db --last 30 --min-bookmakers 3
```

`collect-external-odds` resolves one fresh TotoBrief open drawing, records all
15 target events, uses cached provider schedules where possible, collects
candidate odds, and publishes an atomic collection summary.

`audit-external-coverage` reads only stored prospective snapshots and exports
deterministic CSV and Markdown reports. Reports include match, market, staleness,
bookmaker-count, quota, fallback, sport, league, and per-drawing metrics.

The existing `ev-package` command continues to use TotoBrief BK during this
phase. External consensus is not connected to playable selection until the
coverage gate passes and a separate ensemble design is approved.

## Coverage Experiment and Gate

Collect at least 30 future drawings and at least 450 TotoBrief events before a
GO/STOP decision. When a sport has at least 30 observed events, evaluate it
separately as well as overall.

GO requires all of the following:

- at least 80% of target events have one unique deterministic provider match;
- at least 70% have a fresh, complete three-way consensus from three or more
  eligible bookmakers;
- no ambiguous match is consumed as external probability input;
- all 15 target events in every drawing have a stored external or explicit
  TotoBrief fallback disposition;
- collection and reporting complete with zero secret leakage and zero silent
  event loss.

The report also records median and p90 missing/fallback counts per drawing,
coverage by sport and league, and request consumption per drawing. A failed
gate does not trigger payment. The next step is to implement The Odds API as a
second adapter and run the same gate. A paid API-Sports plan up to 30 USD/month
is evaluated only if the measured failure is caused by request quota rather
than absent leagues, events, markets, or bookmakers.

## Error Handling

- Missing key: controlled configuration error; no network request.
- Quota reserve reached: stop requests, persist explicit quota fallbacks.
- Network/provider failure: bounded retries for transient failures, then
  explicit provider-error fallback.
- Invalid response: reject the affected record and retain a sanitized reason.
- Ambiguous event: never pick one automatically.
- Partial market: never manufacture a draw probability.
- Database/report failure: transaction rollback and atomic report publication.

## Testing

Tests use recorded synthetic fixtures and injected HTTP transports; repository
tests never require a live key.

- provider contract and API-Sports football/hockey response parsing;
- authentication redaction, quota accounting, caching, and retry behavior;
- exact, missing, ambiguous, alias, time-window, and reversed-team matching;
- football and regulation-hockey market acceptance;
- overtime moneyline and incomplete market rejection;
- de-vig and median consensus against hand-calculated values;
- append-only idempotent storage and provenance;
- 15-event invariant with explicit fallback for every failure mode;
- deterministic atomic CSV/Markdown coverage reports;
- CLI errors and no regression to the accepted EV pipeline.

Before merge, run full pytest and Ruff. A live smoke test is optional and uses
an operator-provided key; its sanitized coverage evidence is stored in the
project memory bank, not as a test dependency.

## Non-Goals

- No claim that API-Sports probabilities are superior.
- No historical profitability claim.
- No automatic aliases learned from results.
- No external-data use in `PLAY` during the coverage phase.
- No subscription purchase or paid historical backfill.
- No scraping of bookmaker or score websites.

