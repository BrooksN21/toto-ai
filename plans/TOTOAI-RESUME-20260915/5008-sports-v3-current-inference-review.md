# 5008 Sports-v3 current-inference independent review

**Task:** `TOTOAI-RESUME-20260915`  
**Scope:** read-only review of the frozen current 5008 Sports-v3 adapter and fixed-package common-matrix diagnostic. No refit, implementation, operational action, results/labels, coupon display, Git operation, or remote action.

## Verdict: NEEDS_FIX (P1 binding gap)

The persisted 5008 artifacts themselves are internally consistent, but the current-adapter code does **not** enforce the required full final-input snapshot binding across the prediction request and package-comparison request. Therefore the source change is not accepted until this is made fail-closed and covered by a current-request regression test.

### P1 — package comparison does not bind its current final-input snapshot to the frozen prediction snapshot

`src/toto_ai/research/sports_v3_package_comparison.py`, `_sports()` / `bind_current_rows()` validates row target IDs, BK matrix hash and BK probabilities against the package request's final-input file. It replays the prediction request separately, but it never requires:

- `prediction.final_input_file_sha256 == package_request.final_input.file_sha256`, or
- `prediction.final_input_snapshot_sha256 == package_final_input.snapshot_sha256`.

Thus a separately sealed prediction request could be paired with another sealed current final-input snapshot that has the same probability matrix and event IDs. The current row-level checks would pass, while the required AS-OF/full-snapshot identity is not enforced. This is specifically material because the report claims snapshot binding, not merely BK-matrix equality.

**Required repair:** before accepting the current arm, require both the final-input file hash and full snapshot hash to equal the frozen prediction's corresponding bindings (and preferably assert the prediction request final-input reference matches too). Add a regression that uses two valid current snapshots with identical BK probabilities/IDs but distinct `snapshot_sha256`/AS-OF metadata, and prove rejection. This is a code/test repair only; no refit or new research plan is needed.

## Verified artifact facts (current artifact only)

- Common-matrix file SHA-256 recomputed: `8e6c375365283d1dabbdc58e20f6a74550e012662f02790b18906242965db474`.
- Actual artifact references are equal despite the code gap: final-input file `c7cb615c2fb9d71ccb3d15425fd7d6612af91e0c4690696d79f0d0d457d6356c`; snapshot `be8dfa3d79c6d3e3c033702030f1df72ef6a359bd137f4f1a2c93cea4391c2d5`; BK input `f55b5d7aab0303f494d0c52c7f737a4edb41da997e3957ab62c41bda30e6526e`.
- Frozen model file/payload hashes: `f334b21efd5dfd369c530d7e037b7c9ac8e6ee087d235872ac42453579d37b0e` / `8381fcf507c77152835e69325c46e446d40e5acb163bf019f03ea1c16d74fdde`. Model declares 53 feature names and 26 non-intercept feature rows with a nonzero coefficient; no fit executed by this run.
- Reviewed source has exactly 12 accepted rows. Inference has 12 nonzero, changed Sports rows and exact BK fallbacks at zero-based event orders 7, 8, 9. All output probability vectors are positive and sum to one within floating-point precision.
- Reviewed rows retain nullable optional feature values (11 nulls of 53 feature fields on each of the 12 accepted rows); no null-to-zero fabrication was observed. Prediction payload has no outcome/label field; freeze receipt says `labels_read=false` and `fit_executed=false`.
- Focused verification run here: `49 passed in 1.58s`; Ruff passed. (The supplied historical “50 passed” count was not reproduced by the current two specified test files.)

## Exact P(13+) common-matrix diagnostic

| Fixed package | COMMON_BK | COMMON_SPORTS_V3 | Difference (Sports − BK) |
|---|---:|---:|---:|
| quality-v2 | 0.013794798981212 | 0.013445525152024 | -0.000349273829188 |
| sports-shadow | 0.013629249975188 | 0.013305510606943 | -0.000323739368245 |
| quality-v3 | 0.018587090240809 | 0.019618115521664 | +0.001031025280855 |
| robust | 0.017420111343040 | 0.018079166202235 | +0.000659054859195 |
| sports-v3-top-product | 0.012075138585898 | 0.020456210598184 | +0.008381072012287 |

These are fixed-package probabilities under two specified probability matrices, not empirical profitability, calibration, or a wagering recommendation.

## Fairness / comparator boundary

A paired BK top-product control **does exist**: the adapter creates `BK` and `MIXED_V3` packages using the same `top_probability_coupons(..., limit=166)` selector, same cost and same fixed input. It is the valid within-generator control for the Sports-v3 top-product result.

It is **not** fair to call the Sports-v3 top-product package a model-only replacement for quality-v2, quality-v3, or robust. Those existing packages use different objectives/generators. In particular, quality-v3 is created via `toto_ai.optimizer.uncertainty_package.select_uncertainty_package(...)`, whose current contract takes `bk_probabilities`, builds BK-plus-flattened uncertainty models, generates candidates, then calls `select_robust_package`; it does not accept an arbitrary Sports-v3 matrix.

A fair same-engine follow-up therefore requires a bounded adapter/run that supplies the frozen Sports-v3 matrix to the same quality-v3 candidate-generation and `select_robust_package` contract, preserving the exact `QualityV3Config`, 166-coupon budget, anchors/exposure constraints, seeds and fixed final input, alongside a BK control. Alternatively, use the already general `select_robust_package(candidates, probability_models, category, max_coupons, sample_count, seed_material, exposure_constraints, fallback_coupons)` with one unchanged candidate universe and identical settings for BK and Sports-v3. Neither run should be described as a pure model improvement unless generator/candidate-set effects are controlled.
