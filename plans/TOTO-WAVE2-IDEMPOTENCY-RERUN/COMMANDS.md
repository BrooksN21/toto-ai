# TOTO-WAVE2-IDEMPOTENCY-RERUN commands

All commands ran from `/Users/turshevr/toto-ai`.

No Git, production-code edit, scheduler, package, settlement, upload, bet, TLS bypass, or forced network operation was used.

## Scope

```text
Network: 4940 4945 4949 4950 4951 4952 4957
Offline: 4954
```

## State capture and online backup

```bash
.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-WAVE2/capture_state.py \
  --db data/toto.db --raw-root data/raw --output RUN_DIR/state-pre.json

.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-WAVE2/capture_drawings.py \
  --db data/toto.db --output RUN_DIR/drawings-pre.json

.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/db_logical_audit.py \
  --db data/toto.db --output RUN_DIR/db-audit-pre.json

.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/create_online_backup.py \
  --source data/toto.db \
  --backup /Users/turshevr/toto-ai/data/backups/toto-before-wave2-idempotency-rerun-20260730T111538Z.db \
  --manifest RUN_DIR/backup-manifest.json
```

## Exact network command template

Executed once per allowed number only, first with `--dry-run`, then with `--apply`, then repeated with `--apply`:

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db /Users/turshevr/toto-ai/data/toto.db \
  --from-drawing N --to-drawing N --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file RUN_DIR/PHASE/network/state-N.json \
  --raw-archive-root /Users/turshevr/toto-ai/data/raw/archive \
  --dry-run-or-apply
```

No `--force` was used. All apply passes skipped before transport.

## Offline 4954 command

Executed as dry-run, one apply, and one repeated apply:

```bash
.venv/bin/python -m toto_ai.cli repair-canonical-raw \
  --drawing-number 4954 \
  --db /Users/turshevr/toto-ai/data/toto.db \
  --raw-cache-root /Users/turshevr/toto-ai/data/raw \
  --raw-archive-root /Users/turshevr/toto-ai/data/raw/archive \
  --dry-run-or-apply
```

## Data Health comparison

The pre-operation online backup was copied temporarily beside `data/raw` so Data Health resolved the same canonical RAW root. For each database and use case:

```bash
.venv/bin/python -m toto_ai.cli data-health \
  --db DATABASE \
  --use-case USE_CASE \
  --output-dir OUTPUT_DIR \
  --no-strict
```

Use cases:

```text
historical_inventory
backtest_probability
result_settlement
prospective_generation
```

The temporary sibling copy was removed after comparison. The online backup remains unchanged.
