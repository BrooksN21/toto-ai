# 4988 postmortem and 4989 package-improvement plan

## Goal

Replace the current EV/crowd-only package path with an auditable equal-input
comparison that prioritizes the chance of category hits, while keeping all
claims paper-only until prospective evidence exists.

## Phase 1 — close drawing 4988

- [x] Synchronize the complete TotoBrief result snapshot.
- [x] Settle the archived 166-coupon package.
- [x] Record hit distribution, event exposure, BK ranks, and immutable hashes.
- [x] Compare EV/crowd with BK-only, Cover-13, Cover-14, and a preliminary
  Cover-14/BK-fill construction.

## Phase 2 — protect drawing 4989

- [x] Keep passive schedule retries active while five kickoff times remain
  unresolved.
- [ ] Reach 15/15 independently verified kickoff evidence and activate the
  identity-bound evening scheduler.
- [ ] Freeze one final input at the operational T-25 checkpoint.
- [ ] Generate, from those same bytes and the dynamic 4,980 RUB bank:
  `EV_CROWD_CURRENT`, `BK_PROBABILITY_ONLY`, and `COVER_14_BK_FILL`.
- [ ] Publish all three only as clearly labelled research candidates; never
  substitute a stale or non-scheduler package.
- [ ] Record exact package hashes and modeled category probabilities before the
  draw result is known.

## Phase 3 — implement the challenger

- [ ] Add `COVER_14_BK_FILL` as a deterministic strategy adapter.
- [ ] Preserve the independently verified Cover-14 subset.
- [ ] Fill remaining dynamic bank capacity with unique BK top-probability
  coupons.
- [ ] Add schema-7/8-compatible equal-input comparison and report generation.
- [ ] Add tests for uniqueness, cost, cover-subset preservation, deterministic
  hashes, dynamic bank handling, and exact category probabilities.

## Phase 4 — automated post-draw learning

- [ ] After every completed drawing, force result synchronization and settle
  every frozen package.
- [ ] Report best/mean hit distribution, 9+/13+/14+/15, exposure of actual
  outcomes, probability rank, fixed misses, and missing payout evidence.
- [ ] Append paired strategy deltas to a prospective ledger.
- [ ] Never select or tune a strategy on the same rows used for evaluation.

## Phase 5 — probability improvement

- [ ] Keep BK as the market prior and fallback.
- [ ] Measure sports-source coverage and as-of correctness before using values.
- [ ] Calibrate any sports model chronologically against BK using log loss,
  Brier score and calibration error.
- [ ] Test only capped BK/sports blends that pass a no-degradation gate.
- [ ] Re-run package comparison using the calibrated frozen probability matrix.

## Decision gates

- Operational readiness requires complete identity/timing evidence and a
  scheduler-owned final input.
- A challenger may replace the control only after a predeclared prospective
  sample and metric gate.
- Modeled EV alone cannot open a release gate.
- No package or model guarantees a win or positive ROI.
