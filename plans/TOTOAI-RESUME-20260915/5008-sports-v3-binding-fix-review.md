# 5008 Sports-v3 binding fix — independent review

**Task:** `TOTOAI-RESUME-20260915`  
**Verdict:** **NEEDS_FIX**

## A. P1 binding repair

The production adapter path now calls `bind_current_snapshot()` before accepting
the Sports arm. It requires the prediction file hash to match both sealed
request references and the prediction snapshot hash to match the loaded current
final-input snapshot. A `ValueError` is caught by the existing adapter boundary,
which retains the BK-only result (`SKIPPED_MISSING_OR_INVALID_SPORTS` /
`BK_CONTROL_ONLY_SPORTS_SKIPPED`). The successful non-overwriting 5008 artifact
at `.../binding-fix-check/verified/comparison.json` records
`COMPLETE_PAIRED_RESEARCH` and `VALIDATED_SPORTS_APPLIED`, with the stated
file/snapshot bindings and 12 Sports rows plus 3 exact BK fallbacks.

However, the new distinct-AS-OF regression directly invokes
`bind_current_snapshot()` only. It does **not** build sealed prediction and
package requests and call `_sports()`/`compare_frozen_predictions()` to prove
that the real adapter rejects two otherwise-valid current snapshots and emits
the BK-only fallback. The existing adapter-level fallback test covers missing,
tampered, and corrupt predictions, not this snapshot mismatch. Therefore the
requested real-adapter regression remains missing; passing 51 tests and Ruff
do not close this P1 acceptance condition.

**Minimal repair:** add one fixture-backed adapter-level test: preserve the
same event IDs/probabilities and declared probability-input identity, change
only `captured_at`/`snapshot_sha256` in a second valid current final input,
invoke `compare_frozen_predictions()`, and assert no `MIXED_V3` package,
`BK_CONTROL_ONLY_SPORTS_SKIPPED`, and the snapshot-binding error. Retain the
current helper unit test as a focused unit check.

Verification run: `51 passed` for the two specified test files; scoped Ruff
passed. No implementation, refit, results read, operator/DB/job/gate action,
or publication was performed by this review.

## B. Same-engine comparison and common-matrix metrics

`5008-same-engine/comparison.json` substantiates a restricted generic robust
pair: one 293-candidate BK∪Sports-v3 union, 166 coupons per arm, 10,000 samples
per variant, the same seed, identical 10%/20% flatten variants, and no explicit
exposure constraint. The recorded base figures (1.4978% BK; 2.1622% Sports-v3)
are each arm's **own base probability matrix**, not a common-evaluator
cross-evaluation. Both selected packages report maximum outcome share `1.0`;
that concentration warning remains material.

Cross-evaluation is **not reproducible from saved artifacts**. The same-engine
record stores only selected coupon-order SHA-256 values, not the selected coupon
strings or sealed package files. The persisted input BK/MIXED_V3 package paths
are candidate-universe sources, not the two selected generic-robust outputs.
Consequently, no `COMMON_BK` / `COMMON_SPORTS_V3` table is emitted here and no
numbers are invented or regenerated after the cutoff.

**Minimal missing capture for a future reproducible table:** immutable sealed
JSON (or coupon bytes plus hash/protocol) for each selected same-engine arm,
both common probability matrices and their hashes, plus the evaluator settings
(category, seeds, sample counts, flatten variants, candidate-union hash and
constraints). Then evaluate both fixed selections under each matrix without
reselecting candidates.

This is not deployed `quality-v3`: it is the restricted generic robust pair,
not the direct quality-v3 14,140-candidate universe. It supports neither a
model-quality, calibration, profitability, activation, nor wagering claim.
