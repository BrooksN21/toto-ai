# Sports history backfill: input-validation boundary

2026-09-05; isolated implementation pending separate review/integration.

`backfill_sports_history_manifest` must validate every manifest snapshot and its
hash-bound source/identity/as-of inputs before opening or initializing a writable
database. Keep the constructed snapshots in memory for the persistence phase;
do not reopen/reparse input sources after initialization.

If no snapshot passes input validation, an absent DB must remain absent and an
existing DB (including old schema) must remain byte-identical. `validate_only`
must not open/initialize/migrate the database for valid or invalid inputs.
Audit output is still written to the explicitly contained output directory.

Preserve the existing per-snapshot PARTIAL contract: once the entire manifest
has been checked, valid snapshots may be persisted while rejected snapshots
retain their original manifest positions and errors. This is not a new
all-or-nothing transaction over the entire manifest. Existing per-snapshot
storage atomicity and semantic retry/conflict rules are unchanged.

Regression evidence must inspect DB bytes/absence directly, including sidecar
file presence; it must not call `init_db` merely to assert an empty database.
Test both old-schema rejection without migration and successful valid write
with required initialization/migration. A spy on the real initialization call
checks ordering; actual synthetic SQLite writes/queries verify persistence.

This boundary concerns input rejection. Storage/runtime failures after valid
preflight are still governed by the existing storage transaction, not a promise
to roll back prior schema migrations or independent successful snapshots.

Evidence and exact patch:
`plans/TOTOAI-4996-4997-RECOVERY-20260904/P2_IMPLEMENTATION_REPORT.md`.
