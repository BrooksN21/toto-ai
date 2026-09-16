# 5008 exporter portability review

**Task:** `TOTOAI-RESUME-20260915`  
**Verdict:** `ACTIONABLE_TEST_GAP`

The exporter itself is portable for a clean checkout: it obtains all inputs
relative to the supplied root, has no `reports/` dependency, and preserves the
15-slot roster with three `BK_FALLBACK_NO_PROVIDER_FIXTURE` slots.  Each
present provider fixture and history document is SHA-256 checked, and the
exporter carries the final-input file SHA-256 into every roster slot.

However, the replacement regression does not fully prove the claimed bindings:

1. **P2 — missing-slot/feature-to-roster association is masked.** The fixture
   places all missing slots at the end (`{12, 13, 14}`), then compares
   `roster[:12]` to `rows`. That passes even if an implementation incorrectly
   associates feature hashes by compact row index rather than `event_order`.
   Use at least one non-terminal missing order and assert, by event order, that
   every populated roster slot's `feature_sha256` equals the original row for
   that same order. Exercise `derive_reviewed()` with matching accepted
   decisions so the actual consumer's `row_id`/fixture/kickoff/hash binding is
   checked rather than only `_validate_row()` and `_roster()` separately.

2. **P2 — input-hash assertions are incomplete.** The test checks only the
   final-input *file* hash. It does not assert the exported
   `probability_input_sha256` equals the synthetic final input's declared
   value, nor that `source_evidence_sha256` equals the generated evidence
   bytes. Add both checks (including each roster slot's probability-input
   hash), so a wrong field selection or omitted evidence binding cannot pass.

Focused verification run locally:

- `.venv/bin/pytest -q tests/test_sports_v3_current_feature_export.py` —
  `1 passed in 1.25s`
- `.venv/bin/ruff check tests/test_sports_v3_current_feature_export.py src/toto_ai/research/sports_v3_current_feature_export.py` — passed.

No implementation, Git, scheduler, database, consent, outcomes, or secret
artifacts were changed or read.
