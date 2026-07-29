# Roadmap

## Scheduler operational remediation

- [x] Add drawing-4959 contextual API-Sports identities for Gimnasia L.P.
  (434) and River Plate (435), reject domestic/global-friendly crossover, and
  retain Iceland 3. Deild as an explicit source-missing non-match.
- [x] One immutable final snapshot and canonical probability binding.
- [x] Independent T−45/T−30/T−20/T−16/T−12 ticks and zero-cost `NO BET`.
- [x] Dynamic drawing-neutral morning dispatcher.
- [x] Persist generated state before activation and safely reuse exact
  artifacts after bootstrap failure or process interruption.
- [x] Reuse one per-drawing plan across a permitted two-day drawing.
- [x] Typed/status-based retry classification; no message substring matching.
- [x] Reject incompatible production `--run-id`, preserve schema-v3 root, use
  correct T−12 diagnostics, and blanket-ignore generated reports.
- [x] Reacquire time after morning/preflight network preparation and block
  post-preparation plan generation at or after T−45.
- [x] Record final snapshot capture at detail-response completion.
- [x] Remove stale actionable package/archive files on late recovery to
  zero-cost `NO BET`.
- [x] Enforce the actionable cutoff for final calculation completion,
  recomputed subprocess timeouts, and every retry admission.
- [x] Reserve the remaining interval through hard T−12 exclusively for
  package/archive-manifest writing, durable archive, recovery, status, and
  marker publication; allow recovery through T−12 and fail closed after it.
- [x] Current verification: five exact reserve boundaries, 175 focused
  scheduler/morning tests, 1443 full tests, Ruff, and diff check.
- [ ] Add a lawful provider-neutral schedule fallback for events absent from
  API-Sports; drawing 4958 women event 5 and drawing 4959 Iceland 3. Deild
  event 9 are current real examples. Official KSÍ and an independent public
  source confirm the latter fixture, but reviewed web evidence is not yet a
  provider pin and must not be injected as an API-Sports fixture.
- [x] Run drawing-4959 activation-disabled morning drill: 14 safe candidates,
  one explicit source-missing event, zero partial pins, no evening plan,
  package, marker, activation, or bet.
- [x] Run a schema-v4 five-trigger network-free simulation after the
  2026-07-29 scheduler fixes.
- [x] Split generic morning automation into passive default and explicit
  post-drill `--activate-evening` mode; full verification is `1444 passed`,
  with Ruff and diff checks green.
- [x] Install and verify the passive generic morning dispatcher at
  08:00/10:30 Moscow time; its installed wrapper contains neither `--activate`
  nor a drawing number. Manual launchd execution completed three bounded,
  consistent 4959 deferrals without an evening plan/package/marker.
- [ ] Repeat an activation-disabled 15/15 live drill.
- [ ] Enable automatic evening activation only after that drill passes.

## Sports statistics milestone

- [x] Provider-neutral immutable football contracts and validators.
- [x] Append-only run/event persistence and as-of lookup.
- [x] Existing-transport API-Sports adapter and strict no-future filtering.
- [x] Recent form/home-away/rest/standings feature builder.
- [x] Audit-only CLI and JSON/CSV/Markdown reports.
- [x] Prospective acceptance run on drawing 4957.
- [x] Independent-review hardening: strict network-free historical replay,
  nullable unknown windows, actual standings capability parsing, full
  run/event identity validation, unrelated-team rejection, deterministic
  reports, legacy-DB initialization, package/PLAY isolation tests, and safe
  reuse of a frozen prospective `last=10` history cache by historical
  `from/to` replay with strict as-of and local fixture cutoffs.
- [ ] Select a lawful source with current-season history/standings coverage.
- [ ] Accumulate at least 30 frozen drawings / 450 events with material
  non-fallback sports coverage.
- [ ] Run chronological out-of-sample sports-only and capped-blend evaluation
  against bookmaker log loss, Brier, calibration, and coverage.
- [ ] Consider a capped bookmaker/sports blend only after a frozen
  no-degradation gate passes.

The API-Sports free-plan result is a provider limitation, not a reason to
weaken the as-of contract or substitute old-season/currently fetched data.
Until a suitable source is selected, `p_final = p_market`.

## Hybrid Package Program — Milestone 1 complete

The ordered program is defined in
`plans/hybrid-package-program/plan.md`. Its goal is to compare and eventually
operate three explicitly different strategies for every eligible drawing under
the same dynamic bank: true conditional **Cover**, exact modeled **EV**, and a
calibrated/concentration-controlled **Hybrid**. No strategy claims profit.

