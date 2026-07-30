# TOTO-CONTROLLED-PRODUCTION-BACKFILL-WAVE3

## Decision

- **GO** for bounded nightly reconciliation under the existing no-force, cooldown/quarantine, low-rate, exact-selection, RAW-first and non-betting controls.
- **NO-GO** for unrestricted full-history backfill or any force mode.

Wave 3 had no safety defect. One drawing was fully recovered; seven were proven source-incomplete and placed in cooldown without invented results or VOID.

## Frozen allowlist

Frozen before network access: **4939, 4499, 3643, 3351, 3341, 3292, 2763, 2762**.

All eight were the newest eligible `all_results_missing` drawings below 4940 under the approved class-priority rule. Zero-pool-only drawings without missing results were excluded.

## Backup

- Path: `/Users/turshevr/toto-ai/data/backups/toto-before-controlled-backfill-wave3-20260730T113035Z.db`
- SHA-256: `205d948dfb8da8bd9b7b08efa5b8f4959e3ec03e40315529222cc1114066acfa`
- Size: 100933632 bytes
- Mode: `0o600`
- Backup `quick_check`: `ok`
- Backup FK violations: 0

## Read-only dry-run proof

All checks passed:

- source database SHA/size unchanged;
- schema and all row counts unchanged;
- deterministic logical checksum unchanged;
- exact per-drawing state unchanged;
- RAW inventory unchanged;
- WAL/SHM unchanged;
- no per-drawing state files written;
- only the exact frozen allowlist was selected;
- network calls: 0.

## Network apply

- Exact detail HTTP requests: **8**
- Retries: **0**
- HTTP/TLS/transport errors: **0**
- TLS bypass: **not used**
- Drawings outside allowlist mutated: **0**

| Drawing | Result | Terminal | Pool | BK | RAW | Result snapshot | State |
|---:|---|---:|---:|---:|---:|---:|---|
| 4939 | repaired | 15/15 | 15/15 | 15/15 | 1 | 1 | complete |
| 4499 | source_incomplete | 0/15 | 0/15 | 15/15 | 1 | 0 | cooldown |
| 3643 | source_incomplete | 0/15 | 15/15 | 15/15 | 1 | 0 | cooldown |
| 3351 | source_incomplete | 0/15 | 15/15 | 15/15 | 1 | 0 | cooldown |
| 3341 | source_incomplete | 0/15 | 15/15 | 15/15 | 1 | 0 | cooldown |
| 3292 | source_incomplete | 0/15 | 15/15 | 15/15 | 1 | 0 | cooldown |
| 2763 | source_incomplete | 0/15 | 15/15 | 15/15 | 1 | 0 | cooldown |
| 2762 | source_incomplete | 0/15 | 15/15 | 15/15 | 1 | 0 | cooldown |

### Per-drawing outcome

- **4939:** fully recovered to 15/15 with immutable RAW and complete result snapshot.
- **4499, 3643, 3351, 3341, 3292, 2763, 2762:** TotoBrief returned 0/15 terminal results. Each exact payload was archived and verified; state is `source_incomplete/cooldown`. No result or VOID was invented.
- **4499:** source still has zero-valued pool, so it remains unsuitable for probability use despite complete BK.

All eight archived RAW records passed `RawArchive.verify()`.

## Data Health delta (full database)

| Metric | Before | After | Delta |
|---|---:|---:|---:|
| Historical-inventory healthy | 6 | 7 | +1 |
| Probability-backtest healthy | 1657 | 1658 | +1 |
| Settlement healthy | 6 | 7 | +1 |
| Prospective-generation healthy | 1985 | 1985 | +0 |
| Finished drawings with incomplete results | 367 | 366 | -1 |
| Missing terminal results | 654 | 639 | -15 |
| RAW snapshot drawings | 18 | 25 | +7 |
| Result snapshot drawings | 6 | 7 | +1 |

## Idempotency repeat

The exact non-force apply was repeated with network unavailable.

- HTTP requests: **0**
- complete drawing selected for network: 0
- seven incomplete drawings: skipped by persisted cooldown
- database SHA unchanged
- schema/row counts/logical checksum unchanged
- RAW and reconciliation state unchanged
- WAL/SHM unchanged

## Non-betting boundaries

The following tables are byte-logically unchanged from baseline:

- `archived_packages`
- `package_settlements`
- `drawing_preparations`
- `drawing_event_pins`
- `drawing_pin_sets`
- `drawing_pin_set_items`

No scheduler, package generation, settlement, marker, upload or bet command was run.

## Limits

This wave demonstrates operational safety, not profitability or complete source history. Seven of eight selected old drawings remain unrecoverable from the current TotoBrief response and must stay excluded from analyses requiring results.
