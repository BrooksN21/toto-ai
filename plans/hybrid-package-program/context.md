# Hybrid Package Program — factual project context

Collected on 2026-07-22 from the standalone repository
`/Users/turshevr/toto-ai`. This document records existing implementation and
gaps only. It does not approve a design or claim profitability.

## Requested program

The requested direction combines four currently separate concerns:

1. Retain the useful properties of TotoBrief-style brief/cover systems,
   especially explicit category coverage guarantees.
2. Retain the project's exact monetary-EV ranking, but remove the current
   concentration failure where a small set of low-probability outcomes may be
   fixed across the whole package.
3. Add lawful, official sports/statistical evidence to the probability layer;
   today API-Sports is used for identity, schedule and odds collection, not a
   sports-performance model.
4. Make every produced package prospectively auditable after the draw, while
   preserving the morning preparation and evening scheduler workflows.

Automatic account betting is explicitly out of scope. The operator uploads
the published package manually.

## Current end-to-end architecture

### TotoBrief and local history

- `toto_ai.api.client`, `toto_ai.api.rate_limit`, and
  `toto_ai.api.detail_cache` provide the API client, cross-process pacing and
  strict raw-detail cache.
- `toto_ai.collector.sync.Collector` stores drawing summaries, 15 ordered
  events and 15 quote rows in SQLite.
- Core tables are `drawings`, `events`, and `quotes` in
  `toto_ai.db.models`.
- `events.result` and `events.score` hold final outcomes when a refreshed
  drawing-info payload contains them.
- Modern quote rows may contain pool, BK, Pin and normalized triplets, but the
  live EV path currently consumes TotoBrief BK and pool only.

Important result-refresh limitation:

- `Collector.drawing_needs_detail()` considers a drawing current once it has
  15 contiguous events and 15 complete pool/BK quote rows.
- It does not check whether a finished drawing has 15 final results/scores.
- Normal `collect` therefore skips an already structurally complete drawing
  even when final outcomes have not yet been refreshed.
- `sync_drawing_detail(..., force=True)` exists, but there is no dedicated
  post-draw result-refresh command or scheduler.
- The roadmap explicitly records post-run finished-result refresh as future
  work.

### Exact EV package engine

Reusable modules:

- `toto_ai.ev.models`: immutable EV configuration, input, surface, package and
  timing models. A bank must be a positive integer multiple of the stake.
- `toto_ai.ev.prize`: category-fund allocation, BK normalization and
  Jeffreys-smoothed crowd marginals.
- `toto_ai.ev.ternary`: exact full-space computation over all
  `3^15 = 14,348,907` coupons.
- `toto_ai.ev.package`: deterministic full-surface ranking and package
  selection.
- `toto_ai.ev.drawing`: fresh open-drawing input, dynamic effective budget,
  timing veto and sensitivity factors.
- `toto_ai.ev.reports`: exact package CSV/Markdown publication.
- `toto_ai.ev.backtest`: chronological modeled-EV backtest with frozen-holdout
  exclusion and result leakage protections.

Current live EV input and objective:

- `ev_input_from_payload()` sets all 15 probability sources to
  `totobrief_bk`.
- Crowd marginals come from TotoBrief pool percentages with Jeffreys
  smoothing.
- Crowd joint behavior is modeled as independent event marginals. This is a
  disclosed assumption, not observed player-ticket correlation.
- Category funds model hits 9 through 15. The regular-prize proxy uses
  `possible_winnings`; 14/15 also use jackpot shares.
- `build_open_ev_package()` computes exact EV components, materializes prize
  sensitivity surfaces and applies the 1% pool self-dilution cap.
- `select_ev_package_with_top_coupons()` ranks the complete coupon space by
  descending gross EV with deterministic coupon-index tie-breaking.
- Research mode fills capacity. Playable mode keeps coupons at or above the
  configured gross-EV threshold and may return `NO BET`.
- The selected package is not constrained by a brief or category guarantee.
  Its `derived_brief` is only the union of outcomes present in selected
  coupons.
- Modeled payout/ROI are not observed payout/ROI because actual category
  winner counts and bookmaker payouts are not available in the stored history.

Current dynamic-bank behavior:

- Requested bank is configurable and must be divisible by stake (default
  30 RUB).
- Effective budget is the minimum of requested bank, any caller-provided
  selection cap, and the exact 1% pool self-dilution cap rounded down to stake.
- Package capacity is `effective_budget // stake`; full requested-bank use is
  not forced when coupons fail the Playable threshold.

Relevant CLI commands:

- `ev-package --open`
- `backtest-ev`
- `benchmark-ev`

### Brief and Cover Engine

Reusable modules:

- `toto_ai.optimizer.brief`: BK/pool analysis, baseline brief candidates,
  candidate scoring and Cover Engine invocation.
