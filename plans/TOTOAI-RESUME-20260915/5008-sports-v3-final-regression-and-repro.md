# 5008 Sports-v3 final regression and reproducibility handoff

Task: `TOTOAI-RESUME-20260915`  
Scope: test-only sealed-adapter regression and local research-artifact follow-up.

## Completed

- Added `test_current_adapter_rejects_distinct_valid_snapshot_and_keeps_bk_control`
  in `tests/test_sports_v3_package_comparison.py`.
- Portability correction: the test is now entirely synthetic and self-contained
  under `tmp_path`. It builds a sealed model, roster, reviewed feature rows,
  manifest, prediction request/freeze, and two parseable current inputs with
  valid file and payload hashes. It reads no `reports/` runtime artifact and
  has no absence skip.
- The two synthetic current inputs have identical event IDs and BK probabilities,
  and differ only in `captured_at` and `snapshot_sha256` for input B.
- The real `compare_frozen_predictions()` path receives a prediction request for
  A and a package request for B, each with its own physical hash. It rejects the
  mixed binding, persists `comparison.json`, produces only a valid 166-coupon BK
  package, and reports `BK_CONTROL_ONLY_SPORTS_SKIPPED`.
- The same test then uses input A for both sealed requests and proves the positive
  path remains `COMPLETE_PAIRED_RESEARCH` / `VALIDATED_SPORTS_APPLIED`, with both
  166-coupon BK and `MIXED_V3` research packages.
- The mismatch reaches the earlier physical-file binding (`current final-input
  file binding`), as two valid independently hashed files cannot also satisfy
  the exact-file equality prerequisite. The existing helper test continues to
  cover the subsequent snapshot-only predicate after file identity is established.

Verification:

```text
./.venv/bin/pytest -q tests/test_sports_v3_package_comparison.py
20 passed in 2.15s

./.venv/bin/pytest -q tests/test_sports_v3_package_comparison.py tests/test_sports_v3_retrospective_predict.py
52 passed in 2.56s

./.venv/bin/ruff check src/toto_ai/research/sports_v3_package_comparison.py tests/test_sports_v3_package_comparison.py
All checks passed!
```

## Same-engine reproducibility: deferred safely

The saved `5008-same-engine/comparison.json` has the recorded settings and the
two selected coupon-order hashes, but no selected coupon arrays and no saved
replay harness. A bounded source search found no saved same-engine runner.
Recreating it before the protected 16:30 MSK primary checkpoint would require
constructing and validating a new local script, so it was not started in the
pre-16:29 safety window. No research compute, operator artifact, upload format,
or shared-memory/runtime mutation was performed.

After the primary is complete, a separate bounded replay may recreate the exact
recorded 293-candidate union, 166-coupon count, category 13, 10,000 samples,
seed `quality-v2-vs-v3-prospective-v1-selector`, and flatten weights 0.1/0.2.
It must write only a new fixed research subdirectory containing selected coupon
arrays and candidate union as JSON/CSV, both common matrices and hashes, source
bindings/settings/hash manifest, and `operator_compatible=false` plus
`automatic_wagering=false`. It must compare generated coupon-order hashes with
the old BK `6fd5ab5eb4571b239e9ec154140bd009ee611d171e5a0265428c0bd44d5a1bfb`
and Sports-v3 `036c15018499b79d4abea0c73a13b971029165df5693b03a639ffd77ede161ab`;
any mismatch must be labelled a **new replication**, not original evidence.
Only then evaluate both fixed packages under `COMMON_BK` and
`COMMON_SPORTS_V3`, reporting four conditional P(13+) values with no empirical
profitability claim. Preserve the existing artifacts untouched.
