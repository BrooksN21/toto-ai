# Roadmap

## Phase 1: Infrastructure - completed

- API client
- Historical collector
- SQLite storage
- Audit
- API inspector
- Validation suite
- Persistent project knowledge base

## Phase 2: MVP - completed

- Cover Engine
- Exact cover verifier
- Baseline brief generator
- Current/open drawing selection
- CSV exports

## Phase 3: Baseline evaluation - in progress

- Backtest baseline brief generator on 100/500/1000 completed drawings.
  - Backtest CLI and report export are implemented.
- Measure brief containment.
- Measure package best hits.
- Measure 13/14/15 hit rates.
- Measure average cost.
- Compare category 13 vs 14.
- Compare different budgets.
- Compare against simple baselines.
- Use `budget-oracle` to estimate the gap between baseline generation and an
  oracle package under the same budget.
- Use budget-oracle progress, timeout, and timing diagnostics for longer
  baseline/oracle comparison runs.
- Use `budget-oracle --profile-workload` to inspect generated/unique candidate
  counts, Cover Engine calls, cache hits/misses, brief variant sizes, and
  slowest candidate briefs before changing search strategy.
- Budget Oracle retains pruning diagnostics, but unsafe dominance and
  full-cover cost pruning are disabled.
- Implement the approved Direct Package Optimizer experiment and compare
  `baseline_brief`, `top_probability`, and `weighted_coverage` on a chronological
  development/holdout split. Completed for a frozen retrospective 500-drawing
  experiment with 350 development and 150 holdout drawings.
- Use 5000 RUB as the primary bank and 3000/10000 RUB as sensitivity checks.
- Diagnose the weighted-coverage objective on development data: it improved
  average best hits but did not improve development 13+ frequency over
  top-probability. Completed on all 350 frozen development drawings.
- Implement deterministic package structure and overlap metrics for development
  strategy diagnostics. Completed.
- Add a fail-closed development diagnostics CLI that regenerates packages,
  verifies frozen package hashes/results, and exports deterministic reports.
  Completed.
- Hybrid Direct Package experiment Tasks 1-5 are completed: selector, GO/STOP
  model, fail-closed evaluator, atomic reports/CLI, and sealed development run.
  The final decision is STOP: no hybrid added the required two 13+ hits over
  top-probability. Total 13+ counts for top/0.50/0.75/0.90 were 6/4/5/6;
  per-fold counts were 0/0/0/0, 0/0/0/0, 1/0/0/1, 1/1/1/1, and 4/3/4/4.
  Average best hits were 8.691429/9.491429/9.288571/9.060000, with zero
  operational failures. The sealed rerun exactly reproduced these metrics with
  zero holdout-ID overlap and zero timeouts. BK-only optimizer tuning is closed.
- Harden the hybrid development boundary with a reproducible development-only
  seal and separate canonical CSV, pre-drawing input, result, and protocol
  hashes, plus clean-code binding and rollback-safe artifact publication.
  Completed without changing strategies, folds, budgets, categories, or
  GO/STOP criteria.
- Extend the hybrid deadline across all package-generation stages and skip
  post-timeout exact coverage work. Completed.
- Reserve a new untouched or prospective evaluation window before claiming an
  improvement from further optimizer tuning.

## Phase 4: Research

- Bookmaker calibration
- Brief oracle research
- Budget-constrained brief oracle
- Pool calibration
- Crowd calibration
- Pool vs BK bias
- Draw underestimation
- Favorite overestimation
- Position streak hypotheses
- League effects
- Entropy and uncertainty
- Cancelled/missing-result handling

## Phase 5: Probability Model

- Direct Pinnacle access is unavailable for this project; prohibited scraping
  is excluded.
- Evaluate lawful third-party feeds, starting with API-Sports football/hockey,
  for coverage, terms, freshness, historical availability, and event matching.
