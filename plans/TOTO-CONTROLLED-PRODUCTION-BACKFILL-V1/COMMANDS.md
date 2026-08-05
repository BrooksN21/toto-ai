# Commands executed

Run directory:

`/Users/turshevr/toto-ai/plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/run-20260730T092227Z`

## Preflight and backup

```bash
sha256sum data/toto.db

.venv/bin/python \
  plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/db_logical_audit.py \
  --db data/toto.db \
  --output plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/run-20260730T092227Z/pre-db-logical-audit.json

.venv/bin/python \
  plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/create_online_backup.py \
  --source data/toto.db \
  --backup data/backups/toto-before-controlled-backfill-20260730T092227Z.db \
  --manifest plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/run-20260730T092227Z/backup-manifest.json

.venv/bin/python -m toto_ai.cli data-health \
  --db data/toto.db \
  --from-drawing 4946 \
  --to-drawing 4958 \
  --use-case historical_inventory \
  --output-dir plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/run-20260730T092227Z/pre-health \
  --no-strict
```

## Dry-run

The following was executed separately for `N` in `4946 4955 4956 4958`:

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db data/toto.db \
  --from-drawing N \
  --to-drawing N \
  --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file plans/TOTO-CONTROLLED-PRODUCTION-BACKFILL-V1/run-20260730T092227Z/reconcile-state.json \
  --raw-archive-root data/raw/archive \
  --dry-run
```

The operation stopped immediately after proving that this dry-run added the
empty `drawing_reconciliation_states` table.

No network/apply command was executed.
