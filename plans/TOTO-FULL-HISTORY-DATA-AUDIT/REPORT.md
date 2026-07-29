# TOTO-FULL-HISTORY-DATA-AUDIT

## Scope

- Audit time (UTC): `2026-07-29T13:29:15.476953+00:00`.
- Repository: `/Users/turshevr/toto-ai`.
- Database: `/Users/turshevr/toto-ai/data/toto.db`.
- Database SHA-256: `1a6c9f4d62ba2198852066405342769ebbfa8a057b0525661fc1b58f576fd0c9`.
- SQLite `PRAGMA quick_check`: `ok`.
- Network was not used.
- Production code and Git were not changed.
- Bookmaker filter: exact `drawings.name = 'baltbet-main'`.

## Executive conclusion

The local database contains 2199 BaltBet drawings (2759–4959) and 32985 event rows. Every stored drawing has 15 ordered event rows, but the history is not fully current or forensically complete.

Among 2197 rows marked `finished`, 369 drawings have incomplete results (754 missing event outcomes).
Only 15 drawings have any locally discoverable TotoBrief RAW/detail evidence, and only 4 drawings have immutable result snapshots.
Three drawings have blank names and no analytical quotes; 0 drawings have persisted settlements.

Therefore the earlier statement that the complete API history and all fields were fully validated was too broad and is false for the current local evidence.

## Core counts

| Metric | Value |
|---|---:|
| Drawings | 2199 |
| Events | 32985 |
| Quotes | 32940 |
| Visible number gaps | 3843, 3844 |
| Duplicate visible numbers | 0 |
| `started_at` present | 0 / 2199 |
| `ended_at` present | 2199 / 2199 |
| Exact 15-event/order structure | 2199 / 2199 |
| Complete nonblank names | 2196 / 2199 |
| Exact 15-quote/order structure | 2196 / 2199 |
| Complete pool triples | 1981 / 2199 |
| Drawings with 15 all-zero pool triples | 215 |
| Complete BK triples | 2196 / 2199 |
| Complete norm triples | 2 / 2199 |
| Complete Pin triples | 0 / 2199 |
| Complete results including void | 1828 / 2199 |
| Finished drawings with incomplete results | 369 |
| Missing event results in finished drawings | 754 |
| Explicit void events | 1 |
| Drawings with immutable result snapshot | 4 |
| Drawings with preparations | 5 |
| Drawings with pins | 2 |
| Drawings with archived packages | 1 |
| Drawings with settlements | 0 |

All `started_at` values are null. Available TotoBrief detail payloads do not contain a top-level `started_at`, so this is a schema/source coverage gap rather than evidence that 2,199 imports independently dropped a present field.

Normalized and Pin fields are optional/sparse source fields. Their completeness is reported but they are not treated as hard analytical input failures; pool and BK are the required three-way inputs.

The pool defect is not only the three recent missing quote tables: 215 older drawings contain 15 non-null but unusable `0/0/0` pool triples. The previous non-null field-count audit treated these rows as filled.

## Result defect

- Finished result-incomplete drawings: **369**.
- Missing outcomes in those drawings: **754**.
- Finished drawings missing all 15 results: 2759, 2760, 2761, 2762, 2763, 3292, 3341, 3351, 3643, 4499, 4939, 4940, 4945, 4949, 4950, 4951, 4952, 4957, 4958.
- The many older one-event gaps are consistent with unresolved/cancelled source events, but without saved RAW or explicit `result_status=void` they cannot be distinguished safely and remain unusable for standard backtests.

## RAW vs SQLite root-cause classification

| Class | Meaning | Anomaly rows | Distinct drawing examples |
|---|---|---:|---|
| A | RAW contains more data; SQLite lost/did not import it | 14 | 4850, 4938, 4954, 4955, 4956 |
| B | Available RAW is already incomplete/stale | 17 | 4850, 4939, 4940, 4945, 4950, 4951, 4952, 4957, 4958 |
| C | No local RAW/provenance is available | 4946 | 2759, 2760, 2761, 2762, 2763, 2764, 2765, 2766, 2767, 2768, 2769, 2770, 2771, 2772, 2773, 2774, 2775, 2776, 2777, 2778, … (+2165) |
| D | Conflicting/ambiguous local state | 0 | none |

Classification is per anomaly, not per drawing. One drawing may have multiple anomaly classes for different fields.

The clearest class-A defect is 4954–4956: immutable/local finished payloads contain 15 names and 15 pool/BK quote triples, while operational SQLite has blank names and zero quote rows. The result-only persistence path updated outcomes but did not import analytical event fields.

Recent drawings fetched while active have local RAW snapshots without final outcomes. Where SQLite later says `finished` but was never force-refreshed, the result gap is class B: the saved RAW itself is pre-result/stale.

## Local RAW inventory

