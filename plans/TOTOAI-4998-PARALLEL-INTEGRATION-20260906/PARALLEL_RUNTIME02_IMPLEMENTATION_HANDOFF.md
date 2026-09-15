# Runtime02 / PR-1 — frozen for independent rereview

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906; 2026-09-06T20:29:52.038399+03:00. NOT ACCEPTED; not staged/published.

## Work summary
- Reproduced both exact independent failures before changes (2FAIL1.39s).
- Pin the original native-export SHA; re-read current canonical upload and operator record.
- Existing `_validated_actionable_operator_upload` reruns native expiry/authority/status/marker/CSV/archive validation at reuse and prepublication. Compare returned bytes and re-read current bytes after validator IO; never reseal substituted data.
- Actual sidecar publication route supplies the same validation callback before/after optional writes, also rechecks unchanged parallel authority and the clock. Lost validity yields terminal `SKIPPED_PRIMARY_CHANGED`; only newly created optional publication files removed, completed research and primary preserved.
- No search/category/score/bank changes or further optimization. No observer edits or live operator generation.

## Verification
101PASS3.15s: original58 scoped + unchanged22 independent +21 new PR1 regressions. Ruff13PASS (12candidate Python paths plus unchanged independent probe).
New probes cover real native positive checks, upload replace/delete/symlink, expiry/marker/source/authority invalidity, concurrent validator byte swap and returned-byte mismatch, expiry crossing, nine ranking/package/companion mutation cases and two terminal reuse failures. Native file checks are real; only archive DAO is in-memory, not a live DB. Older lightweight fixtures explicitly stub native validation; original independent test bytes are unchanged.
All commands bounded25s pytest/15s Ruff: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/runtime02/commands.json`.
No long replay. Historical foreground198.859s recomputed bothEV and is NOT LaunchAgent proof; runtime02 adds no fresh performance claim.

## Frozen artifacts
- Full13-path candidate: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/PARALLEL_RUNTIME02_IMPLEMENTATION.patch` SHA256 `152c92c8e068e971b5c926dc70234c2b57c3815c3396ac0ba195b56d5d46bbab`.
- Only PR-1 delta vs runtime01 (6paths): `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/PARALLEL_RUNTIME02_REVIEW_FIX.patch` SHA256 `1dfeb4fe709a8ed619619b3166dbd6930105598a24efe621f79dfe9a43468087`.
- Manifest: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/PARALLEL_RUNTIME02_IMPLEMENTATION_MANIFEST.json` SHA256 `1fbdbd82c0872f7f0b319c23570cc195b03ad70126d12ba0fb9f7171cd60321b`.
- Exact candidates/base copies: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/runtime02/candidate`, `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/runtime02/base`.
- runtime01 patch/captures and original reviewer-owned probe retained unchanged. Eight dependency hashes unchanged.

Changed in this job:
- `src/toto_ai/sports_stats/final_hybrid_comparison.py`
- `src/toto_ai/sports_stats/final_hybrid_sidecar.py`
- `tests/test_final_hybrid_runtime_contracts.py`
- `knowledge/parallel_runtime.md`
- `tests/test_final_hybrid_sidecar.py`
- `tests/test_final_hybrid_primary_validity.py`

Remaining: independent rereview of runtime02; publication is a separate authorized job. No blocker to handing off now.
