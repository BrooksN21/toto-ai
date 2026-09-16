# P0/P1/P2 — first bounded observability increment

Task TOTOAI-RESUME-20260915 · 2026-09-15T21:23:21.972472+03:00

## Implemented
- Robust result now records `selection_trace`: path, fallback reason, greedy selected count, one-based selection iteration, remaining candidate count and violated final exposure bounds at fallback. Identical coupon sets alone are not labelled fallback.
- Real synthetic counterexample: candidate universe11/12/21 has feasible control12+21; greedy chooses11 and stalls on iteration2. Trace correctly reports missing outcome2 in both events and preserves control order. Legitimate identical selection and timeout are separately tested.
- Additive `sampled_metrics_scope=OPTIMIZER_SELECTION_SAMPLE_NOT_CALIBRATED`; previous numeric fields retain definitions.
- New opt-in `evaluate_fixed_package` in research records training-sample coverage, independent-stream coverage, exactP13/14/15, seeds/counts, coupon-order and probability hashes. No actual outcomes or generator callback accepted. It never marks a probability calibrated, authorizes a wager, or runs in the live selector.
- Independent streams can sample the same outcome; removing overlaps would bias evaluation. Tests check different stream seeds, not disjoint outcome support.

## Verification
- RED reproduced before code:3missing-trace failures and missing-diagnostic-module collection failure.
- **56 passed,1 deselected,1.33s; Ruff4files PASS.** Heavy realEVSurface test already passed earlier; not rerun.
- **6 baseline parity cases PASS** against HEAD source: all original fields, coupon order, sampled/exact metrics, timeout and category unchanged. Initial comparison harness needed old-module ExposureConstraints type; that harness issue was corrected, not production behavior.
- Real frozen5001quality-v3 evaluated in0.74s, no coupon regeneration: BK training4.20%, independent2.49%, exact2.3846%. All3model training/exact metrics exactly match original record; input/package/freeze bytes unchanged. This is unknown-asof SCENARIO evidence, not real-world calibration.

## Changed code/tests
- `/Users/turshevr/toto-ai/src/toto_ai/optimizer/robust_package.py`
- `/Users/turshevr/toto-ai/src/toto_ai/research/package_selection_diagnostics.py`
- `/Users/turshevr/toto-ai/tests/test_robust_package.py`
- `/Users/turshevr/toto-ai/tests/test_package_selection_diagnostics.py`

## Runtime / publication boundary
After independent review/publication, newly started Python processes importing robust_package see additive trace. Already-imported running processes do not hot-reload. No restarts performed or needed for this research-only diagnostic demonstration. Evaluation remains explicit opt-in, never inserted into live runtime.
No stage/commit/push, scheduler/DB/consent/Sports/ACTIVE_PLAN edits. All commands completed. Only selection metadata changed in native module; evaluation helper stays inactive.

## Next small behavioral patch — NOT implemented
For separate design/review: an inactive `repair_from_feasible_seed` helper starts from complete valid control and attempts bounded deterministic one-out/one-in exchanges. Reuse native objective helpers; keep every intermediate complete package within exposure/cardinality/uniqueness constraints. Explicit no-op/timeout reason; retain valid control. Never change production defaults in this step.
Acceptance: exhaustive tiny feasible-universe tests; all constraints preserved; declared objective monotonicity and independent/exact assessment; bounded runtime; no labels accepted. Do not force a difference or retune toward these8outcomes.

## Handoff
- Machine receipt and source SHA256: [P0-P1-observability.json](/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/P0-P1-observability.json)
- [P0-P1-observability-parity.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/P0-P1-observability-parity.json)
- [P0-P1-real-fixed-evaluation.json](/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/P0-P1-real-fixed-evaluation.json)
- Independent review and canonical-memory/publication belong to parent/finalizer. No ongoing owned command.
