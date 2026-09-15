# Delivery observer — review fix02

Task `TOTOAI-4998-PARALLEL-INTEGRATION-20260906`. Implementation only; **pending independent rereview**, no rollout/publication.

- Full frozen patch: `DELIVERY_OBSERVER_CANDIDATE02.patch`, SHA256 `f244c0873f5c43dce193af093fc7ddf3656f78753580ea6ba7f4c5b903cd2579`.
- Delta from reviewed candidate01: `DELIVERY_OBSERVER_DELTA01_TO_02.patch`, SHA256 `15ad627bc37ba9e895aae0123ce564f01ecb27e1e1f2a7c816ce844bb0617788`.
- Exact four before/after guards and eight read-only dependency guards: `DELIVERY_OBSERVER_CANDIDATE02.json`. Both patches reconstructed/verified exactly.

## Fixes
DO-1: reject links before resolve; walk/open pinned no-follow directory descriptors, exclusive temp + fsync + directory-relative atomic replace, guarded history append. Ancestor-swap regression preserves unrelated target bytes.
DO-2: reject `..`, symlink ancestry and normalized output escapes.
DO-3: verify current primary control-copy hash, exact run source/archive/final-input payload/probability chain, report seal/file hash and selected package/ranking bindings. Invalid optional chain leaves current valid primary actionable.
DO-4: support native ranking with **no drawing fields**; require actual plan-file/input/probability/package bindings; no inline/unbound ranking accepted. Missing proof never delays primary.

## Actual verification, no hidden regression suppression
- Original immutable independent copy: **8 failed / 7 passed** before corrections.
- Focused final: **73 passed in2.69s**; Ruff **3 clean**.
- Source-owned equivalents of all15 independent cases: **15 passed in0.92s**, already included in73.
- Unmodified reviewer file against updated shared helper: **10 passed /5 failed**. Three tests stop in `mkdir` because the valid helper now creates native inputs; native-schema positive has only dummy hashes/no chain; last test spies obsolete `Path.replace`. No tests skipped/xfail/assertions removed. Detailed logs + exact fixture/spy amendments in `DELIVERY_OBSERVER_REVIEW_FIX02_RECEIPT.json`. Reviewer must assess these changes, not treat unmodified15 as green.
- Seven extra native-chain substitutions, five ranking-binding substitutions, four link destinations and ancestor-swap check supplement the15 cases.
- Initial focused guard incorrectly rejected integer-fd `fchmod` (6 harness errors); tracked-fd guard fixed, full suite rerun. Import-time urllib3 localhost socket.bind **denied**, no successful network/DB.

## Boundaries / next owner action
Only four owned files changed. Shared memory handed to finalizer, no concurrent update. No actual coupons generated, runtime changes, archive edits, DB/API, stage/commit/push. Existing entity-bridge JSON/MD and user-reported owner wager evidence retained. No payout/profit or host-delivery claim.

Return frozen02 for independent read-only rereview; rollout/publication remain separate.
