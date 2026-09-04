# TOTOAI-4995 Model Improvement Plan

Date: 2026-09-04 (Europe/Moscow)  
Scope: planning only; no scheduler, operator package, model, or release mutation.

## Current project stage

TotoAI has a protected operational control (`quality-v2`), three same-input
challengers (`sports-shadow`, `quality-v3`, `robust`), immutable replay and
post-draw settlement infrastructure, and a scheduled drawing-4996 operational
cycle. The project is still in prospective validation: no model has proved a
13+ advantage or profitability. The immediate forecast stage is to finish the
Sports Analytics v3 residual and validate it chronologically before allowing it
to influence model selection.

## Defect ledger

| Item | Status | Evidence / acceptance state |
|---|---|---|
| Parallel sidecar skipped record was passed to the ready-package validator | Fixed | Hash-valid terminal skips such as `SKIPPED_OPERATOR_NOT_READY` are now classified as non-settleable; malformed skips still fail closed. |
| 4995 equal-input replay produced no visible progress | Fixed | Replay completed with ten-second progress in 157.02 seconds. |
| P0.9 owner-facing post-draw delivery | Open | Storage/API boundary exists, but 4995 remains `pending / OWNER_RECEIPT_REQUIRED`; only a real owner-visible delivery plus hash-bound receipt closes P0.9. |
| 4995 four-model replay | Complete | qv2 9, sports 9, qv3 10, robust 9; all packages had zero 13+/14+/15 coupons. |
| Drawing 4996 scheduler/operator flow | Untouched and scheduled | Plan `0d8c2cdfb10ef9c5`; first checkpoint 17:30 MSK, T-10 19:20 MSK. This improvement work must not mutate or manually execute it. |

## 4995 failure decomposition

1. **Forecast miss, not cover-only failure.** BK top and Sports top each
   predicted only 6/15 actual outcomes. The probability inputs therefore put
   too much mass on wrong outcomes before coupon selection.
2. **No high-category coverage.** qv2, sports-shadow, qv3, and robust all had
   zero 13+ coupons. Package diversification did not recover the probability
   errors.
3. **Challenger gain was small.** qv3 improved realized best hits from 9 to 10,
   but remained three hits below category 13 and is not evidence of superiority.
4. **Sports v2 did not add realized signal.** sports-shadow tied qv2 at 9/15;
   Sports top accuracy was also only 6/15.
5. **Failure is persistent across the comparison window.** On 4990-4994,
   average best hits were qv2 10.0, sports 10.0, qv3 9.8, robust 10.2, with
   zero 13+ for every model. This rules out treating 4995 as an isolated package
   accident.
6. **Profitability is unproved.** Model and package changes must be judged by
   chronological probability quality, equal-bank 13+/14+/15 performance, and
   observed payout evidence—not one-drawing best hits.

## Ordered backlog

### P0 — operational correctness and observability

1. **Close P0.9 owner delivery.**
   - Acceptance: a completed post-draw report is delivered through the actual
     owner-facing channel; a hash-bound receipt changes delivery from `pending`
     to `delivered`; missing/failed delivery remains retryable and visible.
2. **Protect drawing 4996.**
   - Acceptance: no model-improvement task writes under its plan directory,
     invokes its scheduler, changes its authorization, or replaces its
     operator artifacts; status is observed only through the plan-bound watcher.
3. **Keep replay observable and bounded.**
   - Acceptance: every replay lasting over 10 seconds emits progress at least
     every 10 seconds and identifies drawing/model/current phase; no silent
     interval reaches the project 30-second command limit.

### P1 — probability and model improvement

1. **Create a leakage-safe 4990-4995 event attribution table.**
   - Acceptance: all 90 resolved events have immutable pre-cutoff BK/Sports
     probabilities, actual outcome, league/team identity, timestamp, and
     feature-availability flags; no post-result feature is admitted.
2. **Decompose errors by feature and segment.**
   - Acceptance: report BK versus Sports top accuracy, Brier, log loss, and ECE
     overall and by league coverage, favorite strength, entropy, venue, rest,
     congestion, standings availability, and sports-data completeness; sparse
     segments are labelled rather than generalized.