- API-Sports coverage-audit Tasks 1-6 are complete: provider-neutral records,
  API-Sports transport/cache/quota, strict deterministic fail-closed event
  matching with reviewed alias diagnostics, and strict three-way
  market-semantics consensus with explicit fallback, plus append-only
  prospective storage and deterministic 15-event collection with explicit
  TotoBrief BK fallback. Task 5 storage is review-hardened with identity-bound
  schedule/market fetch provenance, canonical quote ordering, and deterministic
  duplicate-key anomaly coalescing under the unchanged uniqueness constraint.
  Task 6 adds read-only stored-snapshot coverage auditing, deterministic atomic
  CSV/Markdown reports, `collect-external-odds`, and
  `audit-external-coverage`. Task 6 review hardening completes the aggregate and
  per-scope report schema, exact fallback classification, bookmaker-threshold
  diagnostics, and dedicated report atomicity/determinism coverage. Task 7
  adds end-to-end fail-closed acceptance for success/mixed/failure/quota/
  interruption paths, report evidence, EV non-interference, and API-key absence
  across persistence, cache, CLI, exception chains, and reports.
- Final whole-branch review fixes are complete for the coverage-audit branch:
  consensus now uses an external observation clock distinct from TotoBrief
  target provenance; official item-level API-Sports odds updates are parsed as
  bookmaker defaults; schedules and odds fetch all pages fail-closed; market
  outcomes reject duplicate or unknown labels before provider-neutral records;
  and actual HTTP attempts are reported separately from cache hits.
- Live-contract hardening is complete for the first authorized API-Sports run:
  unpaged schedule requests, official odds items without teams/top-level
  timestamps, numeric non-three-way labels, cache observation timestamps,
  daily/minute quota semantics, stale-cache quota isolation, and TotoBrief
  `start_at=null` matching are covered by regression tests.
- Matcher v3 reversed-pair mapping is complete and live-verified on drawing
  4945: 13/15 unique exact matches and usable consensuses, two explicit
  fallbacks, two recorded reversed orientations, and zero ambiguous matches.
  Consensus `1`/`2` is swapped only for reversed pairs; raw prices are retained.
- Fresh prospective orchestration is complete: one target is pinned, isolated
  run caches prevent stale observations, and approved operational fallbacks are
  retried across the API-Sports minute reset. The final live drawing-4945 T-15
  run finished in two passes and 69.04 seconds with 13/15 consensuses, leaving
  13 minutes 50 seconds before the betting deadline.
- Remaining coverage-audit work: collect the prospective sample. The operator
  gate remains `PENDING` below 30 drawings and 450 events; external consensus
  still has no `PLAY` impact.
- Run the free-tier prospective gate on at least 30 future drawings and 450
  events before external probabilities can influence package generation.
- Test a second free provider when the gate fails for missing coverage; consider
  a paid plan up to 30 USD/month only when quota is the measured blocker.
- Add a provider-neutral, event-level probability interface with explicit
  TotoBrief BK fallback and prospective odds storage.
- Feature builder
- Train/validation/test split by time
- Calibration
- Log loss, Brier score, ROC-AUC where appropriate
- Avoid data leakage

## Phase 6: Package Optimizer

- Cover Engine performance optimization for greedy cover is implemented.
- Direct Package Optimizer design is approved; v1 targets holdout `13+` rate
  directly with BK probabilities and a 5000 RUB bank. V1 and its frozen
  retrospective comparison are implemented; no statistically proven winner was
  found.
- Safe Budget Oracle optimization remains open. Any future pruning must match
  exhaustive evaluation in regression tests.
- Compare greedy cover, MILP, simulated annealing, genetic algorithms.
- Optimize expected value and probability of 13+/14+/15.
- Monte Carlo simulation.
- Implement the approved Expected-Value Package Engine in the sequence defined
  by `docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md`:
  pure payout/reference math, exact ternary full-space engine, dynamic-bank
  research/playable selection, reports/CLI, then chronological evaluation.
- Chronological modeled-EV evaluation is implemented with frozen-holdout
  exclusion before event queries, pre-result package hashing, reusable complete
  factor rankings, dynamic banks/thresholds, resumable exact-config checkpoints,
  realized 9..15 indicators, deterministic reports, and `backtest-ev`.
- Task 6 integrity hardening is complete: latest-N result-complete backfilling,
  diagnostic-only skip re-evaluation, exact checkpoint Cartesian grids and row
  invariants, SQL projection leakage tests, live-compatible 1% self-dilution
  suppression, and configuration-hash-scoped final/checkpoint artifacts.
- Task 6 checkpoint package integrity is complete: SQL parameter scoping covers
  every Event/Quote query, and checkpoint-only canonical coupon manifests make
  package hashes exactly verifiable while rejecting missing, duplicate, orphan,
  conflicting, or tampered package records.
