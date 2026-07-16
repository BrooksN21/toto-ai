# Current State

This file is the project-local state note for TotoAI only. Do not mix it with
local skills, personal knowledge bases, team knowledge bases, or unrelated
memory stores.

## Current Important Commits

- `f771bbe` Initial TotoBrief API client and CLI
- `bdcf776` Add historical data collector
- `d368704` Add historical research analytics
- `c962613` Add API inspector
- `4112362` Improve inspect-api with drawing number support
- `8ceda4b` Fix playable drawing selection
- `68cabb9` Add Cover Engine
- `0f92ee5` Add exact Cover Package verifier
- `7e95f24` Add baseline brief generator
- `8b3ed6d` Add persistent project memory bank

Note: the current PR branch was rebased onto an empty remote base for the first
GitHub pull request, so local branch commit hashes may differ from the original
task commits listed above.

## Verification

- Tests currently passed: 746
- Focused multi-day eligibility acceptance suite passed: 179
- Ruff passed

## Latest Completed Feature: Fresh Prospective Collection

`collect-external-odds` now defaults to a unique per-invocation cache session
instead of silently reusing unexpired historical payloads. It pins one open
TotoBrief target, creates a new API-Sports client for each pass, reuses only the
successful responses from that invocation, and retries quota, schedule, or odds
provider failures up to three passes with a 65-second default delay.

The legacy shared cache remains available only through explicit
`--reuse-cache`. The CLI reports pass count, aggregate HTTP attempts/cache hits,
elapsed time, and stop reason. Every pass remains an immutable complete
15-disposition snapshot, and external probabilities remain audit-only.

The first live dry run of the new command on drawing 4945 finished in two
passes and 68.66 seconds. The final T-15 run resolved the target once at
17:45:01 MSK and finished its second pass at 17:46:09 MSK, 13 minutes 50
seconds before the 18:00 deadline. It completed in 69.04 seconds with 15 HTTP
attempts and ten cache hits across the invocation; the final pass produced
13/15 consensuses, two explicit missing-provider fallbacks, two reversed exact
matches, and zero ambiguous matches. The prospective gate remains `PENDING`
only because the sample is below 30 drawings and 450 events.

## Completed Task: Provider-Neutral Drawing Eligibility Classifier

Task 1 of the multi-day drawing eligibility plan is complete. The new
provider-neutral classifier validates immutable effective starts for all 15
ordered events, applies the inclusive `Europe/Moscow` calendar span, returns
fail-closed `playable`, `multi_day`, or `unknown` results with source counts,
and creates deterministic target fingerprints that exclude fetch time.
Constructor invariants cover status, span, missing orders, source counts, and
earliest/latest consistency. Focused verification passed with 20 eligibility
tests and Ruff. Progressive schedule expansion, persistence, audit/report
changes, and the playable timing gate remain future work under the approved
multi-day design below.

## Approved Next Design: Multi-Day Drawing Eligibility

Rare holiday and off-season drawings can span four or five days. The approved
follow-up preserves the normal two-day API request cost, progressively expands
missing-start searches through day five only when needed, isolates failures by
sport/date, and persists provider-derived effective start times. Playable mode
will require all 15 effective starts within an inclusive two-day Moscow
calendar span; `multi_day` and `unknown` are mandatory `NO BET`. Historical
TotoBrief collection and research output remain unchanged, and external
probabilities remain audit-only.

Design specification:
- `docs/superpowers/specs/2026-07-15-multiday-drawing-eligibility-design.md`

## Completed Task: Per-Date Schedule Collection and Provenance

Task 2 of the multi-day drawing eligibility plan now requests schedules one
sport/date at a time in deterministic order, covers the selected Moscow
calendar horizon with all required UTC dates, and isolates sanitized failures
by date. A schedule quota cutoff marks the current and remaining date outcomes
and prevents every subsequent market request, including for events matched by
earlier successful schedule responses.

Fresh immutable snapshots carry target fingerprints, horizon and per-date
schedule provenance, provider/effective start times, and Task 1 eligibility.
Those fields participate in equality, `asdict`, and full canonical identity.
Pre-Task-3 SQLite persistence keeps its explicit legacy projection because the
current schema has no columns for the new data; Task 3 must persist and reload
the full provenance before it can be considered a storage round trip.

Verification: Task 2 collection/storage/end-to-end/matching/consensus tests
passed (`61 passed`), full pytest passed (`696 passed`), and repository Ruff
passed. The external coverage CSV/Markdown frozen hashes were regenerated only
after two separate byte-deterministic integrity runs.

## Latest Completed Feature: Explicit Reversed Event Orientation

Matcher v3 accepts a reversed home/away provider pair only when it is the sole
exact same-or-reversed candidate under the existing sport, alias, schedule-date,
and known-time rules. It records `same` or `reversed` orientation, fails closed
when both orientations or duplicate candidates exist, and never promotes fuzzy
similarity suggestions.

For a reversed match, collection swaps only the consensus `1` and `2`
probabilities into TotoBrief orientation. Raw provider home/draw/away prices
remain unchanged. Orientation is bound into immutable collection identity,
persisted in SQLite with a legacy-row backfill, and exported in coverage CSV
and CLI diagnostics.

The live re-collection of drawing 4945 produced 13/15 external consensuses
(86.67%), two reversed exact matches, two explicit missing-provider fallbacks,
and zero ambiguous matches. The gate is `PENDING` solely because the prospective
sample is below 30 drawings and 450 events. External consensus still has no
`PLAY` impact.

## Latest Completed Fix: API-Sports Mixed-Market Parsing

Fixed the remaining final-review blocker where exact `Home`/`Draw`/`Away`
validation was incorrectly applied to every API-Sports bookmaker market. A
payload containing valid full-time football or regulation-time hockey `1/X/2`
alongside totals, double chance, or two-way moneyline no longer aborts the
event. Exact outcome validation now runs only after the market name matches the
existing semantic allow-list, without adding any eligible market names.

Unrelated markets remain provider-neutral records and consensus assessments.
They are ineligible, contribute no probabilities, and remain available to the
existing quote diagnostics/persistence path. Allow-listed candidates still
fail closed on duplicate, unknown, or missing `Home`/`Draw`/`Away` labels.
No EV/PLAY, category, bank, probability, consensus, or gate definition changed.

Verification completed with the mixed-market RED/GREEN regression, focused
external-odds pytest (`117 passed`), full pytest (`643 passed`), Ruff (`All
checks passed!`), and zero-exit CLI help smokes for `collect-external-odds`,
`audit-external-coverage`, and `ev-package`.

## Latest Completed Task: API-Sports Coverage Audit Final Review Fixes

Fixed all final whole-branch review findings for the API-Sports coverage audit.
Consensus now uses an explicit external observation clock that is at least as
late as all consumed provider market fetch timestamps, while the original
TotoBrief drawing-info fetch time remains stored as `target_fetched_at`.
Fresh markets fetched after the TotoBrief target snapshot remain eligible;
genuinely future and stale market updates still fail closed.

API-Sports parsing now supports official-shaped odds items whose `update` is
on the response item rather than each bookmaker, while preserving valid
bookmaker-level overrides. Football and hockey schedules/odds are fetched
deterministically across every reported page with explicit `page` queries;
invalid or inconsistent `paging.current`/`paging.total` fails closed. Market
outcome labels are validated before `ProviderMarket` construction: each market
must contain exactly one `Home`, `Draw`, and `Away`, with no duplicate or
unknown extra outcomes.

Request accounting now distinguishes actual HTTP attempts from cache hits and
logical fetch calls. Retries and additional pages increment actual requests;
cache hits are persisted and reported separately. Collection reports, CSV, and
Markdown expose actual request attempts, cache hits, quota counters, target
fetch provenance, provider schedule provenance, and market fetch/update/hash
provenance. EV/PLAY behavior, gate thresholds, exact 15-event fallback
behavior, consensus thresholds, and probability definitions are unchanged.

Verification completed with focused external-odds pytest (`115 passed`), full
pytest (`641 passed`), Ruff (`All checks passed!`), required CLI help smokes
for `collect-external-odds`, `audit-external-coverage`, and `ev-package`
(all exited zero), and `git diff --check` (zero).

## Latest Completed Task: API-Sports Coverage Audit End-to-End Acceptance

Task 7 of the API-Sports coverage audit is implemented. Added an end-to-end
acceptance suite that runs the open collection pipeline through target parsing,
provider matching, consensus/fallback disposition, append-only SQLite storage,
latest-complete loading, read-only coverage audit, deterministic report
publication, and CLI sanitization boundaries.

Acceptance covers mixed success/fallback collections, provider schedule
failure, quota exhaustion after five successful market events, interruption
rollback with no complete run published, deterministic report hashes and
ordered 15-event evidence, provider timestamps, quota counters, consensus gate
settings, and EV non-interference. The same suite proves the API key is absent
from stored SQLite text, API-Sports cache files, CLI output, exception chains,
coverage CSV, and coverage Markdown.

Review hardening now raises sanitized API-Sports transport and
`collect-external-odds` CLI exceptions outside the secret-bearing handler
context. Recursive acceptance walks both `__cause__` and `__context__` and
proves the key is absent from `str()` and `repr()` of every reachable exception.

