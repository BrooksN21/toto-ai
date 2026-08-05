# Wave 2 commands

All commands ran from `/Users/turshevr/toto-ai`.

No Git, scheduler, package, settlement, marker, upload, bet, TLS-bypass, or
automatic restore command was run.

## Frozen selection

Network:

```text
4940 4945 4949 4950 4951 4952 4957
```

Offline canonical RAW repair:

```text
4954
```

Each network drawing was selected with one exact command:

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db /Users/turshevr/toto-ai/data/toto.db \
  --from-drawing N \
  --to-drawing N \
  --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file RUN_DIR/PHASE/state-N.json \
  --raw-archive-root /Users/turshevr/toto-ai/data/raw/archive \
  --dry-run
```

After dry-run proof, only `--dry-run` changed to `--apply`.

## Baseline and online backup

```bash
.venv/bin/python \
  plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-WAVE2/capture_state.py \
  --db data/toto.db \
  --raw-root data/raw \
  --output RUN_DIR/state-before.json

.venv/bin/python \
  plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-WAVE2/capture_drawings.py \
  --db data/toto.db \
  --output RUN_DIR/drawings-before.json

.venv/bin/python \
  plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/db_logical_audit.py \
  --db data/toto.db \
  --output RUN_DIR/db-audit-before.json

.venv/bin/python \
  plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/create_online_backup.py \
  --source data/toto.db \
  --backup \
    data/backups/toto-before-controlled-backfill-wave2-20260730T104031Z.db \
  --manifest RUN_DIR/backup-manifest.json
```

## Data Health

For each use case:

```text
historical_inventory
backtest_probability
result_settlement
prospective_generation
```

the command was run for both the full database and `4940..4957`:

```bash
.venv/bin/python -m toto_ai.cli data-health \
  --db data/toto.db \
  --use-case USE_CASE \
  --output-dir OUTPUT_DIR \
  --no-strict

.venv/bin/python -m toto_ai.cli data-health \
  --db data/toto.db \
  --from-drawing 4940 \
  --to-drawing 4957 \
  --use-case USE_CASE \
  --output-dir OUTPUT_DIR \
  --no-strict
```

## Offline repair 4954

The first diagnostic dry-run used relative RAW paths and therefore resolved
them incorrectly as `data/data/raw`. It reported `source_missing`, performed no
apply, and the physical/logical immutability checks passed.

The corrected and applied command used absolute paths:

```bash
.venv/bin/python -m toto_ai.cli repair-canonical-raw \
  --drawing-number 4954 \
  --db /Users/turshevr/toto-ai/data/toto.db \
  --raw-cache-root /Users/turshevr/toto-ai/data/raw \
  --raw-archive-root /Users/turshevr/toto-ai/data/raw/archive \
  --dry-run
```

After a dry-run result of `171` recoverable changes and another unchanged-state
proof, only `--dry-run` changed to `--apply`.

## Idempotency pass

The exact offline repair and all seven exact reconciliation commands were
repeated without `--force`.

- complete drawings returned `selected=0`;
- source-incomplete drawings returned cooldown without network access;
- the pass ran with network unavailable and produced no transport failure,
  proving zero HTTP requests;
- RAW bytes were unchanged.

The repeated offline repair exposed the classification mutation documented in
`REPORT.md`; no further apply operation was run after discovery.
