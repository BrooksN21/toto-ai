# Exact canary commands

Canary directory:

`/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z`

All mutate-capable commands below received only this copied database:

`/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/toto-canary.db`

## Safe SQLite backup

`sqlite3.Connection.backup()` was used from the read-only URI for
`/Users/turshevr/toto-ai/data/toto.db` into the canary database.

## Baseline health

```bash
.venv/bin/python -m toto_ai.cli data-health \
  --db "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/toto-canary.db" \
  --from-drawing 4946 --to-drawing 4958 \
  --use-case historical_inventory \
  --output-dir "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/data-health-before" \
  --no-strict
```

## Dry-run template (executed separately for 4946, 4955, 4956, 4958)

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/toto-canary.db" \
  --from-drawing N --to-drawing N \
  --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/state/dry-run-N.json" \
  --raw-archive-root "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/raw-archive" \
  --dry-run
```

## Network apply template (executed separately for each selected number)

```bash
.venv/bin/python -m toto_ai.cli reconcile-finished \
  --db "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/toto-canary.db" \
  --from-drawing N --to-drawing N \
  --batch-size 1 \
  --max-attempts 2 \
  --initial-backoff-seconds 0.25 \
  --max-backoff-seconds 1 \
  --backoff-multiplier 2 \
  --rate-limit-seconds 1 \
  --state-file "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/state/apply-N.json" \
  --raw-archive-root "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/raw-archive" \
  --apply
```

The same per-drawing commands were executed a second time for idempotency.
4955 used `apply-escalated-4955.json` after the sandbox-only transport
attempt failed. No TLS bypass was used.

## Final health

```bash
.venv/bin/python -m toto_ai.cli data-health \
  --db "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/toto-canary.db" \
  --from-drawing 4946 --to-drawing 4958 \
  --use-case historical_inventory \
  --output-dir "/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/data-health-after-second-pass" \
  --no-strict
```