3. **Build Sports Analytics v3 as a bounded residual to BK.**
   - Acceptance: opponent-adjusted strength, recency/venue form, goals, rest,
     congestion, standings, and reliable timestamped lineup evidence are
     included only when available pre-cutoff; missing data falls back to BK;
     residual magnitude is capped and probabilities remain normalized.
4. **Run chronological walk-forward probability validation.**
   - Acceptance: folds preserve time order; Sports v3 is compared with BK and
     Sports v2 on log loss, Brier, ECE, and top accuracy; no package generation
     or promotion occurs before this gate passes without material calibration
     regression.
5. **Replay four package strategies on identical inputs.**
   - Acceptance: qv2, sports-shadow-v3, qv3, and robust use the same frozen
     input, bank 4,980 RUB, stake 30, and 166-coupon capacity for each of
     4990-4995; report P(13+), P(14+), P(15), concentration, best hits, and
     realized category counts with hashes.
6. **Define a non-degradation promotion gate.**
   - Acceptance: a challenger cannot replace qv2 unless it passes predeclared
     calibration, concentration, exposure-floor, and same-input package
     criteria; otherwise selection deterministically falls back to qv2.

### P2 — evidence and product validation

1. **Accumulate prospective evidence.**
   - Acceptance: at least 30 future drawings / 450 events with frozen
     pre-cutoff inputs and no retrospective model switching.
2. **Attach authoritative payouts.**
   - Acceptance: each settled drawing with owner evidence has a hash-bound
     transcription and observed cost/payout/profit/ROI; research-only packages
     remain explicitly counterfactual.
3. **Make a promotion decision only from the prospective set.**
   - Acceptance: publish uncertainty intervals and choose promote/retain/reject;
     no superiority or profit claim is made from 4990-4995 alone.

## Daily drawing-4996 operational checklist

- [ ] Observe the plan-bound watcher; do not manually run or mutate the scheduler.
- [ ] At/after 17:30 MSK, report the exact primary and challenger states,
      selected strategy, blocker, operator-result readiness, and next checkpoint.
- [ ] Confirm the existing plan-bound manual-release authorization remains
      valid for drawing 4996, bank 4,980 RUB, stake 30, through T-10 19:20 MSK.
- [ ] Keep quality-v2 as protected control; run sports-shadow, quality-v3, and
      robust only through the already scheduled non-blocking same-input flow.
- [ ] Before final calculation, confirm with the owner whether the manual wager
      is still planned; absence of timely confirmation fails closed.
- [ ] At terminal state, report `PLAY`/`NO_BET`, exact reason, strategy, package
      path/hash/expiry, and computed highest-P(13+) coupon metadata when valid.
- [ ] Never wager automatically and never substitute research artifacts for an
      operator package.
- [ ] Preserve the post-draw lifecycle and deliver the completed comparison on
      the next-day cycle with a verifiable owner receipt.

## Model-improvement sequence: 4990-4995 to Sports v3

1. Freeze and validate the 90-event attribution dataset for 4990-4995.
2. Produce the segmented error decomposition; identify only repeatable,
   pre-cutoff residual signals.
3. Implement Sports v3 features behind an offline/research boundary with strict
   fallback and residual caps.
4. Tune caps and feature eligibility only in chronological training folds.
5. Evaluate untouched chronological validation folds on calibration metrics.
6. Feed eligible Sports v3 probabilities through the same four-package replay
   harness and equal-bank constraints.
7. Compare against the verified baselines: 4990-4994 averages
   10.0/10.0/9.8/10.2 and 4995 results 9/9/10/9; all historical comparisons
   currently have zero 13+.
8. Keep Sports v3 non-operator until prospective gates and operational safety
   criteria are satisfied.

## Exact next checkpoint

After the drawing-4996 scheduler reaches its first automatic checkpoint at
**2026-09-04 17:30 MSK**, read only the plan-bound watcher state and report the
primary/challenger/operator status without mutating the scheduler. Separately,
the next model-development checkpoint is a hash-bound 90-event 4990-4995
attribution report with chronological availability checks and BK/Sports-v2
error decomposition; no Sports v3 coding begins before that artifact is
reviewed.
