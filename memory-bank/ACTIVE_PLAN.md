# Active execution plan

Last updated: 2026-09-04 Europe/Moscow.

This is the binding TotoAI plan until every item is complete or the project
owner explicitly changes it. Read this file before any operational,
automation, package, settlement, or forecast work. A context compaction does
not reset this plan.

## Fixed product rules

- The objective is to improve the real probability of high-category hits and
  ultimately observed profit. No current model has proven profitability.
- A one-off owner choice on drawing 4993 or any other drawing is not a model
  preference. Compare all eligible same-input models anew on every drawing.
- Automatic wagering is forbidden. The owner uploads a verified text package
  manually.
- Every bank divisible by 30 and at least 4,980 RUB is supported; 4,980 RUB is
  the current debugging default, not a permanent constant.
- Moscow time controls the BaltBet operational cutoff. T-10 is immutable.
- Research, rehearsal, expired, and `NO_BET` artifacts are never wagering
  packages.

## Mandatory daily operating cycle

### A. Night and morning preparation

- [ ] Nightly reconciliation at 03:20 MSK refreshes finished drawings and
  persists `SUCCESS`, `PARTIAL`, or `DEFERRED` with an exact reason.
- [ ] The morning dispatcher discovers every new active drawing, synchronizes
  all 15 events, collects schedule evidence, prepares the evening scheduler,
  parallel sidecar, and post-draw lifecycle.
- [ ] Zero, missing, or immature early pool probabilities defer only training;
  they must not block drawing sync, timing evidence, scheduler preparation, or
  sidecar preparation.

### B. Completed-drawing review

- [ ] At 12:00 MSK, refresh the previous drawing and settle the actual frozen
  primary package plus all frozen same-input comparison packages.
- [ ] If results are incomplete, classify pending/VOID/postponed correctly and
  retry every three hours without manufacturing outcomes.
- [ ] Report actual hits, 13+/14+/15 counts, model comparison, misses by event,
  and concrete forecast improvements. Ask the owner whether additional manual
  review is wanted when settlement becomes complete.
- [ ] Attach authoritative category payout evidence when available; otherwise
  ask the owner for a redacted BaltBet payout screenshot. Until public or
  owner-confirmed evidence exists, payout, profit, and ROI remain unknown.

### C. Active-drawing monitoring and release

- [ ] Once an exact drawing scheduler is active, keep one plan-bound local
  watcher running from the first evening checkpoint through terminal output.
- [ ] Attach one five-minute Codex heartbeat only as a read-only chat-delivery
  channel for watcher status. It never runs or repairs project code.
- [ ] Every status says: Moscow observation time, drawing/plan, last phase,
  exact success/error, primary and challenger states, selected strategy,
  operator-result readiness, blocker, next checkpoint, and expiry.
- [ ] Before the final calculation, ask whether the owner plans a manual wager.
  If yes, request exact drawing/plan-bound pre-T-10 experimental authorization,
  even when the default gate is expected to be `NO_BET`. No answer means fail
  closed.
- [ ] Run the protected quality-v2 control and non-blocking sports-shadow,
  quality-v3, and robust candidates on the same final input, bank, stake, and
  coupon capacity.
- [ ] Publish a challenger only if the predeclared same-input non-degradation
  and safety selector passes; otherwise retain the control.
- [ ] For terminal `PLAY`, deliver one downloadable BaltBet `.txt` plus drawing,
  strategy, coupon count, stake, total cost, hash-bound expiry, and the computed
  highest-P(13+) coupon with model, objective, probability, and one-based
  package position.
- [ ] For terminal `NO_BET`, report the exact reason and absence of an
  actionable package. Never substitute a research package.
- [ ] Delete the chat heartbeat after the terminal status is delivered. Keep
  the post-draw LaunchAgent.

## Immediate operational repair checklist

- [x] P0.1 Finish, format, and test project-`.venv` binding and migration for
  generated parallel-sidecar wrappers.
- [x] P0.2 Add a generated-wrapper import smoke before LaunchAgent activation.
- [x] P0.3 Fix drawing-4995 early zero/missing pool as training-only deferral.
- [x] P0.4 Observe a real automatic drawing-4995 preparation and preflight;
  manual execution does not satisfy this item.
- [x] P0.5 Observe drawing-4994 post-draw automation from the
  2026-09-03 12:00 MSK checkpoint and its bounded retries.
- [x] P0.6 Add an end-to-end status contract covering selected drawing, plan,
  phase, exact error, next attempt, all model states, operator state, and
  expiry.
- [x] P0.7 Make concurrent probability refresh monotonic: if another process
  persists newer same-drawing probability evidence while a scheduler pass is
  running, the scheduler must adopt/reload the newer evidence instead of
  terminating with `older probability evidence cannot replace newer evidence`.
- [x] P0.8 Bind scheduler plans to an immutable per-plan schedule-evidence
  snapshot (or an equivalent immutable drawing slice), not the mutable global
  ledger bytes. Updating unrelated/current evidence must not make read-only
  `scheduler-status` fail with a ledger content-hash mismatch.