- RAW snapshot records found: **23**.
- Unique drawing/payload pairs: **21**.
- Drawings with any local RAW/detail snapshot: **15 / 2199**.
- Drawings with file-based snapshot: **13**.
- Drawings with primary `data/raw` snapshot: **12**.
- Drawings with result-snapshot payload: **4**.
- Drawings without any local RAW/detail snapshot: **2184**.
- JSON scan errors: **1**.

Repeated copies in rehearsal/report directories are retained in the inventory but deduplicated by canonical payload hash for unique counts.

## Period summary

| Year | Drawings | Result complete | Result incomplete | Missing outcomes | Pool/BK complete | RAW available | Result snapshots | Health FAIL |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 174 | 123 | 51 | 130 | 174/174 | 0 | 0 | 51 |
| 2021 | 364 | 297 | 67 | 107 | 344/364 | 0 | 0 | 81 |
| 2022 | 365 | 295 | 70 | 142 | 318/365 | 0 | 0 | 109 |
| 2023 | 362 | 314 | 48 | 60 | 275/362 | 0 | 0 | 123 |
| 2024 | 363 | 315 | 48 | 70 | 321/363 | 0 | 0 | 80 |
| 2025 | 362 | 317 | 45 | 72 | 348/362 | 0 | 0 | 56 |
| 2026 | 209 | 167 | 42 | 194 | 201/206 | 15 | 4 | 48 |

## Hard anomaly types

| Type | Count |
|---|---:|
| `bk_quotes_incomplete` | 3 |
| `blank_event_names` | 3 |
| `finished_results_incomplete` | 369 |
| `package_without_settlement` | 1 |
| `pool_quotes_incomplete` | 218 |
| `quote_structure_incomplete` | 3 |
| `stale_nonfinished_status` | 1 |
| `visible_number_gap` | 2 |

## What the earlier 2,179 / 32,685 validation actually proved

- `2,179 × 15 = 32,685`. Those numbers prove that, at that point, there were 2,179 drawing rows and 15 event rows per drawing.
- The current database has 2,199 drawings and 32,985 events: exactly 20 additional 15-event drawings.
- Inside the original 2,179-drawing corpus, **361** drawings were already result-incomplete, containing **639** missing event outcomes.
- Among the later 4940–4959 rows, **10** are incomplete, containing **136** missing outcomes.
- The retained validation artifact is `reports/validation_4938.md`. It reports PASS for drawing **4938** only.
- `toto_ai.analytics.validation.run_validation()` accepts one supplied RAW payload and compares only that drawing with SQLite.
- The CLI `validate --number N` fetches one live detail payload and runs that single-drawing comparison.
- The old global audit checked aggregate row/field counts and duplicate primary keys; it did not prove that every finished drawing had all results, that every RAW payload was retained, or that every package was settled.
- Project memory already recorded that hundreds of old finished drawings were result-incomplete, but that limitation was not carried into the broad user-facing claim. The broad claim was therefore incorrect.

## Root causes visible from local evidence

1. **Lifecycle refresh defect.** `Collector.drawing_needs_detail()` considers a drawing current after 15 events plus complete pool/BK quotes. It does not require final results after a summary changes to `finished`, so active snapshots can remain permanently result-empty.
2. **Result-only import boundary.** The finished-result operation persists `result` and `score` but does not import names or quotes. This produced 4954–4956 result shells despite complete saved payloads.
3. **Historical source incompleteness.** Hundreds of old finished drawings have one or more unresolved outcomes. With no immutable RAW or explicit void status, source incompleteness cannot be separated from import loss.
4. **Insufficient RAW retention.** Most drawings have no local API payload, so the current database cannot be independently reconstructed or fully forensically verified offline.
5. **Aggregate audit blind spot.** The earlier quote-completeness metric counted non-null fields, so 15×`0/0/0` pool rows appeared filled; its probability helper skipped non-positive triples instead of reporting them as invalid coverage.
6. **No closed settlement lifecycle.** Only one archived package exists and it has no settlement; it is a rehearsal artifact rather than evidence of a placed bet.

## Artifacts

- `drawing_audit.csv`: one row for every BaltBet drawing.
- `anomalies.csv`: all structural, lifecycle, RAW, result-snapshot, and settlement anomalies with A/B/C/D classification.
- `period_summary.csv`: yearly aggregates.
- `raw_snapshot_inventory.csv`: every detected local TotoBrief detail snapshot and canonical hash.
- `raw_comparison.csv`: per-drawing RAW-vs-SQLite classification.
- `json_scan_errors.csv`: malformed/unreadable JSON diagnostics.
- `summary.json`: machine-readable aggregate summary.
- `queries.sql`: key read-only SQL checks.
- `audit_full_history.py`: complete reproducible audit.
- `run_audit.sh`: reproduction command.

## Safety conclusion

Do not use the complete local history as one trusted backtest corpus without an eligibility gate. A drawing is historically usable only when event identity/names, required pool/BK input, and authoritative 15/15 results (including explicit reviewed voids) are complete and its as-of provenance is appropriate for the experiment.
