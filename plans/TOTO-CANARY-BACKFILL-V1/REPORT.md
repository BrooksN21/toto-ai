# TOTO-CANARY-BACKFILL-V1

Date: 2026-07-30
Production code changed: **no**
Git/commit/push: **not used**
API scope: **TotoBrief drawing-info only**
API-Sports/sports statistics: **not used**

## Safety boundary

- Main database: `/Users/turshevr/toto-ai/data/toto.db`.
- Canary database: `/Users/turshevr/toto-ai/reports/rehearsal/toto-canary-backfill-v1-20260730T082137Z/toto-canary.db`.
- The canary was created with SQLite `Connection.backup()` from a read-only
  source connection, so WAL state was included safely.
- Every mutate-capable command received only the canary DB path.
- Main DB SHA-256 before: `5242945ace687adc59f2a6472bcf3c836075dbc88f47496a45756de6fe4f41fb`.
- Main DB SHA-256 after:  `5242945ace687adc59f2a6472bcf3c836075dbc88f47496a45756de6fe4f41fb`.
- SQLite `quick_check`: `ok`; foreign-key violations: `0`.

## Selection criterion

Four explicit finished drawings were selected to minimize network volume while
covering the required defect classes:

- **4955** and **4956**: mandatory recent rows with 15 terminal results but
  blank names, no quotes, and zero usable pool/BK in SQLite;
- **4958**: recent finished drawing with all 15 results missing;
- **4946**: finished drawing with one missing result (event order 11).

4955/4956 also cover the requested zero-pool class. Each drawing was processed
as a separate batch of one, with at most two attempts, 30-second client timeout
per request, 1-second rate interval, and bounded 0.25/1-second backoff.

## First network pass

| Drawing | Result | Restored / observed |
|---:|---|---|
| 4955 | repaired, 15/15 | +15 names, +15 championships, +15 quote rows, +15 valid pool, +15 valid BK; existing results preserved; new RAW-linked complete result snapshot |
| 4956 | repaired, 15/15 | same completeness restoration as 4955; existing results preserved; new RAW-linked complete result snapshot |
| 4958 | repaired, 15/15 | +15 decided results and one RAW-linked complete result snapshot; existing names/quotes preserved |
| 4946 | source_incomplete, 14/15 | no synthetic result or VOID; missing event remains order 11; RAW evidence archived |

No terminal conflicts or destructive downgrades were observed. No VOID was
synthesized; all selected payloads contained zero VOID outcomes.

## Data-health delta

The command-level range is 4946–4958 (13 drawings); only the four selected
numbers were network-mutated.

| Metric | Before | After |
|---|---:|---:|
| historical_inventory healthy | 0 | 3 |
| finished incomplete-result drawings | 8 | 7 |
| missing terminal outcomes | 92 | 77 |
| valid-pool drawings | 10 | 12 |
| complete-BK drawings | 10 | 12 |
| RAW-evidenced drawings | 0 | 4 |
| complete RAW-linked result-snapshot drawings | 0 | 3 |
| probability-backtest eligible | 3 | 6 |
| prospective-generation eligible | 10 | 12 |
| result-settlement eligible | 0 | 3 |

Selected outcome:

- 4955: unhealthy -> healthy;
- 4956: unhealthy -> healthy;
- 4958: unhealthy -> healthy;
- 4946: remains unhealthy/source_incomplete with 14/15.

For canary isolation, RAW was originally written under `raw-archive`. A byte
copy was exposed under the canary DB's canonical sibling `raw/archive` before
final `data-health`, because Data Health intentionally discovers RAW only in
the canonical sibling tree. This did not alter SQLite or source evidence.

## RAW and snapshot verification

- Seven appended RAW observations were verified with the project's
  `RawArchive.verify()`:
  - four observations for 4946 (two bounded attempts in each of two runs);
  - one each for 4955, 4956, and 4958.
- Every payload and canonical metadata hash verified.
- The 4955/4956/4958 result snapshots each link to the new RAW snapshot.
- All four 4946 attempts returned the same payload SHA-256
  `c44c81ad8f19812c4a7a1caf95a1809ac3fd544e46653fd14f832c42f082fbff`
  and remained 14/15, supporting `source_incomplete` rather than a transport
  error or invented VOID.

## Idempotency

Second pass:

- 4955, 4956, and 4958: `selected=0, processed=0`; no network refresh and no
  analytical or evidence changes. Freshness skip works.
- 4946: correctly remained selectable because it is not fresh/complete. It made
  two bounded source observations again, appended only RAW-attempt evidence,
  and made no changes to names, quotes, results, VOID, or result snapshots.

The canary DB physical SHA changed during the second pass only because two new
4946 RAW-evidence rows were appended. This is expected for a new explicit
source recheck of an incomplete drawing; the analytical state was unchanged.

## Network errors

The first sandboxed 4955 attempt ended as `transport_error`. After granting
minimal HTTPS permission, the same TotoBrief request succeeded immediately.
This was a sandbox restriction, not a TotoBrief API failure. No insecure TLS
bypass, API-Sports request, 429, 404, or 5xx response was used/observed.

## Go / no-go

**GO** for a small, explicit, backed-up production reconciliation batch of
recent drawings whose source now returns 15/15, with before/after Data Health
and RAW verification.

**NO-GO** for an unbounded full-history or nightly automated backfill yet.
Persistently `source_incomplete` rows such as 4946 are retried on each explicit
run and append new evidence. Before automation, define/verify a cooldown and
terminal classification policy so hundreds of unrecoverable rows are not
queried every night indefinitely.

No production database changes were made by this canary.
