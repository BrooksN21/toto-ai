# TOTOAI-4995-POSTDRAW-FIX-20260904 — context

## Scope and constraints

- Narrow local context collection only; no implementation changes, network, tests, VCS operations, commit, or push.
- Read: `AGENTS.md`, `memory-bank/ACTIVE_PLAN.md`, and `memory-bank/TOOLING_POLICY.md`.
- Inspection was stopped immediately when requested. Findings below are limited to files already inspected.

## Exact observed state

### Drawing 4995 post-draw comparison

- `reports/rehearsal/evening-4995-20260903T155500Z/post-draw/parallel-comparison-status.json`
  - `status`: `failed`
  - `drawing_id`: `12092`
  - `drawing_number`: `4995`
  - `error_type`: `ValueError`
  - `error`: `sidecar status identity or safety boundary mismatch`
  - `completed_at`: `2026-09-04T09:00:10.969381+00:00`
  - `automatic_wagering`: `false`

- `reports/rehearsal/evening-4995-20260903T155500Z/parallel-challenger/output/sidecar-status.json`
  - Exists in the canonical `output` directory.
  - `status`: `SKIPPED_OPERATOR_NOT_READY`
  - `reason`: `operator PLAY was not ready before sidecar safe start`
  - `started_at`: `2026-09-03T15:25:02.844927Z`
  - `observed_at`: `2026-09-03T15:40:02.915250Z`
  - `automatic_wagering`: `false`
  - Contains `schema_version` and `record_sha256`, but no `plan_id`, `drawing`, `drawing_id`, `research_report`, or `research_report_sha256` fields.

- `reports/rehearsal/evening-4995-20260903T155500Z/parallel-challenger/output-final/`
  - Directory was absent when checked; therefore no legacy `output-final/sidecar-status.json` was available.

- `reports/rehearsal/evening-4995-20260903T155500Z/post-draw/post-draw-state.json`
  - Primary post-draw lifecycle is independently complete: `status=complete`, `reason=SETTLEMENT_COMPLETE`, `attempts=1`.
  - It is bound to drawing `12092` / `4995` and contains package, result snapshot, settlement, archive, review-request, and state SHA-256 values.
  - Its `updated_at` exactly matches the failed parallel-comparison `completed_at`: `2026-09-04T09:00:10.969381+00:00`.

## Relevant implementation behavior

- `src/toto_ai/operations/finished_draw.py`, `_settle_parallel_comparison_if_available` (observed around lines 1608–1703):
  - Selects canonical `parallel-challenger/output/sidecar-status.json` whenever it exists; otherwise uses the bounded legacy `output-final/sidecar-status.json` fallback.
  - Returns only when neither status file exists.
  - It does not inspect or filter the sidecar `status` before calling `settle_final_hybrid_comparison(...)`.
  - It validates the frozen scheduler identity, then passes the selected sidecar path plus drawing identity, plan ID, actual result, and output directory to the settlement function.
  - Any comparison exception is advisory to primary settlement and is written as `parallel-comparison-status.json` with `status=failed`; it does not fail the primary post-draw state.

## Existing targeted test coverage observed

- `tests/test_post_draw_plan_lifecycle.py`, `test_plan_run_settles_available_parallel_comparison_and_notifies`:
  - Parametrized for both `output` and `output-final`, so canonical and legacy path selection are covered.
  - Writes an empty `{}` sidecar status and monkeypatches the settlement function; therefore it does not exercise real validation of a non-ready/skipped sidecar record.

- `tests/test_final_hybrid_settlement.py`:
  - Happy-path fixture uses `status=READY_PARALLEL_PLAY_BEFORE_T10` and includes `plan_id`, drawing identity, research report path/hash, `automatic_wagering=false`, and a valid `record_sha256`.
  - Covers successful exact-package settlement and rejection of a tampered comparison report.
  - No observed test covers `SKIPPED_OPERATOR_NOT_READY` as input to post-draw comparison settlement.

- `tests/test_final_hybrid_sidecar.py`, `test_sidecar_skips_when_operator_is_not_ready_before_safe_start`:
  - Confirms that the producer legitimately emits `SKIPPED_OPERATOR_NOT_READY` when operator PLAY is unavailable before safe start.
  - Only asserts the status and `automatic_wagering=false`; it does not cover consumption by finished-draw settlement.

## Payout schema precedent (inspection limited to requested file)

- `data/payout-evidence/4993/record.json` uses schema version 1 with drawing/source identity and source SHA-256, displayed/closed timestamps, drawing status, category entries containing `hits`, `winning_variants`, and decimal-string `payout_coefficient`, cumulative-per-ruble semantics, and an explicit payout formula.
- It separates transcription confirmation and ROI eligibility: `owner_transcription_confirmed=false` and `eligible_for_observed_roi=false`; `automatic_wagering=false`.
- This is schema precedent only and does not explain the sidecar settlement failure.

## Concise root-cause hypotheses

1. **Primary hypothesis:** the finished-draw consumer treats every existing canonical sidecar status as settlement input. Drawing 4995 has a legitimate terminal non-ready record (`SKIPPED_OPERATOR_NOT_READY`), but the consumer still calls the strict comparison settlement validator, which expects a ready, identity-bound research record and rejects this skipped record with `sidecar status identity or safety boundary mismatch`.
2. **Coverage gap:** lifecycle tests verify `output`/`output-final` path selection only through a monkeypatched settlement function; settlement tests cover a ready record and tampering, while the producer test covers the skipped state in isolation. No observed integration test connects the legitimate skipped producer state to the finished-draw consumer.
3. **Expected repair direction to validate later:** distinguish a legitimate non-ready/skipped sidecar outcome before invoking exact-package settlement, while preserving strict failure for malformed or unsafe records that claim readiness. The primary post-draw settlement should remain independent, as it did here.

## Blocker

- None for context capture. Further inspection was intentionally stopped by the owner.
