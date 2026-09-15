# Stage A — inert Sports V3 library adopted

Task: TOTOAI-RESUME-20260915. Checkpoint **2026-09-15 17:18:18 MSK**.

**Status: IMPLEMENTED_TESTED_PENDING_INDEPENDENT_REVIEW.**

## Done
- Adopted all nine library modules from accepted manifest06 without changing a byte; final hashes exactly match the previously verified source map.
- Adopted eight reviewed test files. Seven remain byte-identical. Generation test-only fixtures now call real library infer_v3 rather than importing the deferred parallel worker.
- Preserved all 16 original generator assertions (AST comparison after local-variable normalization). Worker integration body/assertions are retained with an explicit skip, not deleted.
- Added isolated-import regression contracts. Original RED: 10 FAIL/1 PASS. Final isolation cases: **11 PASS** with real source, no stubs.
- Focused final pytest: **99 PASS, 1 SKIPPED in 7.79s** (supervised wall7.964s;90s ceiling). Ruff: **18 files PASS**,0.041s.

## Explicitly NOT RUN FOR SCOPE
`tests/test_sports_v3_generation.py::test_native_worker_generates_new_v3_candidate_under_explicit_synthetic_gate` belongs to Stage F. Its worker module and production hook are NOT adopted. No claim that every test passed.

## Isolation and compatibility
- Import subprocess guards reject writes/secret .env access/network/SQLite/process execution. Known urllib3 IPv6 socket capability probe is denied, not granted. Library import does not load CLI/scheduler/final-comparison/parallel worker.
- Guarded production entrypoint imports do not load any of the nine new library modules.
- Six protected entrypoint/config hashes and all eight direct existing dependency hashes remained unchanged.
- Existing parent goal_probe_research regulation-score handling, package_quality cache, and strategy_comparison progress checkpoints retained; focused library tests pass against these parent versions. No obsolete child dependency was copied.
- No CLI/router/config/import-hook changes, no DB/jobs/consent/ledger/operator changes, no live calculation, no Git or publication. 5007 operations remain owned by parent; runtime state not rechecked in this task.

## Limits and handoff
- Synthetic unit tests exercise training/inference mechanics only; no real training, real fitted artifacts, historical replay, quality lift, Sports V3 activation or profitability is claimed.
- Review06 acceptance covered its exact deadline correction, not whole-model production qualification. This adoption/test-only delta still requires independent review.
- ACTIVE_PLAN and shared machine checklist were intentionally not changed while publication owns metadata. Parent can mark A IMPLEMENTED_TESTED, not REVIEW_ACCEPTED/COMPLETE, after consuming this receipt.
- Next: independent Stage A review, then separate publication worker. Stages B–F remain outside this assignment. No commands or owned processes running.

## Changed files
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_probability.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_draw_calibration.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_probability_features.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_feature_disposition.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_f4.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_f4_gate.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_f4_metrics.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_generation.py`
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v3_research_safety.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_probability.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_probability_features.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_f4.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_f4_metrics.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_generation.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_research_safety.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_f4_fit_binding.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_feature_disposition.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_library_isolation.py`
- `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/A-library-adoption.md`
- `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/A-library-adoption.json`

## Exact adopted source hashes
- `src/toto_ai/sports_stats/v3_probability.py`: `b9e91b89ec08e2d87d6a1d676857f2e48c6c7500558558dac8d8295ba7f43b26`
- `src/toto_ai/sports_stats/v3_draw_calibration.py`: `487b3155128debef428b4f2d884d59266f89c43302ab884ae43910c0aa646fd4`
- `src/toto_ai/sports_stats/v3_probability_features.py`: `9723dc218a56a0fca8545b8f9b1f08e2d9470ad7300c4c2f32018639cc00e4d5`
- `src/toto_ai/sports_stats/v3_feature_disposition.py`: `fc3e9df4f4a1730cc9547ae26b1af06fdbf734e54bd9380be36cd8b04b3dbf96`
- `src/toto_ai/sports_stats/v3_f4.py`: `d556803b7ef9df09986c785cd5ffcb3266d09c80df240d46cb2b0464ebb1e3f4`
- `src/toto_ai/sports_stats/v3_f4_gate.py`: `334f4bf5407d946ef1665efe23b4a622c38be5bb5891d8e827951769320c72fd`
- `src/toto_ai/sports_stats/v3_f4_metrics.py`: `291c10f762b301c4f876c7c6afc8724c684b91954c1c3d78692fde37c07cdd4e`
- `src/toto_ai/sports_stats/v3_generation.py`: `a4ca4fcbff013412859d08d0c8228e27988d262ed8d97336e1a0c811cd9c8f47`
- `src/toto_ai/sports_stats/v3_research_safety.py`: `4419d6ed8c61be0e7ed83fbce3c3c7a910b9531de926eadd1dd30541b9630b60`

JSON receipt includes all source/test/dependency/protected hashes, exact commands and output, skipped scope, and full test-only generator diff.