Coverage CSV dispositions now export stored provider schedule fetch/hash and
aligned market fetch/update/hash provenance, requests made, daily limit and
remaining quota, and minute remaining quota. CSV and Markdown also disclose
the fixed three-bookmaker/36-hour collection consensus configuration and all
six ordered gate predicates with actual values, operators, thresholds, and
observed pass results. Exact acceptance hashes bind both report artifacts.
Collection, matching, consensus, gate, report, and EV probability
definitions are unchanged.

The implementation is complete, but the operational external-odds gate remains
`PENDING` until an operator prospectively collects at least 30 future drawings
and 450 events. External consensus still has no `PLAY` impact.

Verification completed with focused acceptance pytest (`6 passed`), full pytest
(`628 passed`), Ruff (`All checks passed!`), and the required CLI help smokes
for `collect-external-odds`, `audit-external-coverage`, and `ev-package`
(all exited zero).

## Previous Completed Task: Append-Only External Odds Storage and Collection

Task 5 of the API-Sports coverage audit is complete. Added append-only
SQLAlchemy tables for external collection runs, event dispositions, and
bookmaker quote provenance. `save_collection()` writes one complete immutable
15-event snapshot in a single transaction, is idempotent for identical canonical
content, and rejects conflicting content under the same deterministic
collection ID.

Added deterministic external odds orchestration that fetches required
sport/date schedules before any odds request, matches all 15 TotoBrief targets,
fetches odds once per unique matched provider event, builds strict consensus
where possible, and otherwise preserves the TotoBrief BK triplet with an
explicit event-level fallback reason. Unknown sports, missing/ambiguous matches,
provider failures, quota exhaustion, stale/partial market paths, and
minimum-bookmaker failures do not drop events. Run rows persist provider quota
and request counts; event and quote rows persist matching, probability source,
fallback, market eligibility, and rejection provenance.

`collect_open_external_odds()` now resolves the nearest open TotoBrief drawing,
fetches exactly that drawing-info snapshot, parses the 15-event target, builds
and saves the external collection only after all dispositions exist, and returns
the immutable snapshot. This remains audit-only and does not change playable EV
package decisions.

Verification completed with focused external-odds storage/collection tests
(`11 passed`), full pytest (`591 passed`), and Ruff (`All checks passed!`).

## Task 5 Review Hardening: Provenance and Canonical Quotes

Matched event dispositions now persist the provider schedule event payload hash
and fetch time together with candidate IDs and the match reason. Bookmaker quote
rows persist provider market payload hash and fetch time. The deterministic
collection ID explicitly binds those fields, the fresh TotoBrief target
timestamp, matching decisions, and consensus configuration; changing either
schedule-event or market provenance changes the immutable identity.

Quote records are sorted canonically before collection construction and
identity, append-only stored-content comparison, insertion, and load. Identical
provider content therefore remains equal and idempotent regardless of response
or assessment order.

Consensus continues to reject duplicate bookmaker/market assessments. Multiple
assessments with the exact database quote key are now coalesced into one
ineligible row with the explicit `duplicate bookmaker market` reason, source
count, deterministic aggregate hash, and canonical source provenance retaining
every source hash, fetch/update time, and price triplet. The mandated unique key
is unchanged, and the anomaly no longer aborts the one-transaction 15-event
snapshot.

Review-fix verification: focused external storage/collection tests (`14
passed`), full pytest (`594 passed`), and repository-wide Ruff (`All checks
passed!`).

## Previous Completed Task: Strict Market Semantics and Consensus

Added `toto_ai.external_odds.consensus` for Task 4 of the API-Sports coverage
audit. The new module accepts only explicit full-time football `1/X/2` market
names and explicit regulation-time hockey `1/X/2` market names from small
allow-lists. It rejects unknown market names, missing outcomes, prices `<= 1`,
future timestamps, stale prices older than 36 hours, and duplicate bookmaker
records for the same accepted market semantics.

Eligible bookmaker prices are de-vigged multiplicatively per book, then the
component-wise median probabilities are renormalized into one provider-neutral
consensus triplet. Consensus requires at least three eligible bookmakers;
otherwise the result is an explicit fallback with per-book rejection reasons.
This prospective consensus remains an audit-only input and does not change
playable package decisions.

Task 4 verification completed with focused consensus tests, full pytest
(`578 passed`), and Ruff (`All checks passed!`).

## Task 4 Review Coverage

Added a deliberately asymmetric overround regression that proves each
bookmaker is de-vigged before component-wise medians are calculated. A
raw-inverse-median mutation produces a detectably different consensus and is
rejected by the test. Added positive coverage for an allow-listed hockey
regulation-time three-way market producing a three-bookmaker consensus. No
production behavior or probability definition changed.

Review verification completed with focused consensus tests (`10 passed`), full
pytest (`580 passed`), and Ruff (`All checks passed!`).

## Latest Completed Task: Deterministic External Event Matching

Added `toto_ai.external_odds.matching` for Task 3 of the API-Sports coverage
audit. Exact matching is fail-closed and accepts only a single candidate with
the same sport, the same home/away orientation, both team names matched after
Unicode normalization and reviewed alias resolution, and a UTC start-time
difference no greater than three hours. Target-side exact names may come from
the primary TotoBrief team names or the optional `name_en` alternatives.

Added `data/external-odds/team-aliases.json` as the versioned reviewed-alias
source. `load_aliases()` now enforces the exact schema, normalizes keys and
values deterministically, rejects normalized-key and normalized canonical-value
collisions, and rejects alias cycles before a mapping can be used.
`suggest_matches()` uses fuzzy similarity only after sport/time filtering,
returns at most five diagnostics in deterministic score/ID order, and cannot
authorize a match.

Task 3 verification completed with focused matcher tests, full pytest
(`570 passed`), and Ruff (`All checks passed!`).

## Latest Completed Task: API-Sports Transport, Parsing, Cache, and Quota

Added `toto_ai.external_odds.api_sports.APISportsClient` for the approved
coverage audit with separate football and hockey hosts, injected
`requests.Session`, sanitized API-key-only header authentication, deterministic
SHA-256 cache files, quota tracking from response headers, bounded retry for
connection failures and HTTP `408/429/5xx`, and fail-closed sanitized
`APISportsError` / `QuotaExhausted` exceptions.

The adapter now parses football fixture responses and hockey game responses
into provider-neutral `ProviderEvent` records, parses bookmaker odds snapshots
into `ProviderMarket` records without deciding semantic eligibility, and
rejects invalid top-level provider errors, paging, timestamps, prices, and
identifier shapes. Repository tests remain synthetic and deterministic with no
live network dependency, and raw external cache files are ignored by Git.

Recovery hardening added focused regressions for hockey `/games` schedules,
hockey odds `game` queries, rejection of football fixture-shaped hockey
payloads, sanitized non-retry HTTP failures, finite timestamp validation, and
provider-owned price validation before domain object construction.

Review hardening now applies quota headers from every HTTP response before
retry or failure handling and rechecks the reserve before a retry. Cache reads
strictly validate the stored envelope, quota fields, and top-level provider
payload and fail closed with sanitized errors instead of consuming malformed
or partial files. Cache writes use same-directory temporary files plus atomic
replacement, clean up failed temporary writes, and retain no secret-bearing
low-level exception context.

## Approved Next Design: Expected-Value Package Engine

The sealed BK-only hybrid experiment is final with `STOP`. The next direction
does not continue tuning hit-count heuristics. It ranks the complete
`3^15 = 14,348,907` coupon space by modeled monetary expected value.

Approved requirements:

- dynamic bank: any positive multiple of the configurable stake;
- no candidate truncation for speed;
- official cumulative BaltBet category allocation model;
- explicit prize-fund proxy/override and sensitivity reporting;
- explicit independent crowd-ticket model from pool marginals;
- Research mode that always shows top coupons;
- Playable mode with configurable EV threshold and honest `NO BET`;
- no automatic threshold reduction to force bank utilization;
- provider-neutral external probabilities with event-level TotoBrief BK
  fallback; direct Pinnacle scraping is excluded;
- modeled ROI is not profitability evidence without prospective payout data.

Design specification:
- `docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md`

Approved implementation plan:
- `docs/superpowers/plans/2026-07-14-expected-value-package-engine.md`
- Seven TDD tasks: domain/prize math, brute-force oracle, exact ternary engine,
  dynamic-bank selection, fresh drawing CLI/reports, chronological modeled-EV
  backtest, and full-space acceptance.

Next action:
- execute the implementation plan task by task with independent review gates.

## Latest Completed Task: External Odds Domain and TotoBrief Targets

Added the provider-neutral `toto_ai.external_odds` package for the approved
API-Sports coverage audit. The new domain layer defines immutable
`TargetDrawing`, `TargetEvent`, `ProviderEvent`, `ProviderMarket`,
`QuotaState`, and `ExternalOddsProvider` records with strict validation for
UTC-aware datetimes, event order, required identifiers, TotoBrief BK
probability triplets, and optional decimal prices.