- Task 6 row binding is complete: SQL scope checks derive drawing IDs from
  explicit Event/Quote predicates, and canonical per-manifest row references
  reject swapped equal-count hashes plus duplicate, missing, extra, or unsorted
  checkpoint contexts.
- End-to-end EV acceptance is complete: tests cover honest `NO BET`, dynamic
  bank caps, deterministic reports, interruption safety, and the small oracle
  guard. The mandatory benchmark evaluated all `3^15 = 14,348,907` coupons
  without truncation and independently verified 20 samples with `PASS`.
- Playable gross-EV thresholds 0.90, 0.95, 1.00, and 1.05 are covered by package
  and chronological backtest tests, including bank utilization and `NO BET`.

## Phase 7: Production
- Drawing-4952 launchd incident remediation is implemented: scheduler plan v2
  binds an absolute project root, wrapper/plist/subprocess working directories
  agree, preflight reuses absolute warmed preparation caches, and package
  phases retain isolated caches. A real cache-only preflight regression starts
  from `cwd=/` with HTTP prohibited. Existing installed launchd jobs are not
  modified automatically and require explicit artifact regeneration/install.
- Scheduler operational contracts are implemented but not installed:
  - scheduler-generated `run-drawing` argv carries the configured finite
    `--min-gross-ev` threshold;
  - generated wrappers may securely source a user-owned `0600` env file while
    plists remain secret-free and wrapper-only;
  - `sync-prepare --expected-drawing-number` prevents a stale still-open draw
    from being prepared for the next scheduled target;
  - a separate morning preanalysis wrapper/plist generator supports multiple
    times and retries beneath `reports/rehearsal` without betting markers.
- Systematic team-resolution Phase 2 is implemented:
  - context-aware reviewed team registry and backward-compatible migration;
  - conservative oriented candidate resolution with review-queue fallback;
  - atomic 15/15 drawing preparation and exact immutable pins;
  - progressive per-date schedule preparation with isolated failures;
  - scheduler preparation preflight and default pin-based final execution;
  - recent provider fixture/team/start revalidation without display-name
    rematching;
  - production-derived sport/country/competition/league context, including
    fail-closed competition-level conflicts and shared Russian/English/ISO
    country-identity normalization;
  - progressive preparation resolves after each successful date and stops at
    playable unique 15/15; unresolved attempts exhaust the configured horizon,
    while any attempted pre-readiness date failure publishes zero pins;
  - runner/manifest schema v4 authoritative 15/15 revalidation summaries and
    scheduler `.no-bet` enforcement before EV/actionable publication;
  - offline 4951 replay, prior-drawing regressions, unseen-team coverage, and
    scheduler-to-bet-ready/fail-closed acceptance.
  - official deterministic `run-drawing --offline-replay` path through real
    preparation, pins, cached 15/15 revalidation, runner, and manifest v4;
    strict cache hashes/identity, injected replay clock, research-only output,
    and scheduler-marker prohibition are covered by CLI acceptance tests.
  - replay safety hardening requires one isolated `--replay-root`, derives all
    mutable state beneath it, rejects live-root/symlink/output escape before
    writes, and makes scheduler replay ingestion marker-free `ignored` while
    retaining `.failed` for malformed live production manifests.
- The legacy name matcher remains compatibility-only through explicit direct
  opt-in. It is not a scheduler/final fallback and its global thresholds were
  not weakened.
- Drawing-4950 production-boundary update (no live bet):
  - 7/15 raw matching, reviewed-alias correction to 13/15, and strict reviewed-timing overrides are now documented for operational use.
  - Scheduler and runner output boundary remains strict fail-closed: only `bet-ready` at T-10 publishes an actionable package, while missing timing or catalog mismatches remain `no-bet`; terminal marker also includes `failed`.
  - Runner/reporting boundary now records `schema_version = 4`: v3
    raw/effective timing and budget provenance plus mandatory pinned schedule
    freshness/identity revalidation evidence.
  - Old `schema_version = 2` `drawing_4947` and `drawing_4950` reports remain historical and are excluded from current status.
  - Live platform install and first prospective live production run are pending.


- Automatic incremental TotoBrief morning synchronization is implemented:
  page-one status updates commit independently, exact detail synchronization
  is cache-aware/resumable, all normal request paths share cross-process
  pacing/retry state, and `sync-prepare --open` reaches systematic preparation
  without a duplicate detail request. The path now has strict page-one-only
  selection, server-authoritative Retry-After state, mandatory sidecar/torn
  cache rejection, exact 15-event validation, safe local roots, and a
  `--sync-only` diagnostic mode. Full historical `collect` remains the
  recovery/backfill path. A post-run finished-result refresh remains future
  operational work.
