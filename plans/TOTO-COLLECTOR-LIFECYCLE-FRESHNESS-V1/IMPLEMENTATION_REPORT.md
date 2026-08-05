# TOTO-COLLECTOR-LIFECYCLE-FRESHNESS-V1

## Scope

Implemented lifecycle-aware finished freshness, RAW-first append-only source
evidence, a non-destructive full-detail importer, bounded reconciliation, and
offline canonical-RAW repair. No LaunchAgent was installed or activated and no
betting path was added.

## Network-free database-copy drill

Source database:

`/Users/turshevr/toto-ai/data/toto.db`

Drill copies:

- `/private/tmp/toto-lifecycle-drill/toto.db`
- `/private/tmp/toto-lifecycle-apply-drill/toto.db`

Results:

- reconciliation dry-run 4940–4959 selected 20/20 legacy drawings;
- dry-run made zero network calls and processed zero drawings;
- canonical RAW 4954: 171 provable logical repairs;
- canonical RAW 4955/4956: missing or invalid local evidence;
- copy-only apply restored 4954 to 15 names and 15 quote rows;
- 4954 remains 14/15 terminal because the source RAW does not explicitly prove
  event 15 VOID;
- no result snapshot was synthesized;
- repeated 4954 import made zero logical changes;
- copied SQLite `quick_check`: `ok`.

## Verification

- focused lifecycle/data-health/finished tests: 71 passed;
- final full pytest: 1499 passed in 246.95 seconds;
- Ruff: passed;
- `git diff --check`: passed;
- main database SHA-256 remained
  `5242945ace687adc59f2a6472bcf3c836075dbc88f47496a45756de6fe4f41fb`.

## Remaining risks

- Historical network backfill has not been run.
- The installed passive morning dispatcher already exists outside this task;
  it was not installed or activated here.
- Old result snapshots are not RAW-linked and therefore do not satisfy the new
  finished-freshness contract.
- Missing canonical RAW cannot be classified as source absence.
- Sports statistics remain audit-only and do not influence probabilities.