Added `parse_target_drawing()` to convert a fresh TotoBrief `drawing-info`
payload into a strict 15-event fallback target set and `classify_sport()` to
honor explicit football/hockey values, detect hockey championship tokens, and
default every other non-empty championship to football. Only an empty
championship classifies as unknown. Target parsing sorts TotoBrief events by
order, splits localized and optional English team names, and preserves normalized
BK probabilities for later fallback provenance.

Task 1 verification completed with focused `external_odds` tests, full pytest,
and Ruff. The added regression accepts any zero-offset UTC-aware datetimes in
the provider-neutral domain instead of requiring the `timezone.utc` singleton.

## Active Design: Hybrid Direct Package Experiment

Approved design:
- Preserve an exact top-probability core of 50%, 75%, or 90% of the package.
- Fill remaining capacity by marginal weighted coverage after accounting for
  scenarios already covered by the core.
- Evaluate only the 350 frozen development drawings in five chronological
  folds; never reopen the old holdout for selection.
- Return GO only for at least two additional 13+ hits, non-loss in at least
  four folds, no lower average best hits, and zero operational failures.
- Return STOP and end optimizer tuning when no candidate passes.

Design specification:
- `docs/superpowers/specs/2026-07-13-hybrid-direct-package-experiment-design.md`

Implementation plan:
- `docs/superpowers/plans/2026-07-13-hybrid-direct-package-experiment.md`
- Five TDD tasks: selector, decision model, fail-closed evaluator, atomic
  reports/CLI, and the frozen development GO/STOP run. Tasks 1-5 are complete.

## Latest Review Fix: Hybrid Development Seal

Added `seal-hybrid-development` to derive a development-only CSV and augmented
manifest from the frozen manifest, the bounded development prefix of the full
backtest CSV, and a read-only SQLite database. The deterministic seal stores
separate SHA-256 hashes for canonical development CSV rows, pre-drawing inputs,
development results, and the fixed hybrid protocol. The seal also records the
clean Git code version. Input/output path collisions are rejected before any
source is loaded, and the manifest/CSV pair is published with rollback-safe
same-directory temporary files.

`evaluate-hybrid` now requires these sealed artifacts. It rejects missing or
mismatched CSV, protocol, and pre-drawing input hashes before result access,
rejects any non-development CSV drawing ID, accumulates result hashes only
after each drawing's top package hash passes, and verifies the final result hash
before summary, decision, or report return. Strategy definitions, fractions,
folds, bank, stake, category, and GO/STOP criteria are unchanged.

The shared package-generation deadline is now checked after every major stage,
including top enumeration, candidate generation, both scenario samples, hybrid
selection, and validation coverage. A timed-out selector returns without a
post-deadline exact coverage pass. Deadline overruns therefore fail closed
instead of being reported as successful zero-timeout drawings.

Both sealing and evaluation reject resolved input/output path collisions before
loading inputs or opening the database, so generated seal/report artifacts
cannot replace a manifest, development CSV, or database.

## Latest Completed Task: Sealed Frozen Hybrid Development Experiment

The approved hybrid direct-package experiment completed on all 350 frozen
development drawings without accessing the 150-drawing holdout during
selection. The final run used the development-only data/code seal at Git
revision `530e1021328bb8436671a273e9ab96b4be03ac06`.

Protocol:
- Bank 5000 RUB, stake 30 RUB, category 13.
- Five chronological development folds of 70 drawings each.
- Compared `top_probability` with hybrid top-core fractions 0.50, 0.75, and
  0.90.
- All four strategies produced 166-coupon packages costing 4980 RUB.
- Operational failures and timeouts: 0.

Development results:
- `top_probability`: 13+ 6, 14+ 1, 15 0, average best hits 8.691429.
- `hybrid_0.50`: 13+ 4, 14+ 1, 15 0, average best hits 9.491429.
- `hybrid_0.75`: 13+ 5, 14+ 1, 15 0, average best hits 9.288571.
- `hybrid_0.90`: 13+ 6, 14+ 1, 15 0, average best hits 9.060000.

Per-fold 13+ counts in strategy order `top_probability`, `hybrid_0.50`,
`hybrid_0.75`, `hybrid_0.90`:
- Fold 1: 0, 0, 0, 0.
- Fold 2: 0, 0, 0, 0.
- Fold 3: 1, 0, 0, 1.
- Fold 4: 1, 1, 1, 1.
- Fold 5: 4, 3, 4, 4.

GO predicates by hybrid core fraction:
- 0.50: additional 13+ -2, non-losing folds 3, average best-hit delta
  +0.800000, operational failures 0; fail.
- 0.75: additional 13+ -1, non-losing folds 4, average best-hit delta
  +0.597143, operational failures 0; fail.
- 0.90: additional 13+ 0, non-losing folds 5, average best-hit delta
  +0.368571, operational failures 0; fail.

Final decision: `STOP`.

No hybrid fraction met every pre-registered GO predicate. All hybrids improved
average best hits, but none produced the required two additional 13+ hits over
`top_probability`. Direct optimizer tuning is closed under the current
BK-only protocol. The old holdout remains excluded and unopened for hybrid
selection. This development-only result is not profitability evidence.

The final sealed rerun completed in approximately 25 minutes and exactly
reproduced the original strategy hit counts, fold counts, average best-hit
metrics, and STOP decision. It processed 1400 evaluation rows with zero
timeouts, exactly 350 development IDs, and zero holdout-ID overlap. This
result remains evidence for the sealed evaluator revision above; subsequent
documentation-only commits do not alter or rerun the experiment.

Reports:
- `reports/hybrid_evaluation_development_last_500_bank_5000.csv`
- `reports/hybrid_evaluation_development_last_500_bank_5000.md`
- `reports/hybrid_development_manifest_last_500.json`
- `reports/hybrid_development_rows_last_500.csv`

The CSV was independently checked: 1400 rows, 350 rows per strategy, and 280
rows per fold.

## Completed Task: Hybrid Evaluation Reports and CLI

Added `write_hybrid_evaluation_reports()` and the fixed `evaluate-hybrid`
command for the approved hybrid experiment. CSV rows use manifest drawing order
and the stable strategy order `top_probability`, `hybrid_0.50`,
`hybrid_0.75`, and `hybrid_0.90`. CSV and Markdown are fully rendered in
same-directory temporary files and closed before either final report is
replaced. Existing final reports are copied to same-directory backups before
publication. If either final replacement fails, both previous reports are
restored byte-for-byte, or both newly published reports are removed when no
previous pair existed; all temporary and backup files are then removed.

The Markdown report records the frozen configuration, five development folds,
total and structural metrics, operational failures, every GO predicate, and
the exact GO/STOP decision. It explicitly labels the result development-only
and as no profitability evidence. Generated reports are ignored by Git.

`evaluate-hybrid` accepts only the database, manifest, frozen backtest CSV, and
report directory paths. It uses `open_readonly_db()` and Rich progress, does
not initialize or migrate the database, and converts controlled failures to
`typer.BadParameter`, including `SQLAlchemyError` database failures.

No evaluation run has been interpreted as profitability evidence. The frozen
holdout remains excluded from hybrid selection.

The worktree CLI help shows only the four path options. Current test and Ruff
verification is recorded once above.

## Latest Completed Task: Development Strategy Diagnostics

Added the fail-closed `diagnose-strategies` command and completed the frozen
development-only diagnostic for the Direct Package Optimizer experiment.
The command opens the existing SQLite database in enforced read-only mode and
cannot create tables or run migrations.

Command:
- `python -m toto_ai.cli diagnose-strategies --db data/toto.db --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv`

Run evidence:
- 350 development drawings processed; the 150 holdout drawings were excluded.
- All regenerated package hashes and recomputed frozen result fields matched.
- Bank 5000 RUB, stake 30 RUB, category 13.
- Weighted vs top best hits: 260 wins, 74 ties, 16 losses.
- Weighted minus top best hits: mean +1.394, median +1.
- Paired 13+ transitions: neither 343, both 3, top-only 3,
  weighted-only 1.
- Average best hits: baseline 8.380, top 8.691, weighted 10.086.
- Observed 13+ frequency: baseline 0.286%, top 1.714%, weighted 1.143%.
- Top vs weighted mean pairwise Hamming distance: 3.491 vs 7.496.
- Top vs weighted mean coupon log probability: -13.682 vs -14.729.
- Average top/weighted package intersection: 11.36 coupons; average Jaccard
  overlap 0.0356.

Interpretation:
- Weighted coverage usually improves the nearest coupon, but its much broader
  and lower-probability package does not improve the observed 13+ threshold.
- No strategy was selected. These are development-only diagnostic findings,
  not holdout evidence and not evidence of profitability.
- The next optimizer experiment should test a development-selected hybrid that
  preserves a high-probability core or probability floor while adding measured
  diversity. It must use a new untouched evaluation window.

Reports:
- `reports/strategy_diagnostics_development_last_500_bank_5000.csv`
- `reports/strategy_diagnostics_development_last_500_bank_5000.md`

Important commits:
- `ec97679` Add development strategy diagnostics command

## Completed Task: Hybrid Package Selector

