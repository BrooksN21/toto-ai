# TOTO-RECONCILE-DRY-RUN-READONLY-FIX-V1

Date: 2026-07-30

## Result

The CLI dry-run boundary is physically read-only.

- `reconcile-finished --dry-run` uses a SQLite read-only URI.
- `repair-canonical-raw --dry-run` uses the same read-only URI.
- Neither command invokes `init_db`, `create_all`, or migrations.
- A missing `drawing_reconciliation_states` table is empty optional state.
- Canonical RAW repair previews the importer delta without publishing RAW or
  result snapshots.
- Explicit apply mode still initializes the additive schema before mutation.

## TDD evidence

The new real-file regression initially failed:

- reconciliation added `drawing_reconciliation_states`;
- canonical repair could not satisfy the write-free preview contract.

After the fix, the focused lifecycle/reconciliation suite passed with 33
tests. The final full suite passed 1518 tests in 248.00 seconds; Ruff and
`git diff --check` passed. Coverage includes:

1. reconciliation dry-run with no reconciliation-state table;
2. reconciliation dry-run with an existing cooldown row;
3. canonical RAW repair dry-run;
4. apply mode creating the missing schema before its first mutation.

Every dry-run test compares:

- physical database SHA-256;
- ordered `sqlite_master`;
- row count for every user table;
- WAL and SHM existence/hash;
- absence of RAW, JSON state, and archive output.

## Network-free backup-copy smoke

Source:

`data/backups/toto-before-controlled-backfill-20260730T092227Z.db`

Physical SHA-256 before and after both commands:

`a117f28fe1d9e61f862191f179f3fcb8b05421e65b808fe9027ead71459ccc94`

Verified unchanged:

- 76 SQLite schema objects;
- 19 user-table row counts;
- no WAL;
- no SHM.

`reconcile-finished` selected drawing 4946 as `would_reconcile`, made no
network call, and created no state or archive path.

`repair-canonical-raw` previewed 171 importer-loss changes for drawing 4954
and created no archive path.

The production database was not used or changed.

## Operational decision

The previous controlled production backfill remains aborted. It is now safe to
repeat its dry-run on a fresh backup and compare the same physical/logical
evidence before any network apply.
