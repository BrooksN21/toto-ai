# 5008 exporter portability fix

## Scope

Reworked `tests/test_sports_v3_current_feature_export.py` into a fully
self-contained `tmp_path` regression. It now writes synthetic final-input,
source-evidence, provider-fixture, and completed-history documents with the
same relative-path SHA-256 bindings consumed by `seal_current_rows()`.

The test invokes the real exporter and validation helpers. It retains positive
coverage for all 12 sealed feature rows, the full 15-slot roster, per-slot
feature SHA-256 binding, the final-input file SHA-256 binding, and all three
missing provider-fixture BK fallbacks (orders 12–14). It does not read
`reports/` and uses no mocks or skips.

No exporter source change was needed:
`src/toto_ai/research/sports_v3_current_feature_export.py` remains byte-for-byte
unchanged. No operational, scheduler, database, consent, gate, watcher, model,
or package artifacts were touched.

## Verification

- `.venv/bin/pytest -q tests/test_sports_v3_current_feature_export.py` —
  `1 passed in 0.34s`
- `.venv/bin/ruff check tests/test_sports_v3_current_feature_export.py src/toto_ai/research/sports_v3_current_feature_export.py`
  — `All checks passed!`

The bare `pytest` executable is not on `PATH`; verification used the
repository-local `.venv` executables.

## Handoff

Changed path: `tests/test_sports_v3_current_feature_export.py`.
Added handoff: `plans/TOTOAI-RESUME-20260915/5008-exporter-portability-fix.md`.
No staging, commit, push, or PR action was performed.