Added `select_hybrid_package()` for the approved direct-package experiment.
It keeps an exact, unique top-probability core sized with `ceil`, fills only
core-uncovered sampled scenarios through the existing weighted selector, and
uses a deterministic unique probability fallback when time remains. Timeout
paths return only work completed so far. Existing top-probability and weighted
coverage behavior remains unchanged.

Verification at completion: pytest and Ruff passed.

Review follow-up: the hybrid probability fallback now checks the deadline before
each coupon log-probability ranking computation, after sorting, and while
appending. On expiry it returns the unique partial package with `timed_out=True`.
Verification at completion: pytest and Ruff passed.

## Completed Task: Hybrid Fold Metrics and GO/STOP Decision Model

Added the pure `hybrid_evaluation` model for the approved hybrid experiment.
It defines immutable evaluation rows/results, assigns exactly five contiguous
chronological folds, aggregates stable top and hybrid fold metrics, and applies
the fixed GO predicate and deterministic fraction ranking. A STOP selects no
core fraction. This task does not load the database, generate reports, or add
CLI behavior.

Review follow-up: `summarize_hybrid_evaluation()` now fail-closes before
aggregation on invalid folds, duplicate or unpaired rows, unequal or empty
folds, non-chronological fold assignments, and mismatched strategy fractions.
Verification at completion: pytest and Ruff passed.

## Completed Task: Fail-Closed Hybrid Development Evaluator

Added `run_hybrid_evaluation()` for the approved fixed-protocol hybrid
experiment. It validates the 5000 RUB / 30 RUB / category 13 configuration and
five equal development folds before database access, then evaluates only the
manifest development IDs. Per drawing it regenerates and validates the exact
top package plus all three hybrids, reuses candidate and scenario inputs across
fractions, verifies the frozen top hash before loading a result, recomputes the
frozen top fields, and produces four scored rows for the GO/STOP model.

The evaluator fails closed on duplicate/non-divisible development manifests,
protocol mismatches, malformed/incomplete/over-budget/timed-out packages,
frozen hash/result mismatches, and invalid package strategy identities. It does
not add reports or CLI wiring, and never loads the frozen holdout during
selection.

Review follow-up: integrity-boundary coverage now tags every development drawing,
captures real result-bearing Event SQL, and proves a later top-hash mismatch
stops before that drawing's result load or any holdout access.

Verification at completion: focused and full pytest suites plus Ruff passed.

## Previous Completed Task: Package Structure Metrics

Added deterministic package diagnostics for coupon log-probability summaries,
pairwise Hamming diversity, package intersection, Jaccard overlap, and mean
log probability of coupons unique to each package. Empty unique coupon sets
are represented as unavailable (`None`).

## Latest Completed Task: Direct Package Optimizer Experiment

Implemented the approved Direct Package Optimizer and its reproducible
evaluation protocol.

Important commits:
- `e5c4823` Add coupon probability utilities
- `c760515` Add deterministic coupon candidates
- `fd71046` Add weighted direct package optimizer
- `c82b135` Add comparable package strategies
- `4cc8987` Add direct strategy backtest
- `baefa34` Add paired strategy evaluation reports
- `e5b4953` Add frozen direct package experiment
- `5beaeae` Ignore generated strategy experiment reports

Frozen retrospective experiment:
- Code version: `5beaeae4d7801748e82a4ae9a0003be4e0796d81`
- Manifest: `reports/strategy_experiment_manifest_last_500_exclude_10.json`
- 500 eligible drawings, 350 development and 150 holdout
- Latest 10 previously exposed drawings excluded
- Bank 5000 RUB, stake 30 RUB, category 13, seed 42
- 500/500 drawings evaluated; no skips, generation errors, invalid packages,
  or timeouts

Holdout results:
- `baseline_brief`: hit13 2, hit14 1, hit15 0, average best hits 8.59,
  average cost 663 RUB
- `top_probability`: hit13 6, hit14 1, hit15 0, average best hits 8.86,
  average cost 4980 RUB
- `weighted_coverage`: hit13 5, hit14 0, hit15 0, average best hits 10.23,
  average cost 4980 RUB
- Paired weighted-vs-baseline hit13 difference: +2.00 percentage points
- 95% paired bootstrap interval: [-0.6667, 5.3333]
- Status: preliminary; the interval includes zero

Interpretation:
- Direct strategies outperform the low-cost baseline on raw holdout hit13
  counts, but superiority is not statistically established.
- `top_probability` currently has the highest holdout hit13 count.
- `weighted_coverage` has substantially higher average best hits, but that
  improvement has not yet converted into more 13+ hits.
- This is a retrospective benchmark, not independent prospective evidence and
  not evidence of profitability.

## Exact Cover Example

- 144 full brief variants
- 8 coupons
- Category 13
- 100% exact verified coverage
- Worst minimum Hamming distance 2

## Previous Completed Task

Fixed unsafe Budget Oracle pruning.

- Disabled dominance pruning because it changed oracle best-hit metrics.
- Disabled pruning based on full-cover coupon-cost bounds because Budget Oracle
  evaluates useful partial packages under budget.
- Restricted incumbent pruning to candidates whose maximum possible hit count
  is strictly below the incumbent's actual hit count.
- Added regression coverage comparing optimized and exhaustive selection.
- Removed the unused unsafe pruning helpers.

Local smoke result on `data/toto.db`:
- `budget-oracle --last 3 --bank 10000 --stake 30 --category 13 --no-progress --profile-workload`
  found 15 hits for all three processed drawings.
- All pruning counters were zero; two drawings reached the configured timeout,
  so these rows are partial oracle evidence rather than exhaustive optima.

## Previous Completed Task

Profiled Budget Oracle candidate workload.

The `budget-oracle` command now supports:
- `--profile-workload` to print aggregate candidate workload diagnostics.
- Per-drawing generated candidate count.
- Per-drawing unique candidate count.
- Cover Engine call count.
- Cache hit/miss counts, where duplicate candidate briefs avoided by
  deduplication are counted as hits and actual Cover Engine evaluations are
  counted as misses.
- Average and maximum brief variant counts.
- Average Cover Engine call duration.
- Slowest 10 candidate briefs across the run.

This does not change oracle search logic, candidate scoring, or default search
space.

## Previous Completed Task

Optimized Cover Engine performance without changing mathematical results.

The Cover Engine now:
- Caches expanded brief variants.
- Caches coverage bitsets by `(brief, category)`.
- Builds coverage via bounded outcome mutation instead of rebuilding all
  coupon/variant Hamming comparisons.
- Uses integer bitsets for greedy uncovered coverage tracking.
- Keeps the same selected coupons, coverage rate, worst minimum distance, and
  guarantee result on the representative regression case.

Benchmark evidence:
- Pre-optimization representative cover runtime: about 1.70s for 1024 variants.
- Post-optimization representative cover runtime: about 0.04-0.05s.
- Speedup: about 35x on the representative benchmark.
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13 --no-progress`
  completed in about 0.5 seconds without `--max-candidates`.

New command:
- `python -m toto_ai.cli benchmark-cover`

## Previous Completed Task

Improved Budget-Constrained Brief Oracle observability and diagnostics.

The `budget-oracle` command now supports:
- Rich progress updates with drawing number, drawing index, candidate index,
  elapsed time, average drawing time, ETA, current best hits/cost, and
  processed/skipped/timed-out counts.
- `--timeout-per-drawing` to keep the best candidate found so far and mark the
  row as timed out.
- `--max-candidates` as an explicit optional candidate limit. Omitted means full
  search.
- `--progress/--no-progress`.
- Partial CSV writes every 10 drawings.
- Per-drawing profiling timings for candidate generation, cover generation,
  verification, and total time.
- Final timing summary.

Local smoke result on `data/toto.db`:
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13 --max-candidates 3 --no-progress`
  completed in about 5 seconds.

## Earlier Completed Task: Budget-Constrained Brief Oracle

Implemented Budget-Constrained Brief Oracle.

The `budget-oracle` command uses actual results only as an oracle benchmark. It
searches BK-ranked candidate briefs that include the actual outcome, runs the
Cover Engine under the same budget/stake/category constraints, and compares the
best oracle package hits against the baseline brief generator.

Command:
- `python -m toto_ai.cli budget-oracle --db data/toto.db --last 500 --bank 10000 --stake 30 --category 13`

Exports:
- `reports/budget_oracle_last_<N>.csv`
- `reports/budget_oracle_last_<N>.md`

Metrics:
- Oracle average best hits
- Oracle hit13/hit14/hit15
- Average singles, doubles, triples
- Average oracle package size and cost
- Baseline generator average best hits
- Oracle vs baseline gap

