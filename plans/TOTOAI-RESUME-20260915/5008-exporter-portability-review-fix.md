# 5008 exporter portability review — P2 test-gap fix

**Task:** `TOTOAI-RESUME-20260915`  
**Scope:** test-only; exporter source unchanged.

| Review gap | Regression assertion |
| --- | --- |
| P2: compact-row order could hide a missing-slot association error | The fixture now omits non-terminal orders `{3, 9, 13}`. It builds `rows_by_order` and `slots_by_order`, compares every populated slot's `feature_sha256` with the original row at the same `event_order`, and runs real `derive_reviewed()` with accepted decisions. That consumer validates `row_id`, provider fixture, kickoff, and feature-hash slot bindings. |
| P2: declared probability input and source-evidence bindings unasserted | The test hashes its own generated final input and source evidence, asserts the complete `input_hashes` mapping (including `probability_input_sha256`), and asserts every roster slot carries both the final-input file hash and declared probability-input hash. |

**Verification:**

- `.venv/bin/pytest -q tests/test_sports_v3_current_feature_export.py` — `1 passed in 0.33s`
- `.venv/bin/ruff check tests/test_sports_v3_current_feature_export.py src/toto_ai/research/sports_v3_current_feature_export.py` — passed

No exporter/runtime, scheduler, model, database, consent, watcher, or report-input artifacts changed.
