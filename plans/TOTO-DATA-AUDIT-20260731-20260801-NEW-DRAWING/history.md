# Toto data audit: 2026-07-31 and 2026-08-01

**Task:** `TOTO-DATA-AUDIT-20260731-20260801-NEW-DRAWING`  
**Audit scope:** local `data/toto.db` and local RAW JSON only; no DB/code changes.

## Executive findings

- The dates map to exactly two drawings: **4961 / DB id 11993** (2026-07-31) and **4962 / DB id 11995** (2026-08-01).
- Both drawings have exactly **15 event rows/orders 0..14**, with no duplicate drawing number/id or duplicate `(drawing_id,event_order)` rows.
- Drawing **4961 is complete**: 15/15 results, 15/15 scores, 15/15 `resolved` statuses, and one complete immutable result snapshot (`event_count=15`).
- Drawing **4962 is incomplete**: event order **6** (`Сегед — БВСК-Зугло`) has blank result, score, and result status. DB totals are 14/15 for each. There is no explicit `VOID` marker, so this is a missing terminal outcome, not a confirmed void.
- Both drawings have 15/15 quote rows with complete pool and BK triples. The DB drawing-level pool/jackpot fields are populated.
- Visible drawing numbers are contiguous around the target range: **4955, 4956, 4957, 4958, 4959, 4960, 4961, 4962, 4963, 4964, 4965**. No visible-number gap was found.
- Official TotoBrief comparison is **not available in this audit**: the current environment exposes no TotoBrief/API credential variables, so no live request was made. Findings below are explicitly local-only.

## Drawing identity and lifecycle

| date | visible no. | DB id | DB status | ended_at | pool_sum | jackpot |
|---|---:|---:|---|---|---:|---:|
| 2026-07-31 | 4961 | 11993 | finished | 2026-07-31T16:00:00.000000Z | 9,774,607 | 18,317,018 |
| 2026-08-01 | 4962 | 11995 | finished | 2026-08-01T15:00:00.000000Z | 9,121,850 | 19,403,081 |

## Event/result completeness

| drawing | rows | distinct orders | results | scores | result statuses | terminal snapshot |
|---:|---:|---:|---:|---:|---:|---|
| 4961 | 15 | 15 (0..14) | 15/15 | 15/15 | 15/15 `resolved` | yes, complete=1, event_count=15 |
| 4962 | 15 | 15 (0..14) | 14/15 | 14/15 | 14/15 | none |

4962 order 6 is the sole missing terminal row. No duplicate or missing event order exists at the row-identity level.

## Pool/BK fields

`quotes` contains 15 rows for each drawing. Every row has non-null `pool_win_1/pool_draw/pool_win_2` and `bk_win_1/bk_draw/bk_win_2` (15/15 for both drawings). `pin_*` values are not populated for these historical rows; `norm_*` values are present only on some rows, but this does not affect pool/BK completeness.

## RAW JSON audit

- Archived RAW exists for DB ids 11993 and 11995; each has 5 archived payload snapshots (5 distinct snapshot hashes).
- 4961 archived payloads: four `source_incomplete` observations followed by one `source_complete` observation; the complete payload has 15 events/results/scores and matches the complete DB result snapshot identity.
- 4962 archived payloads: five `source_incomplete` observations; each has 15 events and complete BK triples, but the event-6 result/score remains blank. No archived payload contains an explicit VOID status for event 6.
- The non-archived top-level files `data/raw/drawing_11993.json` and `data/raw/drawing_11995.json` are stale `active` payloads with 15 events and no results; they must not be mistaken for the finished 4961 evidence or for a completed 4962 result.
- DB RAW metadata reports 5 rows / 5 distinct snapshots / 4 distinct payload hashes for each drawing. This is repeated observation content with distinct captured metadata/snapshot identity, not a duplicate DB row violation.

## Visible-number sequence

Local DB sequence around the dates is continuous:

`4955 -> 4956 -> 4957 -> 4958 -> 4959 -> 4960 -> 4961 -> 4962 -> 4963 -> 4964 -> 4965`

No gap or duplicate is visible in this local sequence. IDs are also unique and increase in the same order: 11977, 11981, 11983, 11986, 11988, 11990, 11993, 11995, 11999, 12003, 12004.

## Official comparison boundary

No live Official TotoBrief API list/detail comparison was performed. The local environment has no visible TotoBrief/API credential variable, and this read-only audit therefore records only local SQLite/RAW evidence. A future authorized read-only comparison should verify page/list identity for 4961/4962 and detail event 6 for drawing 4962.