Local smoke result on `data/toto.db`:
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13` completed in
  about 9 seconds.

## Earlier Completed Task: Project Knowledge Base

Created the persistent project knowledge base.

New repository-local project knowledge areas:
- `memory-bank/`: current state, roadmap, architecture, philosophy, decisions.
- `knowledge/`: concise domain notes for TotoBrief, bookmaker calibration,
  crowd bias, closing line, and Pinnacle integration status.
- `skills/`: project-local workflow checklists for algorithm review, research,
  and backtesting.
- `prompts/`: reusable project prompt templates for feature, research, and
  backtest tasks.

The project rule is now explicit: after every completed feature, update the
project knowledge base first.

## Earlier Completed Task: Brief Oracle Research

Implemented Brief Oracle Research.

The `brief-oracle` command finds the smallest oracle brief that contains the
actual 15-outcome result for completed drawings using BK probabilities only.

Exports:
- `reports/brief_oracle.csv`
- `reports/brief_oracle.md`
- `reports/brief_oracle_by_event.csv`

Per drawing it records:
- singles, doubles, triples
- full brief variant count
- log brief probability
- actual result string
- oracle brief string
- BK rank counts for actual outcomes
- average BK rank and actual-result BK probability
- pool/BK top disagreement diagnostics

Aggregate metrics include:
- average singles, doubles, triples
- p25/p50/p75/p90 full variant counts
- doubles and triples distributions
- BK rank frequency for actual outcomes
- entropy by required cover size

## Earlier Completed Task

Implemented bookmaker calibration research.

The `calibration` command measures:
- Bookmaker reliability by 5 percentage-point bins for outcomes 1/X/2
- Pool reliability by the same bins
- Overall Brier score
- Log loss
- Expected Calibration Error
- Pool vs bookmaker bias
- Draw calibration
- Favorite calibration for BK >= 60%
- Underdog calibration for BK <= 25%

Exports:
- `reports/calibration.md`
- `reports/calibration.csv`
- `reports/reliability.csv`

## Earlier Completed Task: Backtest Optimization

Optimized the Baseline Brief Generator backtest.

The `backtest-brief` command now includes:
- Rich progress for drawing number, candidate index, elapsed time, and best
  score.
- Cover Engine cache keyed by brief tuple, category, and max coupon count.
- Candidate brief deduplication.
- Cheap candidate scoring before exact cover.
- Exact cover/verifier only for top candidates.
- Per-drawing timeout fallback.
- Per-drawing timing metrics.
- `--top-candidates`, `--max-candidate-briefs`, and
  `--timeout-per-drawing` options.

Exports:
- `reports/backtest_brief_last_<N>.csv`
- `reports/backtest_brief_last_<N>.md`

Local smoke results on `data/toto.db`:
- `backtest-brief --last 1 --bank 10000 --stake 30 --category 13` completed
  in about 4.7 seconds.
- `backtest-brief --last 10 --bank 10000 --stake 30 --category 13` showed
  progress and completed in about 41 seconds, testing 9 drawings with one
  skipped due to missing pre-match BK/pool probabilities.

## Latest Completed Task: Expected-Value Domain Math

Task 1 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev` package exposes immutable `EVConfig`, `EVInput`, `EVComponents`,
`EVSurface`, `RankedCoupon`, and `EVPackage` models, plus bank validation,
official cumulative category-fund allocation, triplet normalization, and
Jeffreys-smoothed crowd marginals. `EVConfig` validates positive integer banks
and stakes, including divisibility, during construction; its
`max_coupons` result is always an integer without forcing full bank
utilization. `EVComponents` and `EVSurface` defensively copy and freeze their
NumPy arrays. The exported `CROWD_JOINT_MODEL` contract is
`independent_event_marginals`: later joint coupon probabilities are modeled as
products of the smoothed event marginals.

## Latest Task 1 Fix Wave: Hardened EV Immutability

The second Task 1 fix wave enforces the same positive-integer stake contract in
`smooth_crowd_matrix()` as `validate_bank()`, including rejection of booleans,
floats, zero, and negative values. `EVInput` now deep-normalizes probability
matrices and probability sources to tuples and rejects probability rows that do
not contain three outcomes. `EVPackage` deep-normalizes coupons and derived
brief values to tuples. EV arrays are defensive copies exposed through owned
immutable byte buffers, so their shapes and dtypes are preserved and callers
cannot re-enable writes with `setflags(write=True)`.

Verification for this fix wave: focused EV tests `48 passed`, full pytest
`336 passed`, focused Ruff passed, and full Ruff passed. NumPy remains
intentionally undeclared in `pyproject.toml` until Task 3.

## Latest Completed Task: Independent Brute-Force EV Oracle

Task 2 of the Expected-Value Package Engine is complete. The reference oracle
enumerates actual results and coupons with `itertools.product(range(3),
repeat=event_count)`, preserving deterministic C-order base-three indexing.
It exposes independent joint distributions, Hamming hit counts, crowd
qualifying stakes, coupon payouts, and exhaustive gross EV for event counts up
to eight. Zero-valued outcome probabilities are accepted when the modeled
category denominators remain finite and positive; invalid category denominators
fail closed before payout division.

Verification: focused reference tests `11 passed`; full pytest `347 passed`;
focused Ruff passed; full Ruff passed.

## Latest Task 2 Review Fix: Hardened Reference Validation

The brute-force EV reference now requires every probability row to contain
exactly three finite non-negative values whose sum is one within
`rtol=1e-12` and `atol=1e-12`, while preserving valid zero probabilities.
`coupon_payout()` validates category ranges against the event hit count,
non-negative finite category funds, positive finite qualifying stakes for
every funded category, and strict positive integer stakes. Brute-force EV
rejects out-of-range categories before enumeration, and all public integer
contracts reject booleans.

Verification: focused reference tests `36 passed`; full pytest `372 passed`;
focused Ruff passed; full Ruff passed.

## Latest Completed Task: Exact Ternary Full-Space EV Engine

Task 3 of the Expected-Value Package Engine is complete. Flat arrays and coupon
strings preserve C-order base-three indexing with outcome order `1`, `X`, `2`.
The exact engine builds product probability arrays with repeated Kronecker
products. It computes each crowd qualifying probability over every actual-result
state with a chunked independent-marginal Poisson-binomial DP, then processes
the coupon-side Hamming-ball category sequentially through ternary FFT
convolution. Category denominators must remain finite and positive, and an
interruption propagates without returning a partial EV surface.

`compute_ev_components(EVInput, progress_callback=None)` uses only the official
9..15 regular-prize and jackpot coefficients and returns separate immutable
unit arrays so prize sensitivity can reuse the heavy calculation.
`materialize_ev_surface()` performs the light regular-prize/jackpot scaling.
For small-space oracle work, the explicit convenience signature is
`compute_ev_surface(true_probabilities, crowd_probabilities, pool_sum,
category_funds_by_hits, stake, minimum_category, progress_callback=None)`;
this preserves arbitrary category-fund mappings rather than weakening oracle
equivalence.

The deterministic `benchmark-ev` command records elapsed time, peak resident
memory when available, probability masses, minimum denominator, exact error,
fixed sample diagnostics, and normalized SHA-256 array hashes. Event counts up
to eight compare the complete surface to the independent brute-force oracle;
larger spaces independently verify sampled crowd tails with scalar
Poisson-binomial arithmetic and fixed coupon EVs with direct vectorized hit
comparisons over every actual-result state. Official benchmark expectations are
literal and do not share the production category-fund map. Array hashes are
diagnostic fingerprints only and do not affect PASS/FAIL.

Verification: focused Task 3 tests `35 passed`; full pytest `407 passed`; focused
and full Ruff passed. The five-event CLI benchmark verified all 243 coupons
against the oracle with maximum absolute error `1.897e-19` and status `PASS`.
The mandatory 15-event acceptance benchmark remains deferred to Task 7 and was
not run for Task 3.

## Latest Task 3 Mathematical Review Fix

Removed the absolute FFT cutoff that could erase legitimate positive values.
`ternary_convolve()` now copies the real inverse result away from its complex
buffer, preserves every positive value, clips only negative values within a
scale-aware roundoff tolerance, and raises on material negative output.

Crowd category denominators no longer use FFT recovery. For each category, a
bounded-memory Poisson-binomial DP evaluates `P(matches >= k | actual result)`
for all `3^n` actual-result states without state truncation. Regressions cover
all-positive five-event full spaces and a selected 15-event state with
`(0.999998, 0.000001, 0.000001)` marginals; the latter remains positive at
approximately `1e-90` without allocating the full 15-event state space.

The larger-space benchmark verifier no longer reuses production denominators,
Hamming kernels, or coupon convolution. It compares sampled production tails
to a scalar independent recurrence and recomputes sampled coupon components by
direct vectorized hit comparisons over every actual-result state in chunks.

Verification for this fix: focused Task 3 tests `45 passed`; full pytest
`417 passed`; focused and full Ruff passed. `benchmark-ev --events 5 --samples
10` verified all 243 coupons against the brute-force oracle in `0.116300 s`,
with `62.84 MiB` peak resident memory, minimum denominator `1828.14404892`,
maximum EV error `1.626e-19`, zero sampled crowd-tail error, and status `PASS`.
The full 15-event benchmark was not run, as instructed; its runtime and peak
memory remain Task 7 acceptance concerns.

## Final Task 3 Formula Fix: Exact Crowd Mass Handling