Ordered vertical milestones:

1. **COMPLETE:** Package strategy metadata and deterministic
   concentration/Hamming/coverage audit with schema-v1 JSON/CSV/Markdown,
   `package-audit`, independent exact streaming distance, dynamic banks,
   canonical hashes, probability-aware warnings, and the independently
   verified drawing-4952 acceptance reproduction. Acceptance: focused
   `88 passed`, full `1269 passed`, Ruff passed, `git diff --check` passed,
   real drawing-4952 audit verified, and all P1/P2 findings closed.
2. True probability-aware Cover strategy with exact verification and a common
   EV/Cover comparison.
3. **IN PROGRESS:** Append-only prospective package archive, forced post-draw
   result refresh, settlement, and expected-vs-actual ledger. Explicit
   finished-result sync, immutable package/result/settlement evidence, bounded
   retries, reviewed VOID-event settlement, and the short fail-closed
   active-detail freshness boundary are implemented. Mandatory production
   scheduler integration and complete official payout evidence remain.
4. Provider-neutral lawful sports-statistics collection, morning cache,
   historical backfill, and canonical football/hockey feature snapshots.
5. Chronologically evaluated and calibrated market/sports probability blend;
   market remains prior/fallback and sports influence remains audit-only until
   frozen gates pass.
6. Hybrid optimizer combining category-hit probability, Cover/Hamming
   coverage, modeled EV, and explicit diversity/concentration constraints.
7. Morning and evening three-strategy scheduler integration with dynamic
   stake-multiple banks and manual package upload only.
8. Separate bounded post-draw scheduler that refreshes results/payout evidence,
   settles every archived package, and surfaces missing data.

The first slice reproduces the known drawing-4952 package audit
(`EV`, 166 coupons, fixed events 1/5/8/14/15, event-12 frequency 163/2/1,
union brief 5184, no 13/14/15 guarantee, worst distance 6) before Cover or
Hybrid selection is changed.

Future/not implemented milestones include actual Hybrid package
selection/optimization; an official/reputable sports-statistics probability
model with calibrated integration; mandatory post-draw result refresh,
settlement, and payout/profit/ROI ledger; and morning/evening/post-draw
scheduler integration for the unified Cover/EV/Hybrid lifecycle. True
probability-aware Cover generation and common EV/Cover comparison are also
future work. Completion of the audit foundation is not evidence of
profitability or a proven winning strategy.

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
- Atomic-final scheduler remediation is complete: canonical zero-cost
  `NO BET`, immutable one-fetch final detail, snapshot-fed preparation/EV,
  plan-v4 five-trigger ticks, persistent restart/concurrency state, bounded
  retry, T−12 cutoff, runner manifest v5, and archive manifest v2 provenance
  are implemented and fixture-tested. Terminal `bet_ready` is committed only
  after marker success; marker failures stay package-free/failed, archive
  recovery rechecks current timing overrides, and activation retry verifies
  exact plan/wrapper/plist bytes. Generated LaunchAgent candidates remain
  uninstalled; a bounded operator-controlled drill is still required before
  any manual installation.
- Dynamic morning dispatcher implementation is complete: the recurring
  candidate contains no drawing number, pins one fresh exact drawing, retries
  deferred preparation idempotently, and creates one per-drawing schema-v4
  evening plan only before T−45. The five known obsolete LaunchAgents were
  removed and follow-up inspection found none installed or loaded.
- Next operational gate: run an activation-disabled morning plus atomic-final
  drill on drawing 4958, inspect exact identity/readiness, all due ticks,
  immutable final-input provenance, terminal decision, and absence of automatic
  betting. Do not install any scheduler until this drill succeeds.
- Emergency pre-bet safety slice is complete: production-playable packages
  fail closed on configured concentration/fixed-low-probability/material-
  outcome exposure checks, 4952 is rejected before upload, and morning
  preparation requires fresh playable 15/15 evidence. The earlier actionable
  schema-v3/T-10 contract remains historical compatibility; production
  schema-v4 now requires durable package archival plus post-archive/pre-marker
  T−12 checks before `.bet-ready`.
  Result synchronization, settlement, payout/ROI persistence, and a post-draw
  retry scheduler remain pending.
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
  recovery/backfill path. Explicit finished-result refresh, package archive,
  immutable settlement, and bounded non-betting retry are implemented.
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
- Automatic T−12 publication scheduling of the fresh prospective command
- Open drawing analysis
- Package generation
- Report export
- Reproducible backtests
