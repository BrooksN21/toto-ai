# Cache atomic publication — IMPLEMENTED, INDEPENDENT REVIEW PENDING

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Candidate saved under this task;
**NOT applied to main, NOT independently accepted, no publication/activation**.

## Exact scope

The frozen f817f2d6… functional correction is retained. Only its claim/outcome
publication changes: complete fsynced JSON is prepared under a unique same-directory
.pending name, then atomically hard-linked to its immutable final name. Existing
final bytes are never overwritten; exclusive claims still reject an existing name.
Flock spans reservation/collection/publication unchanged. A crash before linking
has no published claim and cannot have started provider requests; a crash while
writing outcome leaves the complete claim eligible for existing lease recovery.
Pending files remain append-only evidence, not committed metadata. No retry, quota,
lease, deadline or probability redesign; other record publication paths unchanged.

CLI bytes are exactly those of the previous corrected candidate: only the approved
helper import and status-adapter substitution relative to current main. No MODELS
G1 hunks or Leibniz history code changed. Updated manifest binds current helper/test
bytes73f2c05d…/c0cf0f85…; original rejected and corrected artifacts are untouched.

## Bounded proof

- Fresh RED on exact f817…:2 atomic-publication failures /16 PASS.
- GREEN:18 PASS in0.61s: original8 +8 lease/quota/status/concurrency delta cases
  +2 publication-crash probes. Crash injection recognizes both old final-name
  writes and new pending-name writes, so failures are not hidden by renaming.
- Ruff4 PASS, no rule/config/ignore changes.
- Exact reconstructed patch/manifest guard PASS4targets/49dependencies against
  current main HEAD. READY_FOR_MAIN_APPLY is mechanical, not independent ACCEPT.
- Main target/dependency bytes unchanged after verification. No network, DB,
  source collection, jobs, authorization, seed, scheduler or Git index mutation.
  Tests audit-denied network/DB/outside-temp writes;0 blocked actions attempted.
- No owned process remains. Subprocess bounds25s tests/15s Ruff.

## Review/adoption artifacts

Full replacement: CACHE_ATOMIC_CANDIDATE.patch
SHA256: 75bd7b86efcd20329375ad40b45055a2a75d7ca0fc107d5fb1f888af47abde1c
Delta from f817…: CACHE_ATOMIC_DELTA_FROM_F817.patch
SHA256: 0a4cc7d84aface3b98bfa07d3660f8e8b420ac4ad9d9e60feb62b32bfaec3968
Fresh main manifest: CACHE_ATOMIC_CANDIDATE_MANIFEST.json
Receipt, runtime import hashes, guards and exact red/green harness:
CACHE_ATOMIC_IMPLEMENTATION_RECEIPT.json
Candidate mirror: CACHE_ATOMIC_CANDIDATE/
Own reproducible assembly harness: CACHE_ATOMIC_BUILD_VERIFY.py
Independent-style fault probes: test_failed_goal_cache_atomic_publication.py
Original review probes/reports unchanged; portable crash cases also embedded in
candidate tests. No broad119/183-suite run.

Before any separately authorized application use the existing strict read-only
VERIFY_MAIN_INTEGRATION.py with this manifest and /Users/turshevr/toto-ai root;
apply the full replacement only, never the delta to main. Recheck the manifest if
another writer changes a target/dependency. Review remains required.

Before/after SHA256:
- `src/toto_ai/sports_stats/goal_probe_collection.py`: `1c1d5378700d1f4563a051142cf21eac66ebb5c1fa39c8c521c774192202eb62` → `a340762a34bf8c2f8e2257feb01b29d5e3553b3dc5bf0d44fd6b784b22aa7814`.
- `tests/test_goal_probe_collection.py`: `f70be1a4a1d22024b291583048e9a50d239901145137c388e00370a40e5ea504` → `a56288231cd906b28c00665e7071c5b2c3dd8f474d0c96efb568b24415adb8e3`.
- `knowledge/goal_probe_failed_cache_boundary.md`: `None` → `cc37805ed471921516e8846b8d98d8239b201e986bde70cb797b89bc8fd05687`.
- `src/toto_ai/cli.py`: `5b11f3c9cc2ac9feaddc6f935150fcbc55eeffba3aefae48640f0b8f4e29f88c` → `bf3188aa7cfa60767404d5fd030673a6d9b529dc6e67d8af8880af9a82fc54f1`.

DONE: exact two crash holes fixed in review-only candidate with fresh red/green.
BLOCKER: independent review pending. NEXT: independent review of patch75bd7b86…;
no adoption, fresh seed activation or further implementation by this worker.
