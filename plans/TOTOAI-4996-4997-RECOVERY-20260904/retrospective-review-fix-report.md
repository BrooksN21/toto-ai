# Historical P1 reconciliation — bounded review-fix

Task: TOTOAI-4996-4997-RECOVERY-20260904. Worker 01a07108-e153-7df2-8597-397cb71b3589.

## Disposition (not based on successful replay alone)
1. **[P1] Existing retrospective output is accepted without the bound inputs or equal-input contract**
   CONFIRMED STILL OPEN AFTER NOON FIX; NOW FIXED AND INTEGRATED FOR REUSE.
   Old runner checked only report hash/identity/safety; old smoke deliberately accepted
   missing input/budget/result fields. New source validator checks producer ASCII selfhash,
   all five probability/source hashes, drawing/plan, requested/effective budget, stake,
   per-model count/cost and canonical issued control coupon hash. Bound runner recomputes
   expectations from verified frozen files, including sports rebase, not the report.
2. **[P1] Fresh retrospective settlement is not bound to the canonical primary result snapshot**
   CONFIRMED STILL OPEN AFTER NOON FIX. UNSAFE RUNNER PATH NOW DISABLED / FAIL-CLOSED;
   REUSE NOW EXACT-RESULT-BOUND. Read-only loader uses primary.result_snapshot_sha256
   and producer _verified_snapshot in the SAME session (payload/events/content/order,
   complete/VOID/identity verification), never newest row/current event counts as identity.
   Exact legacy report is protected by new execution-plan completed_replay_binding:
   report semantic hash + primary result hash + actual. This is an explicit post-draw
   audit binding, not evidence the old generator originally carried that hash.
   Original report has no result_snapshot_sha256; bytes were NOT rewritten or re-signed.
   Fresh exact-result-bound generator extension remains OPEN. Missing report is an error;
   automatic newest-snapshot replay regeneration removed, not replaced with a silent fallback.

## Current 4996 evidence / unchanged meaning
Strict read-only audit twice succeeded on original report c3563f0b5a32a876613297861c95cd48cb605515eb900c8efba55d56f4b9f283.
Canonical primary snapshot 560bb970a2dc11cfd88b492c00237d9df308e9c1fd5d0b276cbe23a6141ff425;
actual X222XX2111112X2. All five source hashes, budget and baseline contract verified.
quality-v2=11/15; sports-v2=11/15; quality-v3=13/15; robust=13/15.
Bindings VERIFIED, not newly generated. Alternate packages remain post-draw research,
NOT proof of yesterday's selection/release/profit. Original receipt/payout corrections
and immutable archives unchanged. No full replay rerun or production DB write.

## Verification
- RED: new test module initially failed missing implementation.
- 46 focused tests passed in2.90s (23 new binding tests,15 noon integrity,4 payouts,
  4 operational smoke checks). Ruff new source/tests/smoke clean.
- Negative cases: re-signed same-plan input/budget/result/control substitution; malformed
  old smoke fixture; cross-drawing/missing/corrupt snapshot; newer different completed
  snapshot does not change exact lookup; missing replay does not generate anything.
- Positive: producer-created synthetic snapshots; exact older result selected;
  explicit immutable legacy binding; actual4996 strict audit repeated without writes.
- Generated runner still has preexisting E501 formatting and a new local-import-order
  lint warning; it is syntax/runtime tested, NOT declared full-Ruff-clean. Avoid broad
  formatting/rebinding churn in this bounded slice. Parent may normalize with next rebind.

## Controlled 4996-only deployment
Original runner and executionplan bytecopies + SHA manifest preserved under
plans/TOTOAI-4996-4997-RECOVERY-20260904/review-binding-originals/.
Runner import is now active; new validator added to executionplan's file bindings.
Executionplan re-signed atomically; new plan SHA
56694a57a923e1e787a9a17f7b18be1e1fecfbce8bce09925a798ece5a278fe6.
No LaunchAgent/calendar install/change; no primary archive/state mutation. Next natural
4996 retry can reuse verified report; its older stored status retains historical plan SHA
until an actual run, not rewritten to invent a launch.4997 receipts bytehash unchanged.

## Other recovered findings — retained, not newly reproduced
- [P1] retry child policy transition does not reconcile loaded calendar: OPEN/UNVERIFIED.
  Exact next review-fix: false→true/true→false integration regression then parent retry
  reconciliation or proven calendar-preserving transition. Do not touch loaded4997 jobs.
- [P1] dirty baseline not self-contained: OPEN. Preserve storage/domain dependency,
  CLI/history-backfill/tests, scheduler fixture, ignored runtime source publication boundary;
  dirty-tree tests are not clean-checkout proof. No tracked-only/wholesale staging.
- [P2] rejected history-backfill may initialize/migrate DB: OPEN/UNVERIFIED. Validate
  before write, test missing and old-schema DB; not changed here.
- Historical stale watcher snapshot and mixed ledger entries: retain provenance; no
  fresh runtime facts or blanket commit approval inferred.

## Existing model plan / next priority (no new plan)
After scoped fresh-result producer follow-up and generic retry/baseline disposition,
F3 / existing P1 remains deterministic90-row4990–4995 read-only coverage auditor.
Baseline acceptance and predeclared minimum_prior_matches remain unresolved; no arbitrary
threshold chosen. Raw prior counts/sensitivity bands can inform a later explicit contract,
not outcome-conditioned tuning. No fitting/training/blending/activation in this slice.

## Files changed this slice
- src/toto_ai/operations/retrospective_replay_binding.py (new; reusable strict contract)
- tests/test_retrospective_replay_binding.py (new)
- plans/TOTOAI-4996-4997-RECOVERY-20260904/retrospective_smoke_checks.py
- reports/research/4996-postmortem-automation/run-retrospective-12096.py
- reports/research/4996-postmortem-automation/retrospective-plan-12096.json
- memory-bank/ACTIVE_PLAN.md; this report/checkpoint/evidence/original backups.
No wrapper edits, existing-worktree writes, scheduler4997/models/catalog/consent edits,
commit/push/new tasks. No active owned process. NEXT operational checkpoint14:30MSK;
4997cutoff16:20 unchanged. Parent owns monitoring, integration and prioritization.
