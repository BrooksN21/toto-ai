# TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1

Date: 2026-07-30
Result: **ABORTED / NO-GO**
Network reconciliation: **not started**
Automatic restore: **not performed**

## Why the run stopped

The required preflight and online backup succeeded. The subsequent
`reconcile-finished --dry-run` selected exactly the four allowed drawings:

- 4946
- 4955
- 4956
- 4958

However, the dry-run changed the production SQLite database. It added the
empty table `drawing_reconciliation_states`.

This violates the required dry-run contract and the explicit task safety rule.
The run therefore stopped before any TotoBrief request or analytical data
mutation. The backup was not restored automatically.

Root cause confirmed by read-only inspection:

```text
reconcile_finished_command
-> init_db(db)
-> Base.metadata.create_all(engine)
```

The CLI initializes/migrates the database before passing `dry_run=True` to the
reconciliation engine. The engine itself performs no network call in dry-run,
but the CLI database initialization is not read-only.

## Preflight

Main database:

`/Users/turshevr/toto-ai/data/toto.db`

Before dry-run:

- physical SHA-256:
  `5242945ace687adc59f2a6472bcf3c836075dbc88f47496a45756de6fe4f41fb`
- logical SHA-256:
  `ed0ec833114176f89628fd8bb49fca4f37dddac5fa57e900d5b6daf413b7142e`
- SQLite `quick_check`: `ok`
- foreign-key violations: `0`

## Backup

Backup:

`/Users/turshevr/toto-ai/data/backups/toto-before-controlled-backfill-20260730T092227Z.db`

- SHA-256:
  `a117f28fe1d9e61f862191f179f3fcb8b05421e65b808fe9027ead71459ccc94`
- size: `100835328` bytes
- mode: `0600`
- method: `sqlite3.Connection.backup`
- backup `quick_check`: `ok`
- backup foreign-key violations: `0`
- source SHA was unchanged during backup
- no WAL/SHM files existed at backup start

Manifest:

`/Users/turshevr/toto-ai/data/backups/toto-before-controlled-backfill-20260730T092227Z.manifest.json`

The backup has not been deleted or modified.

## Dry-run allowlist proof

Each drawing was invoked independently with `from == to`, `batch-size=1`, and
`--dry-run`.

| Drawing | Selected | Status | Network |
|---:|---:|---|---:|
| 4946 | 1 | `would_reconcile` | 0 |
| 4955 | 1 | `would_reconcile` | 0 |
| 4956 | 1 | `would_reconcile` | 0 |
| 4958 | 1 | `would_reconcile` | 0 |

No drawing outside the allowlist was selected.

## Unexpected database delta

After dry-run:

- physical SHA-256:
  `d94738e26cb35d1f7768a8621f30d0111c2945851bb7165dc6490c57863d2c42`
- logical SHA-256:
  `1e207b8e4f12873e9240248483a17d2abb37268aa0399a7b95ea1885ccda166b`
- SQLite `quick_check`: `ok`
- foreign-key violations: `0`

Exact logical delta:

- added table: `drawing_reconciliation_states`
- rows in added table: `0`
- removed tables: none
- changed rows in all pre-existing tables: none
- reconciliation state rows: `0`
- new RAW observations: none
- state-file writes: none

Per-drawing analytical delta:

| Drawing | Names/quotes/results/snapshots changed | Cooldown state |
|---:|---|---|
| 4946 | no | none |
| 4955 | no | none |
| 4956 | no | none |
| 4958 | no | none |

## Data Health

The required pre health reports were saved for 4946–4958:

`run-20260730T092227Z/pre-health/`

Because the operation aborted before network reconciliation, no legitimate
post-backfill health comparison exists. The only database change is the empty
schema table above; drawing health is unchanged.

## Idempotency

The required second non-force apply was not run. Running it would have required
first performing the network mutation, which was prohibited after the safety
failure.

Therefore:

- network calls in this task: `0`
- API/TLS/429/5xx errors: none
- cooldown state for 4946: not created
- complete states for 4955/4956/4958: not created

## Decision

**NO-GO** for this production backfill and for the next limited wave.

Before retrying:

1. make `reconcile-finished --dry-run` open the database read-only and never
   invoke schema creation/migration;
2. add a regression test proving byte/logical/row-count purity of dry-run;
3. separately apply the required schema migration through an explicit,
   backed-up migration operation;
4. repeat this controlled task from a new backup.

No scheduler, LaunchAgent, package, marker, upload, or bet was touched.