The production accumulation now materializes both C-order Kronecker product
arrays `Q` and `R`. It validates finite unit mass from `R.sum()` within `1e-12`,
records that value as `crowd_mass`, and releases `R` before category work. The
Poisson-binomial denominator DP remains the only denominator path and does not
consume or truncate `R` states.

For tolerance-accepted rows that are not bit-exact unit mass, production and
both independent benchmark recurrences now compute non-match probability from
the supplied row (`row_sum - selected match`) rather than `1 - selected
match`. This preserves the accepted row mass and agrees with the independent
brute-force joint reference. Regressions cover production tails, scalar tails,
direct coupon sums, full EV surfaces, C-order `R` auditing/release, and existing
tiny-positive behavior.

Verification: focused Task 3 tests `48 passed`; full pytest `420 passed`.
The five-event benchmark (`243` coupons) passed in `0.121526 s` with `62.00
MiB` peak resident memory, maximum EV error `1.626e-19`, and zero sampled
crowd-tail error. The 15-event benchmark was not run.

## Latest Completed Task: Dynamic-Bank EV Package Selection

Task 4 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.package` module ranks every validated `3**event_count` EV value
with a complete deterministic NumPy order: descending gross EV, then ascending
base-three coupon index for values tied under `rtol=1e-12` and `atol=1e-15`.
It does not truncate candidates or create a Python object per coupon; only the
selected package rows become `RankedCoupon` values.

Research mode fills the dynamic bank capacity even where gross EV is below one
and labels the result `RESEARCH ONLY`. Playable mode selects only coupons at or
above its configured threshold, can leave bank unused, and returns `NO BET`
with zero cost when none qualify. Packages report cost, unused bank, expected
payout, modeled ROI, and an outcome-union brief in `1`, `X`, `2` order.
Modeled ROI remains a model output, not evidence of profitability.

Verification: focused package tests `19 passed`; full pytest `439 passed`;
focused and repository-wide Ruff passed. Playable threshold tests cover
0.90/0.95/1.00/1.05 with monotonic selected-count assertions.

## Task 4 Review Hardening: Full-Surface Ranking

The full-surface ranker now handles every accepted real numeric dtype without
negating unsigned arrays. It creates one complete ascending index order with
NumPy quicksort, reverses that order in bounded chunks, and then scans adjacent
EV values in fixed-size chunks. Only actual tolerance-tie candidate blocks are
processed; common no-tie surfaces do not enter Python once per coupon. Each
candidate block is split by the specified run-first `rtol=1e-12`,
`atol=1e-15` rule and its tie runs are sorted in place by base-three index.

Regressions cover unsigned zero ordering, non-transitive adjacent-close chains,
candidate blocks crossing scan chunks, no singleton candidate processing, and
complete-order `RankedCoupon.rank` values when threshold filtering skips an
earlier tolerance-tied coupon.

Verification: focused package tests `24 passed`; full pytest `444 passed`;
repository-wide Ruff passed. Synthetic no-tie `uint32` and all-tie `uint8`
surfaces both ranked all `3**15 = 14,348,907` indices exactly. The combined
process completed in `1.00 s`; `/usr/bin/time -l` reported a `229,786,488`-byte
peak memory footprint and `433,176,576`-byte maximum resident set size while
running both surfaces sequentially.

## Latest Completed Task: Fresh Drawing EV Package Command

Task 5 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.drawing` path resolves only page one of the live TotoBrief API,
chooses the nearest future `active`/`expected` drawing by `(ended_at, id)`, and
immediately fetches `drawing-info`. It never falls back to SQLite. The fresh
receipt timestamp is recorded in UTC.

Drawing parsing requires exactly event orders 0 through 14, normalizes every BK
triplet, applies the approved Jeffreys smoothing to every pool triplet, and
fails closed on missing or invalid pool, jackpot, quote, and possible-winnings
inputs. Possible winnings are either an explicit override with the default
factor or the disclosed `pool_sum * prize_fund_factor` proxy. Event results are
not consumed.

`build_open_ev_package()` computes the complete reusable category components
once, materializes and selects the 0.70/0.80/0.90/1.00 sensitivity surfaces,
and reuses the configured factor's package where applicable. No probability or
coupon candidate space is truncated. Package cost divided by `pool_sum` is the
self-dilution ratio: exactly 1% remains supported; above 1% is unsupported.
Unsupported Playable output suppresses `PLAY` to `NO BET`, while Research output
retains diagnostics and an explicit warning.

The new rollback-safe report publisher fully renders deterministic exact-package
CSV and Markdown artifacts before publication and restores both prior files if
the second final replacement fails. Reports disclose fresh timestamps, sources,
the independent-event crowd model, prize factor, bank and self-dilution ratios,
decision, package metrics, derived brief, top-20 diagnostics, sensitivity, and
that modeled ROI is not observed ROI.

`ev-package` requires `--open`, accepts the exact planned mode, bank, stake,
threshold, prize-factor, possible-winnings, and jackpot options, and uses Rich
phase/category progress. API, validation, numerical, interruption, and report
failures become controlled `BadParameter` errors. An interrupted calculation
prints no `PLAY` decision.

Verification before documentation: focused Task 5/API-inspector tests `34
passed`; full pytest `468 passed`; CLI help listed all eight planned options;
repository-wide Ruff passed.

## Task 5 Review Hardening

Unsupported Playable runs are now fully non-actionable. When the proposed
package exceeds the 1% self-dilution limit, the returned package is `NO BET`
with no coupons, zero cost and expected payout, the full bank unused, no
modeled ROI, and an empty derived brief. Sensitivity rows apply the same
suppression, and the exact package CSV contains only its header. Research mode
still retains diagnostic coupons and the unsupported warning. The exact 1%
boundary remains supported.

Atomic report publication now rolls back after any `BaseException`, including
`KeyboardInterrupt` and `SystemExit`, once publication has started. The
original exception is re-raised after both prior artifacts are restored and
temporary/backup files are cleaned.

Fresh `drawing-info` payload IDs must exactly match the requested drawing ID
before EV components are computed. Oversized numeric conversion failures are
normalized to `ValueError`, CLI overflow failures become controlled
`BadParameter` output, and parser receipt timestamps must include an explicit
timezone. Reports now disclose whether jackpot came from the TotoBrief payload
or an explicit override.

Sensitivity factors are materialized and selected sequentially. The workflow
retains only scalar sensitivity summaries and the requested main
surface/package; instrumentation observes at most the main surface plus one
transient sensitivity surface. Main package selection and bounded top-20
diagnostics share one complete deterministic ranking. Every `3**15` EV value
is still ranked for selection; no probability or coupon candidate truncation
was introduced.

Review-fix verification before documentation: focused EV/API-inspector tests
`66 passed`; full pytest `476 passed`; CLI help listed all planned options;
repository-wide Ruff passed.

## Latest Completed Task: Chronological Modeled-EV Backtest