- `toto_ai.optimizer.cover`: Cartesian brief expansion, greedy weighted cover,
  category/error mapping and exact package verification.
- `toto_ai.optimizer.brief_backtest`: historical baseline-brief evaluation.
- `toto_ai.analytics.brief_oracle` and
  `toto_ai.analytics.budget_oracle`: result-aware research upper bounds only;
  neither is a playable predictor.

Exact category semantics:

- category 13: at most two Hamming errors;
- category 14: at most one Hamming error;
- category 15: exact coupon match.

A Cover guarantee is conditional: it applies only when every actual event
outcome lies inside the selected brief. `verify_cover_package()` exhaustively
checks every brief variant and reports the worst minimum distance.

Relevant CLI commands:

- `build-brief --open`
- `cover`
- `verify-cover`
- `backtest-brief`
- `brief-oracle`
- `budget-oracle`
- `benchmark-cover`

### Existing direct and hybrid optimizer work

Reusable modules:

- `toto_ai.optimizer.coupon_probabilities`: normalized BK matrices, coupon log
  probability and exact top-probability enumeration.
- `toto_ai.optimizer.coupon_candidates`: deterministic sampled scenario and
  candidate generation.
- `toto_ai.optimizer.direct_package`: weighted scenario-coverage selection and
  the previous top-core hybrid selector.
- `toto_ai.optimizer.strategy_backtest`: frozen chronological comparison of
  baseline brief, top-probability and weighted coverage.
- `toto_ai.optimizer.strategy_diagnostics`: package diversity, overlap and
  threshold-transition diagnostics.
- `toto_ai.optimizer.hybrid_evaluation`: sealed development-only evaluation,
  fixed folds and deterministic GO/STOP decision.

The existing `select_hybrid_package()` is not the requested EV/Cover/sports
hybrid. It keeps a top-probability prefix, then fills from weighted scenario
coverage. It was evaluated only under a fixed BK-only protocol:

- bank 5000 RUB, stake 30 RUB, category 13;
- core fractions 0.50, 0.75 and 0.90;
- 350 sealed development drawings in five chronological folds;
- final decision `STOP`.

The old hybrids improved average best hits but did not add the pre-registered
two 13+ hits over top-probability. BK-only optimizer tuning was closed. New
optimizer work needs a new hypothesis and an untouched/prospective evaluation
window; it must not reinterpret the old holdout.

Relevant CLI commands:

- `freeze-strategy-experiment`
- `backtest-strategies`
- `diagnose-strategies`
- `seal-hybrid-development`
- `evaluate-hybrid`

### API-Sports and external data

Reusable modules:

- `toto_ai.external_odds.api_sports`: football/hockey schedule and pre-match
  odds transport, parsing, cache, quota and retry handling.
- `domain` and `targets`: provider-neutral target/event/market records.
- `matching`, `team_registry`, `team_resolution`, and `preparation`:
  conservative event identity, reviewed aliases/provider IDs, review queue,
  atomic 15/15 preparation and pins.
- `consensus`: strict football full-time and hockey regulation-time 1/X/2,
  per-book de-vig and median consensus requiring three bookmakers.
- `collection`, `prospective`, and `storage`: immutable 15-disposition
  prospective snapshots with explicit TotoBrief BK fallback.
- `audit` and `reports`: coverage gate and deterministic diagnostics.

Current use boundary:

- API-Sports supplies schedules, fixture/team IDs, event timing and pre-match
  bookmaker odds.
- It does not currently collect or model team form, standings, results,
  lineups, injuries, player availability, goals/xG, shots, home/away splits,
  rest, or strength-of-opposition features.
- External consensus is append-only stored and audited, but remains
  audit-only. It does not replace or blend the `totobrief_bk` probabilities in
  Playable EV generation.
- The prospective activation gate requires at least 30 future drawings and
  450 events, >=80% unique matching, >=70% usable consensus, zero consumed
  ambiguity and explicit disposition for every event.
- Drawing 4952's final manifest recorded only 5 drawings/75 events, 62.67%
  unique match and 61.33% consensus, so the gate was `PENDING`.
- Direct Pinnacle access and prohibited scraping are excluded. Missing lawful
  external data must retain an explicit fallback rather than silently drop an
  event.

Relevant CLI commands:

- `collect-external-odds --open`
- `audit-external-coverage`
- `prepare-drawing`
- `sync-prepare`

### Morning preparation and evening scheduler

Reusable modules:

- `toto_ai.operations.sync_prepare`: one page-one synchronization, exact
  cache/network detail persistence and systematic preparation.
- `toto_ai.runner.models`, `timing`, `orchestration`, and `reports`: exact
  target pinning, T-20/T-5 runner boundary, manifest schema v4 and transactional
  report publication.
