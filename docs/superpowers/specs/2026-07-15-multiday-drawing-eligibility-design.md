# Multi-Day Drawing Collection and Play Eligibility Design

## Status

Approved in conversation on 2026-07-15. This specification is intentionally
separate from the completed fresh prospective collection feature.

## Problem

TotoBrief may return `start_at = null` for every event. The current external
collector then requests only the betting-deadline date and the following date.
Rare holiday or off-season drawings may contain events spread across four or
five days. Those later events would be misclassified as missing provider
coverage.

The historical TotoBrief collector is unaffected: it already stores complete
drawings independently of event dates. The gap concerns prospective external
odds collection and the safety of a future playable package.

## Decisions

- The normal missing-start schedule horizon remains two calendar days.
- When exact events with missing target start times remain unresolved, the
  prospective collector may progressively expand the horizon to five calendar
  days inclusive of the betting-deadline date.
- Drawing-span classification uses `Europe/Moscow`, the operational timezone of
  the BaltBet drawing. Provider schedule requests use every UTC date needed to
  cover the selected Moscow-calendar horizon, preventing midnight boundary
  gaps.
- A drawing is playable only when effective start times are known for all 15
  events and their inclusive Moscow-calendar span is at most two days:
  `(max_date - min_date).days + 1 <= 2`.
- A confirmed known-start span above two days is `multi_day`, even when another
  event remains unresolved. Otherwise, any unresolved effective start time is
  `unknown`.
- `multi_day` and `unknown` are mandatory `NO BET` in playable mode. Research
  output and prospective storage remain available.
- External probabilities remain audit-only. Provider schedule metadata may
  only make the playable decision more conservative; it may never promote a
  package to `PLAY`.
- The five-day horizon is for collection and classification, not a claim that
  all providers or free plans expose every requested date.

## Alternatives Rejected

### Always Request Five Days

This is simpler but spends six additional schedule requests for a normal
two-sport drawing, increases minute-limit waits, and risks provider date-access
errors on every ordinary collection.

### Keep Two Days and Skip Missing Events

This preserves quota but confounds provider coverage with an artificially short
search horizon and loses useful prospective research data.

## Architecture

### 1. Progressive Schedule Horizon

The first stable collection uses the existing two-day missing-start horizon.
If any event with `start_at = null` remains unmatched because no exact provider
pair was found, a separate expansion phase requests only the additional dates
through day five. The same invocation cache is reused, so the original dates
and markets are not downloaded again.

The two/five-day limits apply only to searching for missing target starts.
Events with an explicit TotoBrief start retain the current exact-date request
behavior; an explicit start beyond day five is immediately useful evidence for
`multi_day` eligibility.

Operational retries and horizon expansion are separate concepts:

- quota, schedule transport, and odds transport failures use the existing
  65-second retry protocol;
- a clean two-day miss triggers horizon expansion without pretending it is a
  transport failure;
- expansion receives its own bounded pass allowance so the existing
  `--max-passes` meaning is not silently changed;
- every attempt remains an immutable 15-disposition snapshot.

The command must report the active horizon, whether expansion occurred, and
the stop reason. It must retain enough time for an operator to start at T-15;
no unbounded retry loop is allowed.

### 2. Per-Date Failure Isolation

Schedule retrieval is evaluated per sport and date. A provider or plan failure
for one additional date must not discard events successfully loaded for other
dates.

The collection records:

- every requested schedule date by sport;
- successful dates;
- failed dates with sanitized reasons;
- the configured missing-start horizon.

For an event with a known target start, only failure of its required date may
cause a schedule-failure fallback. For an event with a missing target start,
an unmatched result is:

- a partial-schedule fallback when at least one requested date failed;
- a normal missing-provider fallback only when every requested date succeeded.

Partial schedule failures remain operationally retryable. Normal missing
provider fallbacks trigger expansion only while the horizon is below five
days.

### 3. Effective Event Start

Each event receives an effective start time and source:

1. TotoBrief `start_at`, when present;
2. the uniquely matched provider event start, when TotoBrief is missing it;
3. unresolved otherwise.

Provider event start time is persisted separately from TotoBrief start time;
the original target field is never overwritten. Match orientation does not
affect time.

### 4. Drawing Eligibility

A provider-neutral classifier returns one immutable result:

- `multi_day`: the span of already known effective starts is above 2;
- `unknown`: known-start span <= 2 and at least one start is unresolved;
- `playable`: all 15 effective starts are known and inclusive span <= 2.

The result includes earliest/latest effective starts, inclusive span, missing
event orders, and source counts. It is persisted and exported with collection
provenance.

### 5. Playable Boundary

The EV research path remains unchanged. Before playable output is published,
the open drawing must have a latest complete prospective collection whose
canonical target fingerprint matches the current drawing and whose eligibility
is `playable`. The fingerprint binds drawing ID, number, deadline, and ordered
event identity, but excludes the observation fetch timestamp.

If the collection is absent, stale for a different target snapshot, marked
`multi_day`, or marked `unknown`, playable output is suppressed to an empty
zero-cost `NO BET` with an explicit reason. Timing metadata can therefore veto
`PLAY`, but external probabilities remain unable to create or improve a
playable package.

## Persistence and Compatibility

Append-only collection identity must bind schedule horizon, requested and
failed dates, provider start times, and eligibility. SQLite schema changes need
an explicit migration/backfill strategy:

- legacy snapshots remain readable;
- legacy eligibility is `unknown`, never inferred as playable;
- repeated canonical snapshots remain idempotent;
- conflicting content under one identity remains rejected.

Coverage reports separate ordinary provider misses from partial schedule/date
failures and expose eligibility counts. Multi-day and unknown drawings remain
in research reports but are not mixed into ordinary two-day provider-coverage
rates without a separate scope.

## CLI

`collect-external-odds` retains fresh mode and adds explicit expansion controls,
with conservative defaults:

- base missing-start horizon: 2 days;
- expanded horizon: 5 days;
- expansion enabled by default;
- bounded expansion passes;
- summary rows for horizon, expansion, date failures, and eligibility.

An explicit diagnostic option may disable expansion, but such a collection
cannot be classified `playable` when missing target starts remain unresolved.

`ev-package --mode playable` fails closed to `NO BET` unless current stored
eligibility is `playable`. Research mode continues and reports the same
eligibility warning.

## Testing

Required tests include:

- ordinary two-day drawing completes without expansion;
- missing-start event on day five is found after expansion;
- one inaccessible date preserves successful dates and records a partial
  failure;
- quota exhaustion during expansion resumes from the invocation cache;
- known starts across more than two Moscow calendar days are `multi_day`;
- a provider start fills a missing TotoBrief start without overwriting it;
- any unresolved event makes eligibility `unknown`;
- two dates separated by a gap of more than one day are `multi_day`;
- playable mode returns zero-cost `NO BET` for `multi_day`, `unknown`, absent,
  or mismatched eligibility;
- research mode remains available;
- external probabilities still cannot affect playable coupon ranking;
- legacy stored collections load as `unknown`;
- API keys remain absent from persistence, reports, caches, and exceptions.

## Acceptance

- Normal drawings do not spend requests on days three through five.
- A clean missing-start miss expands through day five within bounded passes.
- Partial provider date access does not erase successful schedule data.
- No drawing spanning more than two Moscow calendar days can produce `PLAY`.
- No drawing with unresolved event times can produce `PLAY`.
- Historical TotoBrief collection and existing research backtests are
  unchanged.
