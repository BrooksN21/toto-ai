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
- Remaining coverage-audit work: no implementation task remains; the
  prospective operator gate is still pending.
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

- Automatic sync
- Open drawing analysis
- Package generation
- Report export
- Reproducible backtests