- `toto_ai.runner.scheduler`: immutable scheduler plan, preflight/fallback/
  final/freeze execution, strict runner-manifest ingestion and terminal
  markers.

Evening schedule is anchored to TotoBrief `ended_at`:

- T-45: preflight and mandatory systematic preparation;
- T-30: diagnostic fallback package;
- T-15: final fresh package;
- T-10: freeze and publish only a valid final package.

Only `.bet-ready` is actionable. `.no-bet` and `.failed` are fail-closed.
Fallback is never promoted after final failure. The operator manually uploads
the final package; no account automation exists or is planned.

Morning preanalysis is separate. `morning-preanalysis-plan` generates a
launchd candidate that runs guarded `sync-prepare --open
--expected-drawing-number N` at configured morning times with bounded retries.
It synchronizes/prepares but cannot create betting markers.

Drawing-4952 scheduler incident and fix:

- The original launchd wrapper lacked a project working directory and
  preflight used a new empty run cache instead of warmed project caches.
- Local commit `a4aa2262daa8d45cd2dd5eabc4860f3c3802b750` adds scheduler plan schema v2,
  absolute `project_root`, wrapper `cd`, plist `WorkingDirectory`, subprocess
  `cwd`, absolute shared preflight raw/API-Sports caches, and retains isolated
  fallback/final caches.
- Root/path/symlink containment is validated.
- A real regression launches preflight from `cwd=/`, forbids HTTP and consumes
  warmed local caches.
- Commit verification recorded 1208 passing tests, Ruff clean and
  `git diff --check` clean.
- Existing installed launchd artifacts are not automatically migrated; they
  must be regenerated/reinstalled explicitly.

Relevant CLI commands:

- `run-drawing --open`
- `scheduler-plan`
- `scheduler-execute`
- `morning-preanalysis-plan`
- `sync-prepare --open --expected-drawing-number N`

## Final drawing 4952 package: verified local findings

Inspected artifacts:

- `reports/rehearsal/evening-4952/emergency-final/ev_package_4952_playable_bank_4980.csv`
- corresponding Markdown report and runner manifest
- BaltBet text export `baltbet_package_4952_4980.txt`

Facts:

- final snapshot fetched at `2026-07-22T15:46:17.560775+00:00`;
- decision `PLAY` under the current model;
- requested/effective/used bank 4980 RUB;
- 166 unique direct EV-ranked coupons at 30 RUB each;
- probability source for every event: `totobrief_bk`;
- crowd source: TotoBrief pool marginals under event independence;
- package was not generated as category 13, 14 or 15 Cover system;
- union brief:
  `2,1X2,1X2,1X2,2,1X,X2,2,1X,X2,1X,1X2,X2,2,1`;
- union brief size: 5184 variants;
- fixed package outcomes: event 1=`2`, event 5=`2`, event 8=`2`, event
  14=`2`, event 15=`1`;
- event 12 distribution: `1` in 163 coupons, `X` in 2, `2` in 1;
- exact verification against the union brief:
  - category 15 covers 166/5184 variants, guarantee false;
  - category 14 covers 992/5184 variants, guarantee false;
  - category 13 covers 2600/5184 variants, guarantee false;
  - worst minimum Hamming distance is 6.

The fixed/near-fixed outcomes arose from global monetary-EV ranking, where a
less popular pool outcome may outrank a more probable outcome because modeled
winner dilution is lower. They are not declarations of high sporting
confidence. This concentration is the concrete failure mode the new hybrid
program must measure and address.

The final report's modeled ROI is extremely high, but it is generated from the
pool-size prize proxy and independent crowd-ticket model. It is not observed
profitability evidence.

## Existing archival, backtest and audit evidence

What exists:

- deterministic package CSV/Markdown and runner JSON/Markdown files;
- immutable run-scoped scheduler snapshots and status/terminal markers;
- external-odds append-only collections in SQLite;
- modeled EV backtest checkpoints with exact package coupon manifests and
  package hashes;
- historical strategy experiment manifests and development seals;
- actual-result evaluation inside retrospective backtests after pre-result
  package hashes are fixed.

What does not exist:

- a production/prospective package ledger table binding every morning/final
  package to input snapshots, algorithm/config version, costs and operator
  placement status;
- an automatic post-draw result-refresh workflow;
- a settlement record for every produced package (best hits, 9..15 category,
  winning coupon, actual payout, stake return and observed ROI);
- a scheduler phase after draw completion;
- an immutable comparison of morning, fallback and final packages against the
  same actual result;
- an observed payout source. Current data can calculate hits/categories after
  result sync but not actual monetary profit unless payout is sourced lawfully
  or entered by the operator.

