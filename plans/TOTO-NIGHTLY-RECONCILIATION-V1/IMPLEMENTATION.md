# TOTO-NIGHTLY-RECONCILIATION-V1

## Scope

Passive results-only reconciliation for recent finished drawings. It does not
generate packages, activate the betting scheduler, upload coupons, or place
bets.

## Runtime contract

- Local LaunchAgent schedule candidate: daily 03:20 machine local time
  (Europe/Moscow on the target Mac).
- Scope: latest 30 finished drawings, then incomplete/eligible filtering.
- Maximum network attempts: 8 exact captured drawing numbers.
- Force: disabled.
- Runtime bound: 240 seconds; request timeout 20 seconds and no in-run HTTP
  retries.
- Cooldown/quarantine: reused from `reconcile-finished`.
- Non-overlap: `data/operations/global-maintenance.lock`, also used by the
  morning dispatcher.
- Backup: online SQLite backup before apply, mode `0600`, integrity manifest,
  seven known-good copies retained.
- Every run writes timestamped report, state, and JSONL log.

## Exact selection protocol

1. Open SQLite physically read-only.
2. Select the last 30 finished drawings.
3. Run network-free reconciliation dry-run.
4. Capture at most eight eligible drawing numbers.
5. Repeat the read-only selection and abort on any drift or extra candidate.
6. If the capture is empty, return `DEFERRED` with zero network and no backup.
7. Create and validate the online backup.
8. Apply only the captured numbers, one bounded attempt each.
9. Run Data Health before/after plus SQLite quick/FK checks.

`source_incomplete` is a controlled `PARTIAL` result. It is not converted to
VOID and does not crash processing of other captured drawings.

## Generated artifacts

- `reports/nightly-reconciliation/run-nightly-reconciliation.sh`
- `reports/nightly-reconciliation/totoai-nightly-reconciliation.plist`

They are generate-only and were not installed or launched.

## Network-free rehearsal

`reports/rehearsal/nightly-reconciliation-v1-20260730T130000Z/`

- isolated SQLite copy;
- fake provider only;
- first run: one `15/15`, one `source_incomplete`, `PARTIAL`, two calls;
- second run: `DEFERRED/NOOP`, zero calls, no second backup;
- no package, scheduler activation, upload, or bet action.

## Installation checklist

Installation is deliberately outside this task.

1. Confirm full pytest, Ruff, and diff checks.
2. Inspect wrapper and plist bytes.
3. Confirm project path and `.venv/bin/python`.
4. Confirm the Mac timezone is Europe/Moscow.
5. Confirm no other maintenance process owns the global lock.
6. Take an operator backup of `data/toto.db`.
7. Install/load only with explicit operator approval.
8. Inspect the first run report before authorizing continued unattended use.

## Verification

- nightly/reconciliation/morning focused suite: 52 passed;
- nightly feature suite: 12 passed;
- full pytest: 1536 passed in 253.31 seconds;
- repository Ruff: passed;
- repository text whitespace check: passed;
- CLI help smoke: passed;
- no network, Git, main-database mutation, LaunchAgent install, or launch.