Task 6 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.backtest` module exposes immutable config, row, summary, and result
types. It validates dynamic stake-multiple banks, finite unique thresholds and
prize factors, and validated frozen holdout IDs from the existing strategy
manifest loader.

Finished drawing candidates are selected from `Drawing` rows with holdout IDs
excluded in SQL before any event or quote query. Historical EV inputs query
only ordered event identifiers and BK/pool quote columns; actual result columns
are loaded only after all factor/bank/threshold packages and deterministic
SHA-256 hashes for that drawing are complete. Inputs require exactly orders
0..14, valid normalized BK rows, Jeffreys-smoothed pool rows, positive pool
sum, and non-negative jackpot.

Each drawing builds one reusable exact component set. Every prize-fund factor
materializes and ranks one complete surface, then reuses that ranking across
all banks and thresholds without candidate limits or timeouts. Selection is
monotonic by threshold, respects exact bank caps, leaves unused bank, and emits
honest zero-cost `NO BET` rows. Realized output records best hits and cumulative
9..15 indicators.

Completed drawings are atomically checkpointed to a diagnostic partial CSV
bound to the exact normalized run configuration, requested window, community,
and forbidden IDs. Resume accepts only complete drawing groups and does not
turn interrupted work into report rows. Final reports include modeled expected
payout/ROI, bank utilization, hit rates, skip rate, and the over-80% model
review alert. They state that expected crowd denominators are modeled and that
modeled payout/ROI are not observed bookmaker payout/ROI.

`backtest-ev` requires `--frozen-manifest`, resolves forbidden IDs before
opening the read-only database, parses comma-separated banks and thresholds
deterministically, and shows drawing/category progress with ETA.

Verification: focused backtest/report tests `27 passed`; full pytest `497
passed`; worktree-local CLI help listed all six options and marked the manifest
required; repository-wide Ruff passed. No historical EV run was interpreted as
profitability evidence, and the old frozen holdout was not used for development
or evaluation.

## Task 6 Review Hardening

`--last N` now means the latest `N` drawings that ultimately have both valid
pre-result inputs and complete normalized actual results. Candidates are scanned
newest-first; each package surface, ranking, selection, and hash is completed
before that candidate's result projection is queried. Incomplete or invalid
newer candidates are skipped and older candidates are evaluated until `N`
complete drawings are obtained. Returned rows remain chronological.

Checkpoint skip records are diagnostic only and are re-evaluated on every
resume. Only completed drawing row groups are reusable. Loading now requires the
exact unique Cartesian grid of configured bank, threshold, and prize factor for
each completed drawing, and validates decision, bank cap, selected count, cost,
unused bank, payout/ROI, self-dilution support, package hash, best hits, and all
9..15 indicators. Stale skips can become processed drawings and displace older
checkpoint rows while preserving same-config equivalence with uninterrupted
execution.

Historical Playable rows now apply the same self-dilution boundary as the live
command: exactly 1% remains supported, while above 1% is a truly empty `NO BET`
with zero cost/payout, full unused bank, no modeled ROI, and explicit ratio and
support fields. Summaries include unsupported counts. Final reports and CLI
checkpoints include the full configuration hash in their deterministic paths,
so bank, threshold, or frozen-manifest holdout changes cannot overwrite another
configuration's artifacts.

Leakage regressions inspect SQL order and projections: the initial `Drawing`
query contains holdout exclusion before any event/quote query, pre-hash input
queries omit `Event.result`, and the result projection appears only after the
`packages_ready` callback carries deterministic hashes. A manageable complete
`3^3` orchestration regression uses real materialization and the production
ranker once per factor and confirms all 27 coupons remain available; full
15-event acceptance remains Task 7.

Review-fix verification: focused backtest/report tests `36 passed`; full pytest
`506 passed`; CLI help listed all required options; focused and repository-wide
Ruff passed.

## Final Task 6 Checkpoint Integrity

Checkpoint CSVs now include one deduplicated `package` manifest record per
referenced package hash. Each record stores the canonical ordered coupon payload;
loading requires unique 15-character `1`/`X`/`2` coupons, recomputes SHA-256 with
the production comma-separated encoding, and matches coupon counts against every
referencing row. Every `PLAY` row must reference a non-empty manifest, while
`NO BET` references only the empty payload and `EMPTY_PACKAGE_HASH`. Missing,
duplicate, conflicting, orphan, malformed, or tampered manifests reject resume.
Coupon payloads remain checkpoint-only and are not added to final report rows.

SQL leakage tests now retain statements and bound parameters. They prove the
initial `Drawing` query excludes frozen holdout IDs, every Event or Quote query
is scoped to exactly one allowed drawing ID, no forbidden ID reaches those
queries, pre-hash projections omit `Event.result`, and actual results are queried
only after `packages_ready` exposes package hashes.

Final integrity verification: focused backtest/report tests `41 passed`; full
pytest `511 passed`; worktree-local `backtest-ev --help` exited successfully with
required `--frozen-manifest`; repository-wide Ruff passed.

## Final Task 6 Row Binding

Checkpoint package manifests now commit not only to exact coupon payloads but
also to canonical sorted unique `(drawing_id, bank, threshold,
prize_fund_factor)` references. The loader derives the expected references from
completed rows and requires exact per-hash equality, so every row context maps
to exactly one matching manifest and equal-count valid package hashes cannot be
swapped between rows. Duplicate, missing, extra, unsorted, or non-canonical
references reject resume. The coupon hash remains solely a hash of the canonical
coupon payload, and row contexts remain checkpoint-only metadata.

The SQL leakage regression now identifies Event/Quote access from SQL table
references, requires every such statement to follow the holdout-filtered
`Drawing` query, and extracts the drawing-ID bind only from an explicit
`events.drawing_id = ?` or `quotes.drawing_id = ?` predicate. Synthetic
Event-only and Quote-only unscoped statements prove unrelated integer binds
cannot satisfy the regression. Pre-package input projections still omit
`Event.result`.

Row-binding verification: focused backtest/report tests `48 passed`; full pytest
`518 passed`; worktree-local `backtest-ev --help` exited successfully with
required `--frozen-manifest`; repository-wide Ruff passed.

## Latest Completed Task: End-to-End EV Acceptance

Task 7 of the Expected-Value Package Engine is complete. Acceptance tests cover
the fresh 15-event payload boundary with an injected deterministic small-space
surface, honest zero-cost `NO BET`, dynamic bank capacity, deterministic report
hashes, complete model assumptions, rollback-safe interruption behavior, and a
direct regression for the independent reference oracle's eight-event limit.
No production EV definition or search behavior changed during acceptance.

Fresh acceptance evidence:

- Full pytest: `526 passed in 5.39s`.
- Repository-wide Ruff: `All checks passed!`.
- Five-event benchmark: `243` coupons, `PASS`, `0.116127 s`, `62.44 MiB`
  peak memory, maximum EV error `1.626e-19`, and zero crowd-tail error.
- `ev-package --help` and `backtest-ev --help` exited successfully and exposed
  every documented option; the latter retained required `--frozen-manifest`.
- Because the shared editable virtual environment targets the parent checkout,
  worktree CLI acceptance used `PYTHONPATH=src` to select this branch's source.

Mandatory full-space benchmark evidence:

- Event count: `15`.
- Coupon count: `14,348,907` (`3^15`), with no candidate truncation.
- Independent samples: `20`.
- Verification: `PASS`.
- Elapsed time: `61.763504 s`.
- Peak resident memory: `1958.73 MiB`.
- Minimum denominator: `0.00550589657572`.
- Maximum sampled EV absolute error: `7.994e-15`.
- Maximum sampled crowd-tail absolute error: `2.776e-17`.

The EV engine is mathematically and operationally accepted under its approved
experimental prize-fund proxy and independent-event crowd model. `PLAY` remains
model output, not a profit guarantee. External probability collection, event
matching, and prospective observed-payout validation remain separate work.

## Latest Completed Task: External Odds Coverage Audit Reports and CLI

Task 6 of the API-Sports coverage audit is complete. Added a read-only
coverage audit over the latest complete stored external-odds snapshot per
drawing. The audit reports all 15 event dispositions for every audited drawing,
including explicit silent-loss diagnostics if a stored snapshot is malformed,
and aggregates overall, per-sport, per-league, and per-drawing metrics for
unique matches, missing/ambiguous/unknown-sport outcomes, consensus coverage at
one/two/three bookmakers, fallback reason classes, quota/provider failures,
fallback events per drawing, and requests consumed per drawing.

The prospective gate returns `PENDING` below 30 drawings or 450 events, `GO`
only when the registered thresholds pass, and `STOP` otherwise. The registered
thresholds remain at least 80% unique matching, at least 70% usable consensus,
zero ambiguous matches, and explicit external/fallback disposition for every
event. Per-sport and per-league metrics are diagnostic only and add no gate.

Added deterministic rollback-safe external coverage CSV/Markdown reports. The
CSV contains one row per event disposition followed by stable aggregate rows.
The Markdown records configuration, provenance/quota summaries, overall/sport/
league/drawing metrics, fallback reasons, gate predicates, and explicit
statements that coverage is neither probability quality nor profitability
evidence.

Added `collect-external-odds --open --provider api-sports --db ...` and
`audit-external-coverage --db ... --last ... --min-bookmakers ...`.
Collection requires `--open`, `provider=api-sports`, and `API_SPORTS_KEY`
before constructing the provider. Audit opens the existing SQLite database in
read-only mode, performs no migrations or network calls, and writes reports
from stored snapshots only. This remains audit-only and does not change
`ev-package` or `PLAY`.

Verification before final commit: focused audit/CLI tests passed (`13 passed`),
full pytest passed (`607 passed`), both new CLI help commands exited
successfully, and repository-wide Ruff passed.

## Task 6 Review Hardening: Complete Coverage Report Schema

Coverage reports now expose every `CoverageMetrics` field consistently.
Aggregate CSV rows include stale, semantic, and incomplete-market counts, while
event rows also expose provider event IDs and per-collection request counts.
Sport, league, and drawing Markdown tables include explicit disposition,
match, missing/ambiguous/unknown-sport, bookmaker availability at one/two/three,
usable consensus, stale, semantic, incomplete-market, quota, provider-error,
and fallback metrics in deterministic scope/name order.

Fallback classification now parses only canonical stored consensus-rejection
tokens. Stale prices, missing outcomes, duplicate bookmaker markets, and
football/hockey settlement-semantic rejections are counted exactly once per
event; incidental substrings do not collide with stale, semantic, incomplete,
quota, or provider-error classes. One- and two-bookmaker availability includes
matched minimum-bookmaker fallbacks, while usable consensus still requires the
configured minimum and an external-consensus disposition. The prospective gate
and its thresholds are unchanged.

Added dedicated report tests for all 15 disposition rows, complete aggregate
schema/content/order, complete Markdown sections and scope metrics,
byte-identical repeat writes, and rollback/temporary-file cleanup after a
`BaseException`. Focused audit/report/CLI verification passed (`28 passed`).
Full pytest passed (`622 passed`), repository-wide Ruff passed, and both new CLI
help commands exited successfully with their required options. Exact command
evidence is also recorded in the ignored Task 6 report.

## Approved Next Design: API-Sports Coverage Audit

The next isolated subsystem is a prospective, free-tier-first external odds
coverage audit. API-Sports is the first provider because its football and hockey
APIs expose pre-match odds on the free plan. This stage does not change
`ev-package` or any accepted EV definition.

The design requires deterministic fail-closed event matching, strict football
full-time and hockey regulation-time `1/X/2` semantics, per-bookmaker de-vig,
a three-bookmaker median consensus, explicit event-level TotoBrief BK fallback,
quota-aware caching, append-only provenance, and no secret persistence.

The prospective gate requires at least 30 future drawings and 450 events, at
least 80% unique event matching, at least 70% fresh complete consensus coverage,
zero consumed ambiguous matches, and an explicit external/fallback disposition
for every event. A failed gate tests a second free provider before any paid plan.
Payment up to 30 USD/month is considered only when measured quota limits, rather
than missing events or markets, are the cause of failure.

Design specification:
- `docs/superpowers/specs/2026-07-14-api-sports-coverage-audit-design.md`

Next action:
- execute the seven-task TDD implementation plan with independent review gates.

Implementation plan:
- `docs/superpowers/plans/2026-07-14-api-sports-coverage-audit.md`
- Tasks: provider-neutral targets, API-Sports transport/cache/quota, fail-closed
  matching and manual alias suggestions, strict three-way consensus,
  append-only storage/collection, audit reports/CLI, and end-to-end acceptance.

## Latest Completed Task: Live API-Sports Contract Hardening

Authorized live checks found several assumptions that synthetic fixtures had
missed. Football `/fixtures` rejects `page`; official response envelopes omit a
top-level timestamp; odds items omit `teams`; unrelated odds markets may use
numeric outcome labels; a daily quota reserve must not be applied to the
per-minute allowance; and cached quota headers must not act as current quota.
The client now follows those live contracts, stores an explicit receipt time in
cache schema v2, and preserves raw provider payload hashes.

Open TotoBrief drawing 4945 (`id=11953`) returned `start_at=null` and
`name_en=null` for all events. Target times are now optional. Matcher v2 keeps
the three-hour filter when target time exists; otherwise it accepts only one
unique exact directional team match in the deadline-date/next-date schedule
window. Reviewed aliases were added only for pairs observed in live API-Sports
records. Fuzzy and reversed pairs remain unconsumed.

The first complete prospective snapshot contains 15 explicit dispositions,
11 external consensuses, four TotoBrief BK fallbacks, zero ambiguous matches,
two actual HTTP requests on the final cache-assisted run, and 11 cache hits.
Coverage audit result: 73.33% unique matching and consensus, decision `PENDING`
because the 30-drawing/450-event sample floor is not met.

Verification target after documentation: full pytest and repository-wide Ruff.
Next isolated task: decide and test exact reversed-pair handling with explicit
`1`/`2` orientation swapping; do not silently consume reversed provider events.

## Multi-Day Eligibility Task 3A: Persistence Complete

External collection storage now persists the target fingerprint, configured
missing-start horizon, canonical per-date schedule results, drawing
eligibility, provider start, effective start, and timing source. Existing
SQLite databases receive additive columns; legacy runs remain readable only as
`unknown`, and read-only database opening never performs a migration.

`load_current_drawing_eligibility` returns a verdict only for a complete
15-event run matching the exact drawing ID and target fingerprint. Malformed
schedule JSON and inconsistent timing/eligibility provenance fail closed.
Focused verification passed: 16 storage tests and Ruff on all touched files.
Task 3 audit/report diagnostics remain next; category, bank, probability, EV,
and coverage-gate definitions are unchanged.

## Multi-Day Eligibility Task 3B: Audit and Reports Complete

Coverage auditing now exposes target fingerprint, collection horizon,
requested/successful/failed schedule dates, event timing sources, drawing
eligibility, provider-missing events, and partial-schedule events. Diagnostic
collection scopes are disjoint and deterministic: `ordinary_two_day`,
`expanded`, `multi_day`, and `unknown`. Legacy collections stay in `unknown`.

The existing overall coverage-gate population, predicates, and thresholds are
unchanged; scoped metrics are diagnostic only. Failed schedule dates are
counted independently from affected event fallbacks. CSV and Markdown reports
remain atomic and deterministic. Focused verification passed (`37 passed`),
Ruff passed, and repeated report hashes were byte-identical:
`45359a3edb07741261cf3cfa5caa3e6f85628f99e76adb3e9998afa4400655b5`
for CSV and
`796fb78654a5db4a6c0bb9d9f8979fcf37b34c1b1d2f229ee9e080692f6544bb`
for Markdown. Task 4 progressive orchestration is next.

## Multi-Day Eligibility Task 4: Progressive Collection Complete

Fresh prospective collection now has two bounded phases. Base collection keeps
the existing two-day horizon and `max_passes` semantics. A stable canonical
`0 exact candidates` miss expands through day five only when the original
TotoBrief event start is absent. Known-start misses never expand. Expansion has
its own pass limit, reuses the pinned target and cache-session path, retries
only operational failures with the existing delay, and never sleeps merely to
change phase.

The result and CLI expose phase/pass counts, final horizon, schedule-date
totals, eligibility, source counts, and stop reason. New controls are
`--expand-missing-starts/--no-expand-missing-starts`,
`--expansion-horizon-days`, and `--max-expansion-passes`. Focused verification
passed (`31 passed`), CLI help succeeded, and Ruff passed. Task 5 fail-closed
playable timing integration is next; probability, EV, bank, stake, and package
ranking definitions remain unchanged.

## Multi-Day Eligibility Task 5: Playable Timing Gate Complete

`EVPackageRun` now carries immutable timing provenance. The resolver receives
the exact fresh drawing payload already used for EV input, computes its
canonical target fingerprint, and performs only a read-only exact lookup in
the selected SQLite database. No external probability enters EV input,
surface construction, coupon ranking, or sensitivity math.

Playable output now requires timing status `playable`. `multi_day`, `unknown`,
`absent`, and `not_checked` suppress the package and all displayed sensitivity
decisions to zero-cost `NO BET`, and exact top coupons are not published after
the veto. Research retains coupons and ranking while reporting timing status.
Missing/unreadable databases and unparseable timing targets become conservative
warnings rather than Research failures. `ev-package` adds read-only `--db`.

Focused verification passed (`59 passed`), CLI help and Ruff passed, and the
three independent review findings were re-reviewed as resolved. Task 6
end-to-end acceptance and final documentation are next.

## Multi-Day Drawing Eligibility Complete

The approved six-task implementation is complete. Missing TotoBrief starts are
collected first over two Moscow calendar days and may expand through day five
only after a stable exact-pair miss. Schedule success and failure remain
isolated per date, and every pass persists an immutable 15-event snapshot with
target fingerprint, horizon, provider/effective starts, source, and eligibility.

Historical and Research flows retain multi-day and unresolved drawings for
analysis. Playable EV output requires an exact stored fingerprint match and
`playable` eligibility: all 15 effective starts known within an inclusive
two-day Moscow span. Confirmed multi-day, unresolved, absent, mismatched, and
unchecked timing all produce zero-cost `NO BET` without publishing diagnostic
coupons. External probabilities remain audit-only and do not enter EV or
package ranking.

Deterministic end-to-end acceptance covers ordinary two-day, day-five
expansion, partial provider-date failure, confirmed multi-day, and unresolved
drawings through collection, SQLite reload, audit/report, and playable/research
output. Focused verification passed: 179 tests. Full-suite and Ruff results are
green: 746 tests passed, repository-wide Ruff passed, both affected CLI help
commands succeeded, and `git diff --check` passed.

## Approved Next Design: Safe Drawing Runner

The next production task is a single operator command that performs preflight,
waits until T-20, revalidates the exact pinned drawing, runs fresh prospective
collection, timing eligibility, coverage audit, and the existing EV package,
then publishes a deterministic run manifest. T-5 is a hard fail-closed boundary
for starting new runner phases. The command never places a bet.

This orchestration does not change probability, EV, category, bank, stake,
consensus, coverage-gate, or timing definitions. External consensus remains
audit-only while the prospective gate is below 30 drawings and 450 events.

Design specification:
- `docs/superpowers/specs/2026-07-16-safe-drawing-runner-design.md`

Next action: write the TDD implementation plan after user review of the spec.

## Approved Implementation Plan: Safe Drawing Runner

The implementation is decomposed into six independently reviewed TDD tasks:
immutable timing/domain, pinned collection cutoff, provider-neutral
orchestration, deterministic reports, Typer wiring, and end-to-end acceptance.

Implementation plan:
- `docs/superpowers/plans/2026-07-16-safe-drawing-runner.md`

Next action: execute the plan task by task with review gates.

## Safe Drawing Runner Task 1 Complete

Added the provider-neutral immutable runner domain and UTC timing state machine.
`DrawingRunnerConfig` preserves the existing divisible-bank/stake rules and
playable default, `pin_drawing()` binds a deterministic canonical target
fingerprint, and waiting transitions exactly at T-20 with a fail-closed T-5
boundary. Waiting uses injected clocks and sleepers only, rechecks wall time
after each bounded sleep, and never sleeps through the final-window boundary.

Task 1 verification passed: focused runner tests (`50 passed`), focused Ruff,
full pytest (`796 passed`), full Ruff, and `git diff --check`.