- [ ] P0.9 Make completed post-draw review delivery observable end to end. A
  local `notification.status=sent` is not sufficient unless the owner-facing
  delivery channel has a verifiable receipt; undelivered review remains
  pending and must be retried/reported.
  The drawing-independent storage/API boundary is implemented: completed
  reviews create a separate hash-bound `review-delivery.json`; local send
  success remains `pending`, send failure is `failed`, both remain retryable,
  and only a hash-bound owner-channel receipt may produce `delivered`.
  Drawing 4995 is currently `pending` / `OWNER_RECEIPT_REQUIRED` with no
  receipt. P0.9 remains incomplete until an owner-visible delivery and receipt
  are observed end to end.
- [x] P0.10 Before the first evening calculation, create and verify the
  plan-bound owner prompt for manual-wager intent and experimental release.
  Missing owner authorization must be visible as an explicit blocker before
  the final calculation, not discovered after expiry. Canonical
  `scheduler-status` now emits a deterministic hash-bound
  `manual_wager_request`; missing authorization is an explicit blocker and
  exact plan authorization clears it. Drawing 4996 verifies the authorized
  path without scheduler mutation.
- [x] P0.11 Settle the canonical parallel sidecar from
  `parallel-challenger/output/sidecar-status.json`. Preserve a bounded legacy
  fallback for `output-final`, but never silently omit the four-model
  post-draw comparison because producer and consumer disagree on the directory.
- [x] P0.12 Keep post-draw synchronization independent from evening scheduler
  success. An early terminal integrity/permanent failure must prepare and, for
  a loaded scheduler, install the exact non-wagering post-draw lifecycle. Bind
  the verified last-known-good package for analysis when available; otherwise
  use an explicit package-free `NO BET` binding.

## Forecast improvement checklist

- [x] F1 Put quality-v2-style exposure floors, hard concentration caps, and
  control-relative concentration limits inside quality-v3 and robust
  construction, not only in the post-generation selector.
- [x] F2 Replay quality-v2, sports-shadow, corrected quality-v3, and corrected
  robust on drawings 4990-4994 with identical immutable inputs, bank, stake,
  capacity, and chronology. All five drawings are complete; every strategy has
  zero 13+ coupons and no superiority or profitability claim is supported.
- [ ] F3 Build Sports Analytics v3 as a bounded residual to the calibrated
  market using opponent-adjusted team strength, recency/venue form, goals,
  rest, congestion, standings, and only reliable timestamped lineup evidence.
- [ ] F4 Validate probabilities chronologically with walk-forward log loss,
  Brier score, ECE, and top-outcome accuracy before package evaluation.
- [ ] F5 Compare equal-bank package P(13+), P(14+), P(15), concentration,
  realized best hits, and category counts prospectively.
- [ ] F6 Accumulate at least 30 prospective drawings / 450 events before
  claiming superiority; one drawing never selects a permanent model.
- [ ] F7 Add authoritative category payouts and calculate observed cost,
  payout, profit, and ROI. Modeled payout is not observed profit.

## Payout evidence protocol

- Prefer a lawful public BaltBet result/payout endpoint if one can be verified.
- If payout data is visible only in the owner's authenticated account, the
  owner may provide a cropped screenshot for each drawing. Remove account ID,
  balance, and personal data.
- A screenshot must visibly bind drawing number/date and show category, winning
  variant count, and BaltBet's displayed payout coefficient. Transcribe these
  exact displayed fields into a structured record, preserve the source image
  hash, show the extracted values back to the owner for confirmation, and only
  then use it for observed ROI.
- BaltBet's official rules verify cumulative threshold coefficients: for a
  coupon with `N` hits, gross payout is `stake * sum(coefficient[h])` for every
  eligible threshold `h` from 9 through `N`. Preserve source decimals exactly.
- Never infer category payouts from pool percentages or hit counts.

## Current status

### Done

- [x] Reconstructed the two-week automation, incident, compaction, and forecast
  context in `memory-bank/OPERATIONS_HANDOFF.md`.
- [x] Preserved the primary scheduler / local watcher / Codex heartbeat
  separation in project memory.
- [x] Confirmed that the one-off 4993 owner choice is not a future selection
  rule.

### In progress

- [x] P0.1 project-`.venv` parallel-wrapper migration is implemented and its
  focused tests pass.
- [x] P0.2 activation performs a real `toto_ai` import smoke before installing
  the LaunchAgent; focused tests and Ruff pass.
- [x] P0.3 zero, missing, or partially zero early pool is parsed as unavailable
  training input while BK/event preparation remains usable; corrupt negative
  or non-finite pool values still fail closed.
- [x] P0.4 drawing 4995 reached verified 15/15 kickoff evidence and the generic
  morning LaunchAgent automatically prepared plan `bfc008b4298d8f31` without a
  manual dispatcher run.
- [x] P0.6 canonical read-only `scheduler-status` and plan-bound local watcher
  cover the primary, challengers, selected strategy, computed highest-P(13+)
  coupon, operator state, blocker, next checkpoint, and expiry.
