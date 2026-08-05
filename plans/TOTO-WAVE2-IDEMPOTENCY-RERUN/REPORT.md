# TOTO-WAVE2-IDEMPOTENCY-RERUN

Run: `run-20260730T111538Z`

## Decision

**GO for wave 3 only as another small, explicit, backed-up allowlist using the same protocol.**

**NO-GO for unattended nightly reconciliation until wave 3 passes its own scope, network, integrity, and idempotency checks.**

The corrected offline classification path passed. The only database mutation in this task was the authorized one-time metadata normalization for drawing 4954. The network reconciliation allowlist made zero HTTP requests because complete drawings and cooldown drawings were skipped before transport.

## Frozen scope

Network reconciliation:

```text
4940 4945 4949 4950 4951 4952 4957
```

Offline repair:

```text
4954
```

No other drawing was selected or changed.

## Backup

```text
path:   /Users/turshevr/toto-ai/data/backups/toto-before-wave2-idempotency-rerun-20260730T111538Z.db
sha256: cc8704c46f276ed953c73e6af0dff7244f6400e6558ae0d44ab659c2de62cb5c
size:   100933632 bytes
mode:   0o600
```

- online SQLite backup;
- source SHA before/after backup identical;
- backup `quick_check = ok`;
- foreign-key violations: 0;
- WAL/SHM absent before backup.

## SHA stages

| Stage | SQLite SHA-256 | Logical SHA-256 |
|---|---|---|
| Pre | `a98eeeb8ec2a7c8121589edace4c7a72c144893f330175277cf205bae995650e` | `2ae46738f73c64183398bf26f843a1be5361bb940fb0d7b540405d2eef9331f0` |
| Post dry-run | `a98eeeb8ec2a7c8121589edace4c7a72c144893f330175277cf205bae995650e` | `2ae46738f73c64183398bf26f843a1be5361bb940fb0d7b540405d2eef9331f0` |
| Post offline normalization | `4a77aa7fb1b6a5417c7c466231419fc03bd40a5177dc04f659fef4e22afcfeff` | not separately captured |
| Post network skips | `4a77aa7fb1b6a5417c7c466231419fc03bd40a5177dc04f659fef4e22afcfeff` | `2a136d7306b4840c585be720ad41e07032c4e6000f019825d1fab287a4f2998d` |
| Final repeat | `4a77aa7fb1b6a5417c7c466231419fc03bd40a5177dc04f659fef4e22afcfeff` | `2a136d7306b4840c585be720ad41e07032c4e6000f019825d1fab287a4f2998d` |

Dry-run proved physical SHA, schema, row counts, logical hash, all drawing hashes, and RAW inventory unchanged.

## Exact state transitions

| Drawing | Transition |
|---:|---|
| 4940 | unchanged; already `complete`, selected=0 |
| 4945 | unchanged; `source_incomplete/cooldown`, skipped |
| 4949 | unchanged; `source_incomplete/cooldown`, skipped |
| 4950 | unchanged; `source_incomplete/cooldown`, skipped |
| 4951 | unchanged; already `complete`, selected=0 |
| 4952 | unchanged; already `complete`, selected=0 |
| 4954 | RAW snapshot `0d8b49…d6bb`: `source_incomplete -> offline_repair_recovered` |
| 4957 | unchanged; `source_incomplete/cooldown`, skipped |

For 4954:

- first apply: `logical_changes=1`, `status=repaired`;
- only `drawing_raw_snapshots.classification` changed;
- events, quotes, result snapshot, reconciliation state, row counts, schema and RAW files did not change;
- event 15 remained `result='*'`, score empty, preserving the existing terminal VOID evidence;
- no other drawing hash changed.

## Network apply

HTTP requests: **0**.

- 4940/4951/4952 were already complete and were not selected;
- 4945/4949/4950/4957 were skipped by existing cooldown;
- no transport, retry, API, TLS, RAW, state or analytical mutation occurred;
- no network permission was requested or needed.

## Repeat/idempotency proof

The exact offline and network commands were repeated:

- 4954: `logical_changes=0`, `status=no_change`, classification remained `offline_repair_recovered`;
- network HTTP requests: 0;
- SQLite SHA unchanged across the repeat: `4a77aa7fb1b6a5417c7c466231419fc03bd40a5177dc04f659fef4e22afcfeff`;
- logical SHA unchanged across the repeat: `2a136d7306b4840c585be720ad41e07032c4e6000f019825d1fab287a4f2998d`;
- reconciliation rows unchanged;
- all drawing hashes unchanged;
- RAW inventory unchanged at 86 files / 250872 bytes;
- schema and all table row counts unchanged.

## Data Health and integrity

Data Health before and after is exactly identical, including every per-drawing row, for all four use cases:

| Use case | Healthy | Unhealthy |
|---|---:|---:|
| historical_inventory | 6 | 2194 |
| backtest_probability | 1657 | 543 |
| result_settlement | 6 | 2194 |
| prospective_generation | 1985 | 215 |

Final integrity:

- `quick_check = ok`;
- foreign-key violations: 0;
- no extra selection/change;
- no package, scheduler, settlement, marker, upload or bet operation was run.

## Artifacts

- `MANIFEST.json`
- `COMMANDS.md`
- `run-20260730T111538Z/backup-manifest.json`
- `run-20260730T111538Z/dry-run-proof.txt`
- `run-20260730T111538Z/offline-transition-proof.json`
- `run-20260730T111538Z/network-zero-http-proof.json`
- `run-20260730T111538Z/repeat-noop-proof.json`
- `run-20260730T111538Z/scope-and-transition-proof.json`
- `run-20260730T111538Z/data-health-proof.json`
- stage state/drawing/logical-audit captures and command stdout/stderr under `run-20260730T111538Z/`
