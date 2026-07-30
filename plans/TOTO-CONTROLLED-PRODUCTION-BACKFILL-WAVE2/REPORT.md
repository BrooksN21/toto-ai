# TOTO-CONTROLLED-PRODUCTION-BACKFILL-WAVE2

Run: `run-20260730T104031Z`

## Decision

**NO-GO for installing unattended nightly reconciliation yet.**

The bounded network reconciliation itself behaved correctly: seven exact
requests, three complete recoveries, four source-incomplete cooldowns, no
transport/API errors, and a zero-request repeat pass. However, the required
whole-command idempotency check exposed one database mutation in the repeated
offline repair. Per the stop-on-defect rule, the run stopped without restore
or further apply.

The next task must make `repair-canonical-raw --apply` preserve the existing
`drawing_raw_snapshots.classification` when `logical_changes=0`, add a
regression test, and repeat this wave's idempotency proof before authorizing
nightly installation.

## Frozen scope

Network allowlist:

```text
4940 4945 4949 4950 4951 4952 4957
```

Offline repair:

```text
4954
```

- Network maximum requested: 8.
- Network drawings used: 7.
- Changed drawings: exactly the eight entries above.
- Unexpected changed drawings: 0.
- Archived packages, package settlements, preparations, pins, collection
  runs, and sports-statistics tables: unchanged.

The exact frozen criteria are in `ALLOWLIST.md` and `allowlist.json`.

## Backup and baseline

Main database before apply:

```text
path:   /Users/turshevr/toto-ai/data/toto.db
sha256: f2f2c2ede3fc6bd8f0ba7f52240d3800fa31a7516775fd4361a2e3e38905110c
```

Online backup:

```text
path:   /Users/turshevr/toto-ai/data/backups/toto-before-controlled-backfill-wave2-20260730T104031Z.db
sha256: 27cf80af6c6ed758b7780a50673357ffee602eb140a2c6ba00b7ef4def512943
size:   100892672 bytes
mode:   0600
```

Backup checks:

- `quick_check = ok`;
- foreign-key violations: 0;
- source SHA before/after online backup: identical;
- no WAL/SHM sidecars.

No automatic restore was performed.

## Read-only dry-run proof

Each of the seven network commands selected exactly one requested drawing with
`would_reconcile` and `dry_run_no_network`.

The corrected 4954 offline dry-run selected exactly 4954 and reported:

```text
classification: importer_loss_recoverable_local
logical_changes: 171
status: would_repair
```

Before/after dry-run:

- database SHA: unchanged;
- schema: unchanged;
- all table row counts and logical hashes: unchanged;
- every per-drawing hash: unchanged;
- RAW inventory and hashes: unchanged;
- WAL/SHM: absent;
- reconciliation state files: not created;
- HTTP requests: 0.

## First apply results

HTTP requests: **7** total, one per exact network drawing.

- retries: 0;
- HTTP 429/5xx: 0;
- TLS errors: 0;
- transport errors: 0;
- TLS bypass: not used.

| Drawing | Final classification | Results | Names | Quotes | Pool/BK | Result snapshot |
|---:|---|---:|---:|---:|---:|---:|
| 4940 | complete | 0→15 | 15 | 15 | 15/15 | 0→1 |
| 4945 | source_incomplete, cooldown | 0→14 | 15 | 15 | 15/15 | 0 |
| 4949 | source_incomplete, cooldown | 0→14 | 15 | 15 | 15/15 | 0 |
| 4950 | source_incomplete, cooldown | 0→14 | 15 | 15 | 15/15 | 0 |
| 4951 | complete | 0→15 | 15 | 15 | 15/15 | 0→1 |
| 4952 | complete | 0→15 | 15 | 15 | 15/15 | 0→1 |
| 4954 | offline repaired | 14 + 1 VOID unchanged | 0→15 | 0→15 | 0→15 / 0→15 | existing |
| 4957 | source_incomplete, cooldown | 0→14 | 15 | 15 | 15/15 | 0 |

The four incomplete upstream payloads were not converted to VOID and were not
given result snapshots. All eight content-addressed RAW records verify against
their hashes. Result snapshots for 4940, 4951, 4952, and the existing 4954
snapshot also verify.

No selected drawing was classified as source-missing or transient.

## Data Health delta

Full database remained at 2,200 drawings during this operation.

| Metric | Before | Final | Delta |
|---|---:|---:|---:|
| historical-inventory healthy | 3 | 6 | +3 |
| probability-backtest healthy | 1,654 | 1,657 | +3 |
| result-settlement healthy | 3 | 6 | +3 |
| prospective-generation healthy | 1,984 | 1,985 | +1 |
| finished drawings with incomplete results | 370 | 367 | −3 |
| missing terminal outcomes | 755 | 654 | −101 |
| valid Pool drawings | 1,984 | 1,985 | +1 |
| complete BK drawings | 2,199 | 2,200 | +1 |
| result-snapshot drawings | 3 | 6 | +3 |
| reconciliation cooldown drawings | 1 | 5 | +4 |

For the selected range `4940..4957`:

- missing terminal outcomes: `107 → 6`;
- probability-backtest healthy: `9 → 12`;
- prospective-generation healthy: `17 → 18`;
- result-settlement healthy: `2 → 5`.

The remaining six missing outcomes in that range are the existing 4946
source-incomplete result plus one missing result in each of
4945/4949/4950/4957 and another pre-existing incomplete drawing in the range.

## Idempotency result and defect

Network repeat:

- 4940, 4951, 4952: complete, `selected=0`;
- 4945, 4949, 4950, 4957: cooldown, no request;
- HTTP requests: **0**;
- analytical rows: unchanged;
- RAW inventory and bytes: unchanged.

Offline repair repeat:

- reported `logical_changes=0` and `status=no_change`;
- nevertheless changed one existing
  `drawing_raw_snapshots.classification` value for 4954:

```text
importer_loss_recoverable_local → source_incomplete
```

Nothing else changed in the repeat pass. This is an evidence-metadata
idempotency defect, not a result/name/quote mutation, but it violates the
explicit zero-change acceptance requirement. The final database was left as-is
and no restore was attempted.

## Final database integrity

```text
sha256: a98eeeb8ec2a7c8121589edace4c7a72c144893f330175277cf205bae995650e
size:   100933632 bytes
quick_check: ok
foreign-key violations: 0
WAL/SHM: absent
```

Scheduler state, generated packages, settlements, betting markers, uploads,
and bets were untouched.

## Artifacts

- `allowlist.json`, `ALLOWLIST.md`
- `run-20260730T104031Z/backup-manifest.json`
- `run-20260730T104031Z/state-*.json`
- `run-20260730T104031Z/db-audit-*.json`
- `run-20260730T104031Z/drawings-*.json`
- `run-20260730T104031Z/per-drawing-delta.csv`
- `run-20260730T104031Z/per-drawing-delta.json`
- `run-20260730T104031Z/data-health-delta.json`
- `run-20260730T104031Z/scope-check.json`
- `run-20260730T104031Z/evidence-verification.json`
- pre/final Data Health reports and command logs

No raw payload or secret is stored under this plan directory.