- [x] F1 quality-v3 and robust now enforce quality-v2 exposure floors, a hard
  concentration cap and a control-relative cap during construction, with an
  exact safe-control fallback. Full verification is 2,300 passed / 13
  deselected; Ruff clean.
- [x] F2 constrained equal-input replay is complete for drawings 4990-4994.
  Average best hits are quality-v2 10.00, sports-shadow 10.00, quality-v3 9.80
  and robust 10.20. Every strategy has zero 13+ coupons; the comparison is
  descriptive only.
- [ ] F3 current work: the immutable 4990-4994 event-attribution aggregate is
  complete over 75 resolved events. Sports v2 is 31/75 top-correct versus BK
  32/75, while Brier/log loss are only marginally better. Next build the
  leakage-safe opponent/recency/venue/rest/standings residual and evaluate it
  only in chronological walk-forward folds.

### Blocked or pending observation

- [x] Drawing 4996 is READY 15/15 under plan `0d8c2cdfb10ef9c5` at
  `reports/rehearsal/evening-4996-20260904T163000Z/`. Its LaunchAgent is loaded
  for the 2026-09-04 19:30 MSK cutoff; first checkpoint is 17:30 MSK and T-10
  expiry is 19:20 MSK. Its plan-bound read-only watcher LaunchAgent
  `com.totoai.status-watcher.v1.0d8c2cdfb10ef9c5` is loaded for 17:30 MSK;
  the matching five-minute chat heartbeat has been proposed in Codex Desktop.
  Events 7, 11 and 13 were closed with hash-bound official-plus-independent
  public schedule evidence. Exact experimental manual-release authorization
  was recorded on 2026-09-03 for bank 4,980 RUB / stake 30 and expires at T-10,
  2026-09-04 19:20 MSK. Profitability remains unproven and automatic wagering
  remains prohibited.
- [x] P0.5 drawing 4994 post-draw completed automatically at 12:00 MSK:
  quality-v2 best hit count was 10/15, with no 13+/14+/15 coupon. The review
  remained local despite `notification.status=sent`; P0.9 tracks the delivery
  defect.
- [x] Drawing 4995 terminated during warmup at 18:05 MSK after a concurrent
  fresher market snapshot overtook the scheduler's in-flight snapshot. A
  validated 166-coupon / 4,980 RUB pre-final checkpoint existed but was
  non-actionable; no plan-bound experimental authorization was recorded, the
  sidecar skipped because operator PLAY was absent, and the package expired at
  18:45 MSK. P0.7 and P0.8 fixed the triggering races. P0.12 now covers the
  independent lifecycle gap: exact post-draw LaunchAgent
  `com.toto-ai.post-draw-12092` is installed for 2026-09-04 12:00 MSK and is
  hash-bound to that non-actionable LKG package for settlement only.
- [x] The P0.7 race now preserves a slightly newer concurrently persisted
  probability snapshot while still rejecting materially stale evidence. The
  P0.8 plan builder now copies the exact schedule ledger and referenced review
  documents into an immutable plan-local binding before hashing them. All
  scheduler consumers and tests now use the materialized persisted plan ID,
  while crash recovery safely reuses that immutable plan after rebinding only
  the mutable source-ledger fields for target comparison.
- [x] P0.11 now reads the canonical parallel sidecar from
  `parallel-challenger/output/sidecar-status.json` with a bounded legacy
  `output-final` fallback. Recovered settlement for drawing 4994 shows all four
  packages at 10/15 and no 13+/14+/15 coupon.
- [x] Drawing-independent post-draw sidecar consumption now recognizes
  hash-valid producer terminal skip records such as
  `SKIPPED_OPERATOR_NOT_READY` as non-settleable. Drawing 4995 records an
  advisory `skipped` comparison instead of passing the record into the strict
  ready-package identity validator; malformed skip records still fail closed.
- [x] Drawing-4995 owner payout evidence is preserved under
  `data/payout-evidence/4995/` with exact screenshot and record hashes. The
  non-actionable 166-coupon package had four 9-hit coupons, yielding a strictly
  counterfactual gross return of 1,029.83400 RUB, net -3,950.16600 RUB and ROI
  -79.320602409638554216867469879518072289156626506024%. It is not observed
  ROI because the package is not evidenced as placed.
- [x] Final local verification for the drawing-4995 repair completed with
  2,306 tests passed, 13 deselected, and full-project Ruff clean.
- [ ] Drawing-4993 payout transcription awaits explicit owner confirmation;
  until then observed payout/profit/ROI stay disabled.
- [ ] The constrained replay has zero 13+ hits on 4990-4993. Robust average
  best hits rose from 9.50 to 10.25 versus its prior selector, but this small
  four-drawing result is not evidence of superiority or profitability.

## Required status format after every step

1. **Done now:** exact completed work and evidence.
2. **In progress:** one current item only.
3. **Remaining:** incomplete checklist items, ordered P0 then forecast.
4. **Blocker/risk:** exact blocker or `none`.
5. **Next checkpoint:** exact command-independent event/time or verification.
