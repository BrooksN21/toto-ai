# 5008 Sports-v3 current-input binding fix

**Task:** `TOTOAI-RESUME-20260915`  
**Scope:** P1 repair in the current Sports-v3 research package adapter only. No refit, feature, collector, DB, scheduler, consent, gate, model-math, commit, or remote action.

## Change

`bind_current_snapshot()` now fails closed before a current Sports arm is accepted. It requires both:

1. the frozen prediction's final-input **file SHA-256** to equal the frozen prediction request and package request references; and
2. the frozen prediction's final-input **snapshot SHA-256** to equal the loaded package final-input snapshot.

The existing `compare_frozen_predictions()` exception boundary is unchanged: a binding error is a Sports validation failure and retains the BK-control-only fallback (`SKIPPED_MISSING_OR_INVALID_SPORTS` / `BK_CONTROL_ONLY_SPORTS_SKIPPED`), rather than accepting a mismatched Sports arm.

## Changed paths

- `src/toto_ai/research/sports_v3_package_comparison.py`
- `tests/test_sports_v3_package_comparison.py`
- `plans/TOTOAI-RESUME-20260915/5008-sports-v3-binding-fix.md`

## Regression evidence

- Added a regression with two current snapshots carrying the same declared probability-input identity but different AS-OF (`captured_at`) and snapshot SHA-256. The original binding passes; the distinct snapshot raises `ValueError: current final-input snapshot binding`.
- Added a regression that a prediction-request final-input file reference differing from the frozen prediction/package reference raises `ValueError: current final-input file binding`.
- Focused verification: `./.venv/bin/pytest -q tests/test_sports_v3_package_comparison.py tests/test_sports_v3_retrospective_predict.py` → **51 passed in 1.71s**.
- Ruff: `./.venv/bin/ruff check src/toto_ai/research/sports_v3_package_comparison.py tests/test_sports_v3_package_comparison.py` → **All checks passed**.

## Actual 5008 artifact re-verification

The unchanged sealed artifacts bind to final-input file SHA-256 `c7cb615c2fb9d71ccb3d15425fd7d6612af91e0c4690696d79f0d0d457d6356c` and snapshot SHA-256 `be8dfa3d79c6d3e3c033702030f1df72ef6a359bd137f4f1a2c93cea4391c2d5`.

A non-overwriting paired-adapter run completed at:

`reports/rehearsal/TOTOAI-RESUME-20260915/sports-v3-packages-v1/5008-inference/binding-fix-check/verified/`

It returned `COMPLETE_PAIRED_RESEARCH` and `VALIDATED_SPORTS_APPLIED`; the exact file and snapshot bindings above were emitted by its comparison output. An earlier attempt at the parent `binding-fix-check/` directory is retained (not overwritten) and is BK-only due to the transient helper-reference `KeyError`; the nested `verified/` result is the successful post-fix evidence.

No hashes were changed and no mismatch was relaxed or repaired.
