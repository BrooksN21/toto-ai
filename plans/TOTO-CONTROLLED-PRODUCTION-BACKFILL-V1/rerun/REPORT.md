# TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1-RERUN

Run: `20260730T100317Z`

## Decision

**GO** for the next small, explicitly allowlisted, backed-up reconciliation wave using the same dry-run/apply/idempotency protocol.

**NO-GO** for an unrestricted full-history backfill or automatic nightly installation yet. The next wave must remain bounded and observed; source-incomplete drawings must continue using cooldown/quarantine.

## Scope and safety

- Main DB: `/Users/turshevr/toto-ai/data/toto.db`
- Strict allowlist: `4946, 4955, 4956, 4958`
- No scheduler, package, settlement, marker, upload, or betting command was run.
- No drawing outside the allowlist changed. See `database-delta-scope-proof.json`.
- No TLS bypass was used.
- No destructive restore was performed.
- No production-code edit, Git commit, or push was performed by this rerun.

## Backup

- Path: `/Users/turshevr/toto-ai/data/backups/toto-before-controlled-backfill-rerun-20260730T100317Z.db`
- SHA-256: `49e43dbf3cfe54c0342e2bbba27c376e03ea9e293c03b3edda4ac86646121426`
- Size: `100855808` bytes
- Mode: `0600`
- Method: `sqlite3.Connection.backup`
- Backup `quick_check`: `ok`
- Backup FK violations: `0`
- Manifest: `backup-manifest.json`

## Main DB SHA stages

| Stage | SHA-256 |
|---|---|
| Baseline | `d94738e26cb35d1f7768a8621f30d0111c2945851bb7165dc6490c57863d2c42` |
| After online backup | `d94738e26cb35d1f7768a8621f30d0111c2945851bb7165dc6490c57863d2c42` |
| After dry-run | `d94738e26cb35d1f7768a8621f30d0111c2945851bb7165dc6490c57863d2c42` |
| After first apply | `f2f2c2ede3fc6bd8f0ba7f52240d3800fa31a7516775fd4361a2e3e38905110c` |
| After idempotency apply | `f2f2c2ede3fc6bd8f0ba7f52240d3800fa31a7516775fd4361a2e3e38905110c` |

Final SQLite `quick_check=ok`, FK violations `0`, WAL/SHM absent.

## Dry-run proof

Each drawing was selected through an exact one-number range. Aggregate selected numbers were exactly the allowlist.

- Network calls: `0`
- Main physical SHA: unchanged
- Logical DB SHA: unchanged
- Schema and all table row counts/hashes: unchanged
- WAL/SHM: absent before and after
- Reconciliation state files created: `0`

See `dry-run-proof.json` and `dry-run/*.stdout.txt`.

## First apply

Exactly four drawing-detail HTTP requests were made, one per allowlisted drawing. There were no retries, HTTP/API errors, 429/5xx errors, transport errors, or TLS bypass.

`4946` returned controlled CLI exit code `2` because the source remained incomplete `14/15`; this is an expected business classification, not a transport/API failure. Processing then continued only for the remaining allowlisted drawings.

| Drawing | Result | Main changes |
|---:|---|---|
| 4946 | `source_incomplete`, 14/15 | Added immutable RAW evidence and reconciliation cooldown. Missing event order remains `11` (match #12). No VOID synthesized. |
| 4955 | `complete`, 15/15 | Restored 15 names/championships, 15 quote rows, result statuses, RAW-linked complete result snapshot. |
| 4956 | `complete`, 15/15 | Restored 15 names/championships, 15 quote rows, result statuses, RAW-linked complete result snapshot. |
| 4958 | `complete`, 15/15 | Restored all 15 results/scores/statuses, refreshed quotes, added RAW-linked complete result snapshot. |

4946 next eligible attempt: `2026-07-30T16:05:22.722261+00:00` (`19:05:22` Moscow). Retry state: `cooldown`; attempts: `1`; VOID count: `0`.

RAW archive files changed from `36` to `44` (four JSON + four metadata files). Four `drawing_raw_snapshots`, three linked complete `drawing_result_snapshots`, and four reconciliation states were added.

## Health delta, drawings 4946-4958

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Historical-inventory healthy | 0 | 3 | +3 |
| Probability-backtest healthy | 3 | 6 | +3 |
| Result-settlement healthy | 0 | 3 | +3 |
| Prospective-generation healthy | 10 | 12 | +2 |
| Finished incomplete-result drawings | 8 | 7 | -1 |
| Missing terminal results | 92 | 77 | -15 |
| Valid-pool drawings | 10 | 12 | +2 |
| Complete-BK drawings | 10 | 12 | +2 |
| RAW-snapshot drawings | 6 | 9 | +3 |
| Result-snapshot drawings | 0 | 3 | +3 |
| Reconciliation tracked | 0 | 4 | +4 |
| Reconciliation complete | 0 | 3 | +3 |
| Reconciliation cooldown | 0 | 1 | +1 |

Full reports are under `pre-health/`, `post-health/`, and `health-and-drawing-delta.json`.

## Scope proof

Comparing the online backup with the final main DB found changes only in:

- `events`
- `quotes`
- `drawing_raw_snapshots`
- `drawing_result_snapshots`
- `drawing_reconciliation_states`

Every changed/added row belongs to drawing IDs `11955, 11977, 11981, 11986`, corresponding exactly to `4946, 4955, 4956, 4958`. No other table or drawing changed. Packages, settlements, scheduler data, and bets were untouched.

## Idempotency proof

Second apply used `--no-force` semantics:

- 4946: cooldown skip; network `0`.
- 4955, 4956, 4958: complete skip; network `0`.
- Main physical SHA: unchanged from first apply.
- Logical table hashes and row counts: unchanged.
- RAW count/tree hash: unchanged (`44`, `3697f938e9193893a000a6e9469ddcc4f79a8d58f733331afcf33f8924e314e9`).
- API errors: `0`.

See `idempotency-proof.json` and `idempotency/*.stdout.txt`.

## Remaining limitations

- 4946 is genuinely source-incomplete at 14/15 and remains unsuitable for complete-result research/settlement.
- This proves a small controlled operational batch, not the safety of an unrestricted 2,199-drawing backfill.
- The current working tree contains the earlier lifecycle/cooldown/dry-run implementation changes; this operational task intentionally did not commit or push them.
