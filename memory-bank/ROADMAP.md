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
- On development data, test a hybrid direct package objective that retains a
  high-probability core or explicit probability floor while adding controlled
  diversity. The top-core design and GO/STOP protocol are approved; implementation
  is next. Do not inspect the frozen holdout during this selection.
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

## Phase 7: Production

- Automatic sync
- Open drawing analysis
- Package generation
- Report export
- Reproducible backtests
