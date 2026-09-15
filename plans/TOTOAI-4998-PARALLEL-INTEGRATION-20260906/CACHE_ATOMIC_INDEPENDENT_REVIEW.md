# REQUEST_CHANGES — cache atomic durability

Exact candidate75bd7b86efcd20329375ad40b45055a2a75d7ca0fc107d5fb1f888af47abde1c.
Fresh18PASS0.73s; Ruff4PASS;4targets/49dependencies unchanged; no application/push.
P1: candidate goal_probe_collection.py:384–386 fsyncs pending file, then links final
name without fsync of the containing directory/new generation ancestor entries.
Atomic visibility is fixed, but a host/power crash after provider requests begin may
lose the published claim/reservation. Observed syscall probe: fsync_file → link;
no directory sync before return. Existing18cases exercise process interruption,
not durable-directory publication. This is a syscall-order proof, not an actual
power-loss experiment.
Required narrow correction: durably publish new directory entries and final claim
before collector entry; outcome likewise before reporting success. Inject directory
sync failures/order into focused tests. Existing exclusive link/flock mechanism and
accepted retry/quota rules need no redesign. Other accepted functional parts not
re-reviewed; exact delta contains helper/test/doc changes, no CLI delta.
Machine evidence: CACHE_ATOMIC_INDEPENDENT_REVIEW.json. No owned process.
