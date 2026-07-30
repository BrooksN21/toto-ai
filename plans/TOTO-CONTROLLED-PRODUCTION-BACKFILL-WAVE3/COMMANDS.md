# Commands — Wave 3

All commands ran from `/Users/turshevr/toto-ai`. No Git, scheduler, package, settlement, marker, upload, bet or TLS-bypass command was run.

## Frozen allowlist

```text
4939 4499 3643 3351 3341 3292 2763 2762
```

## Exact reconciliation template

The command below was executed once with `--dry-run`, once with `--apply`, then repeated once without `--force` for every exact drawing `N` in the frozen allowlist:

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db /Users/turshevr/toto-ai/data/toto.db \
  --from-drawing N --to-drawing N --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file RUN_DIR/PHASE/state-N.json \
  --raw-archive-root /Users/turshevr/toto-ai/data/raw/archive \
  --dry-run|--apply
```

## Backup

```bash
.venv/bin/python plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/create_online_backup.py \
  --source data/toto.db \
  --backup data/backups/toto-before-controlled-backfill-wave3-RUN_ID.db \
  --manifest RUN_DIR/baseline/backup-manifest.json
```

## Health

`data-health --no-strict` was captured before and after for all four use cases, both for the full database and each exact selected drawing. Physical state, deterministic logical audit and per-drawing state were captured before dry-run, after dry-run, after apply and after repeat.
