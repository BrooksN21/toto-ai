# Durability correction — VERIFIED CANDIDATE, independent review pending

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906; 2026-09-06T16:09:04.188980+03:00. Not main-applied/activated/published.
Full replacement: CACHE_DURABLE_CANDIDATE.patch SHA256 `e914a0976e6434198ee4f2164c2877debf1caa33b20c959ed5d282b65aa05597`.
Delta from75bd: CACHE_DURABLE_DELTA_FROM_75BD.patch SHA256 `11b2d765d90a87120d2111d63773dd478d768ed3bc809e1c52818c7ba12c7af4`.
Manifest: CACHE_DURABLE_CANDIDATE_MANIFEST.json; mirror CACHE_DURABLE_CANDIDATE/.
Old75bd candidate and all its CLI bytes preserved. No retry/quota/lease redesign.
Claim/outcome: fsync content, exclusive link, fsync target directory and created
ancestor chain bottom-up through existing cache output root before collector/ack.
Directory fsync errors propagate; existing identical outcomes also sync before return.
RED3fail/18pass0.67s → GREEN21PASS0.76s; Ruff4PASS; audit blocked_actions[].
Tests verify filesystem call order and injected errors, NOT real power loss.

**Separate integration guard:** concurrent G1 main CLI changed; original guarded
before hashes are intentionally NOT rebound. Full replacement targets original
pre-G1 base. Euler must review this tiny delta, then separately compose the already
reviewed CLI correction with G1 and generate a fresh apply manifest. Never forceapply.
Mismatch details: `[{"path": "src/toto_ai/cli.py", "expected_before_sha256": "5b11f3c9cc2ac9feaddc6f935150fcbc55eeffba3aefae48640f0b8f4e29f88c", "actual_sha256": "d7cf47a91d07c0687290a0e3dfe9d5bc73a24759dee4f8e660a8716cf0d9e3fb"}]`.
Receipt/import hashes/repro harness: CACHE_DURABLE_IMPLEMENTATION_RECEIPT.json.
Build harness preserved: CACHE_DURABLE_BUILD_VERIFY.py (its final assembly stopped
safely on CLI mismatch; receipt records the verified original-base reconstruction).
No owned process. NEXT:Euler independent review; no code/main/seed action here.
