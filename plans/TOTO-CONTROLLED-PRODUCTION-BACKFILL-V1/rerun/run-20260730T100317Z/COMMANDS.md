# Commands

All commands ran from `/Users/turshevr/toto-ai`.

## Baseline and backup

```bash
shasum -a 256 data/toto.db
.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/db_logical_audit.py \
  --db data/toto.db --output RUN_DIR/db-audit-baseline.json
.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/create_online_backup.py \
  --source data/toto.db \
  --backup data/backups/toto-before-controlled-backfill-rerun-20260730T100317Z.db \
  --manifest RUN_DIR/backup-manifest.json
```

## Pre/post health

For each `USE_CASE` in `historical_inventory backtest_probability result_settlement prospective_generation`:

```bash
.venv/bin/python -m toto_ai.cli data-health \
  --db data/toto.db --from-drawing 4946 --to-drawing 4958 \
  --use-case USE_CASE --output-dir OUTPUT_DIR --no-strict
```

## Dry-run and apply

Executed separately for `N` in `4946 4955 4956 4958`:

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db data/toto.db \
  --from-drawing N --to-drawing N \
  --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file RUN_DIR/PHASE/state-N.json \
  --raw-archive-root data/raw/archive \
  --dry-run
```

After proving dry-run physical/logical immutability, the exact command was repeated with `--apply`. The complete second pass repeated `--apply` without `--force` to verify cooldown/complete skips and zero network calls.

No scheduler, package, settlement, upload, marker, bet, restore, Git, or TLS-bypass command was run.
