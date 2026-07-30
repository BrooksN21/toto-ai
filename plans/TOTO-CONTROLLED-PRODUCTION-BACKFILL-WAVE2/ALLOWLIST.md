# Wave 2 frozen allowlist

Frozen at `2026-07-30T10:40:31Z` before any apply operation.

## Network reconciliation

Exactly seven finished drawings:

`4940, 4945, 4949, 4950, 4951, 4952, 4957`

Selection criteria:

- listed as `all_results_missing` / `finished_results_incomplete` in the
  full-history forensic audit;
- visible number is within the requested recent range `4940..4957`;
- current read-only inspection confirms 15 events, 15 valid Pool rows,
  15 valid BK rows, 0 terminal results, and no result snapshot;
- excludes already recovered `4955`, `4956`, `4958`;
- excludes cooldown/source-incomplete `4946`;
- total network allowlist is below the hard maximum of eight.

No range selection or implicit `--last` selection is permitted during apply.
Each drawing must be invoked separately with
`--from-drawing N --to-drawing N --batch-size 1`.

## Offline canonical RAW repair

Exactly one drawing:

`4954`

Selection criteria:

- current SQLite has 0/15 nonblank names and 0 quote rows;
- canonical local RAW contains the missing names and quotes;
- its result snapshot already exists;
- repair is local-only and runs before network reconciliation.

## Explicit exclusions

- `4946`: source-incomplete 14/15; handled by cooldown.
- `4955`, `4956`, `4958`: already recovered/healthy.
- every drawing not listed above.

Any extra selection, database delta during dry-run, or mutation outside this
allowlist is an immediate stop with no automatic restore.
