# ACCEPT — fsync delta only

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Candidate e914a097…,
delta11b2d765…; full SHA256 values, exact byte-chain proof and commands in adjacent JSON.

Reviewed only Leibniz directory-durability delta, not self-acceptance of previous
functional/atomic implementation. Content fsync precedes exclusive link;
final directory and ancestor chain sync bottom-up through the existing output
root before collector entry/outcome acknowledgement. Directory open/fsync errors
propagate; descriptors close in finally. Existing identical outcome also syncs
before returning. No swallowed failure or external request before claim sync.

Fresh4 scoped cases PASS: full ordering, claim-sync failure/no collector,
outcome-sync failure/no acknowledgement, independent existing-identical-record
sync failure/no overwrite. Ruff3 PASS; zero audit-denied attempts. No broad21/96
rerun. Exact75bd→delta→e914 reconstruction and all mirrored after hashes match;
CLI bytes unchanged by this delta. Filesystem-call evidence, not power-loss testing.

NOT applied. Current main G1 CLI requires separate exact2hunk cache composition
and fresh guard; never replace CLI wholesale or force old before hashes.
No API/DB/jobs/seed/authority/activation. Next: parent-owned composition/integration;
operational activation stays gated by separate wrapper review. No owned process.