## Critical missing pieces for the requested program

1. **Probability-source boundary**
   - Define one event-level probability interface with explicit source,
     timestamp, provenance, fallback and calibration status.
   - Preserve TotoBrief BK as a strong baseline/fallback.
   - External odds and future sports statistics must not silently alter PLAY
     until tested on untouched/prospective data.

2. **Official sports-statistics subsystem**
   - No such feature store/model exists today.
   - A lawful source and exact pre-match availability contract are required.
   - Football and hockey require separate feature definitions/models.
   - Missing features must be explicit; no guessed injuries, lineups or xG.
   - Time-based validation, calibration, log loss/Brier score and leakage tests
     are required before blending with market probabilities.

3. **New hybrid package objective**
   - Existing hybrid is top-probability plus weighted coverage and already
     returned STOP under BK-only category-13 evaluation.
   - The new hypothesis must combine monetary EV, probability of 9+/13+/14+,
     conditional Cover guarantees and concentration/diversity constraints.
   - Cover guarantees and direct-EV packages must remain separately labelled;
     a derived union brief is not a Cover guarantee.
   - Dynamic bank/stake behavior and honest `NO BET` must remain unchanged.
   - No search-space reduction may be introduced merely to make runs faster
     unless equivalence/quality impact is measured.

4. **Comparison protocol**
   - For every eligible draw compare at least: direct EV, true Cover/brief,
     top-probability baseline and the proposed hybrid under the same bank.
   - Report package overlap, event outcome frequencies, concentration, exact
     conditional category coverage, modeled 9+/13+/14+/15 probabilities,
     modeled EV, cost and runtime.
   - Use a new untouched/prospective evaluation window; do not tune on the old
     150-drawing holdout.

5. **Prospective package ledger and post-draw settlement**
   - Persist each generated package before results are available with hashes of
     exact coupons, inputs, probabilities, pool snapshot, algorithm/config and
     scheduler phase.
   - Add forced/idempotent finished-result synchronization after the draw.
   - Settle all archived morning/fallback/final/recommended packages against
     the exact 15 outcomes.
   - Record best hits, category counts and observed payout/ROI only when actual
     payout data is present; otherwise mark monetary settlement unavailable.
   - Never overwrite a historical package or result assessment.

6. **Operational integration**
   - Morning preparation should also collect/freeze the lawful pre-match data
     needed for later comparison, without publishing a bet.
   - T-15 final generation must use fresh, fully provenance-bound inputs.
   - T-10 publication remains the manual-upload deadline and must fail closed.
   - Add a separate post-draw scheduler/job for result refresh and settlement;
     it must not interfere with the next drawing's morning/evening jobs.
   - Multi-day/unknown drawings remain non-playable but may remain in research
     and historical feature data.

## Critical constraints that downstream planning must preserve

- Work only inside this standalone repository; project memory is only
  `memory-bank/`.
- No automatic BaltBet bet submission.
- No profit or guarantee claim without evidence.
- A TotoBrief category guarantee is conditional on actual outcomes being
  inside the selected brief.
- Market/BK probability quality and package-cover quality are separate.
- Dynamic bank is any positive stake-multiple; 4980 RUB is an operational
  starting choice, not a hard-coded product limit.
- External consensus currently remains audit-only because its gate is pending.
- Direct Pinnacle scraping is out of scope.
- Fifteen exact events, identity pins, timing eligibility and final 15/15
  provider revalidation remain mandatory for PLAY.
- Confirmed multi-day or unresolved timing remains `NO BET`.
- Preserve deterministic reports, hashes, atomic publication and fail-closed
  scheduler markers.
- Every new hypothesis needs tests plus chronological/untouched or prospective
  evaluation before it can affect recommendations.

## High-value existing tests to reuse

- EV exactness/ranking/budget: `tests/test_ev_ternary.py`,
  `test_ev_reference.py`, `test_ev_package.py`, `test_ev_backtest.py`, and
  `test_ev_end_to_end.py`.
- Cover/category guarantees: `tests/test_cover_engine.py` and
  `test_cover_verifier.py`.
- Baseline/direct/hybrid evaluation and leakage: `test_brief_generator.py`,
  `test_strategy_backtest.py`, `test_strategy_diagnostics.py`,
  `test_hybrid_package.py`, and `test_hybrid_evaluation.py`.
- External identity/probability provenance: external odds collection,
  consensus, storage, prospective and end-to-end test files.
- Scheduler/morning/launchd safety: `test_runner_scheduler.py`,
  `test_scheduler_operational_artifacts.py`, `test_runner_end_to_end.py`, and
  sync-prepare tests.
- Result-refresh behavior currently has no dedicated post-draw/settlement test
  suite; this is a new required boundary.
