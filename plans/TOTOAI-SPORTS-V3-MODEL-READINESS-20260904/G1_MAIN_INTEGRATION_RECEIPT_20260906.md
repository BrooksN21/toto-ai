# G1 exact main integration — verified, unused

Task `TOTOAI-SPORTS-V3-MODEL-READINESS-20260904`. Finished 2026-09-06T10:54:58.152193+00:00.

- One immediate unchanged verifier → strict whitespace apply-check → exact patch apply. Guard: **READY_FOR_MAIN_APPLY, 2 paths / 32 dependencies**.
- Applied only accepted patch `/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/G1_MAIN_COMPATIBILITY.patch` (SHA-256 `0d43d19e764dc9d50437c64957a9802007f79a4b8de1842b49ba8c3cbba0dbf2`). No other G1 route applied.
- New `src/toto_ai/optimizer/exact_maximin_refinement.py`: absent → `b249971911e80d353ff719f0bd58e088c1ac4a183c4764ce32ed838147df62ee`.
- New `tests/test_exact_maximin_refinement.py`: absent → `8af5ddb92dc57b70d359bd91d367a41a85807c18c33f06c7b57b957476856504`.
- **G1 pytest:119 passed,3 existing size benchmarks deselected,0.81s.** Includes all15 unchanged independent probes, R1/R2 and stub-only166 control. No performance/profitability claim.
- **Current-main Ruff:PASS**, exact two files plus byte-identical temporary G1 probe; original foreign probe untouched.
- **Omitted F3 probes:16 passed,0.43s.** Exact prior receipt adaptation (MODEL path only), adapted SHA `d38fb8adfcecfb67c7ec8a3c73ae763ca3a0b5b02ea871e5b1d2b8ee7a762f06`. Original F3 SHA unchanged. Together with prior cleanup167 this covers183 cases; not a new combined183 run.
- All32 dependency hashes and loaded main import hashes preserved. O1 cleanup source/test/config hashes preserved. Guarded tests denied network/DB/out-of-temp writes; no blocked actions. Temporary harness removed; no owned process/session.

Full commands, outputs, original probe hashes, imports and before/after bindings: `/Users/turshevr/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/G1_MAIN_INTEGRATION_RECEIPT_20260906.json` (SHA-256 `bbc7eee1ecbd59f8417a98dd2003623526a5fd3e62967397e435a2ede7c8c700`).

**Blocker:none.** G1 remains an optional unused module: no initializer registration, forecast/scheduler/current4998 wiring, replay, real benchmark, authorization, DB/network or job action. No staging/commit/push/index write. No existing source changed; main memory left to the separate finalizer. Next: finalizer verifies this receipt and closes the memory checkpoint; do not reapply or activate.