- Drawing 4950 early-run hardening is complete: immutable collection identity
  now includes request/cache/quota provenance, preventing retry passes with the
  same provider content from conflicting in storage. The early 7/15 coverage
  is explained by the API-Sports free-plan date window rejecting 2026-07-21;
  repeat the final collection after that date enters the provider window.
- The first scheduled run on drawing 4947 exposed an acceptance gap: the
  exact-only matcher could not bridge new Cyrillic names when both `start_at`
  and `name_en` were null, despite all 15 pairs existing in the provider
  schedule. Matcher v4 remediation and raw replay regressions for drawings
  4947 and 4945 are complete. Future matching releases require an unseen-team
  raw replay plus a prior-drawing false-positive regression; synthetic
  fail-closed tests alone are insufficient.
- Safe Drawing Runner implementation and corrective verification are complete:
  immediate protected preflight, exact target binding, T-20 final start, strict
  in-pass T-5 provider cutoff, audit/eligibility/EV orchestration, and
  transactional run artifacts without automatic bet placement. Independent
  whole-feature review is approved with no remaining findings.
- Safe Drawing Runner Task 3 orchestration is complete. The injected state
  machine rechecks the inclusive T-5 cutoff after each bound-phase progress
  notification, validates a terminal result before emitting `complete`, and
  keeps coverage `GO`/`PENDING`/`STOP` diagnostic-only.
- Safe Drawing Runner Task 4 deterministic reports are complete and
  review-hardened. Terminal results retain the actually observed final target
  fingerprint, including mismatch and unresolved-final states, and report-pair
  transactions precompute and exclusively create every temp/backup path before
  writes so interruptions cannot leak artifacts.
- Safe Drawing Runner Task 5 production Typer wiring is complete. `run-drawing`
  validates the approved configuration before API-Sports access, uses fresh
  pinned collection, exact timing, latest-30 diagnostic audit, existing EV and
  report writers, and publishes linked runner artifacts without automatic
  betting. Review hardening rejects page-one/drawing-info ID mismatches,
  detaches sanitized provider failures from secret-bearing exception graphs,
  and closes the owned CLI acceptance gaps.
- Safe Drawing Runner whole-feature review corrections are implemented,
  verified, and independently approved. Fake-clock and real
  CLI acceptance cover in-pass schedule/market/page/retry cutoff, second-fetch
  target mutation, post-complete/publication cutoff, computed-`NO BET` coupon
  suppression, all-artifact rollback, path aliases, unwritable roots, and
  publication TOCTOU. The 30-drawing/450-event coverage gate remains `PENDING`
  and external probabilities remain audit-only. Runner manifest schema v2 is
  still the first structured computed/suppressed `ev` contract; schema v1
  retains its historical `ev: null` representation when EV did not run.

- Task 1 complete: provider-neutral drawing eligibility classifier and
  deterministic target fingerprint, including immutable effective starts,
  Moscow calendar-span classification, and fail-closed invariants.
- Task 2 complete: deterministic per-date schedule collection/provenance,
  date-local failure isolation, quota-stop suppression of market requests,
  effective starts, and immutable eligibility-bound collection identity.
- Task 3 is complete: additive legacy-safe persistence, exact
  drawing/fingerprint eligibility lookup, and deterministic audit/report
  evidence with separate ordinary, expanded, multi-day, and unknown scopes.
  The existing overall coverage gate remains unchanged.
- Task 4 is complete: fresh collection now uses bounded base retries at a
  two-day horizon and an independent, cache-reusing expansion phase through
  day five only for stable null-start exact-pair misses.
- Task 5 is complete: playable EV output requires exact fresh-target timing
  eligibility with status `playable`; all other statuses produce a zero-cost
  `NO BET`. Research math and ranking remain unchanged.
- Task 6 is complete: deterministic acceptance covers ordinary two-day,
  day-five expansion, partial-date failure, confirmed multi-day, and unresolved
  drawings across collection, persistence, audit/report, and playable/research
  output. The multi-day eligibility feature is complete.
- Automatic T-15 scheduling of the fresh prospective command
- Open drawing analysis
- Package generation
- Report export
- Reproducible backtests
