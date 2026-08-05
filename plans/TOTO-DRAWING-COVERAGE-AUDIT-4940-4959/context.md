# TOTO-DRAWING-COVERAGE-AUDIT-4940-4959

## Scope and constraints

- Audit date: 2026-07-29 (Europe/Moscow).
- Scope: local standalone repository `/Users/turshevr/toto-ai` only.
- Network: not used.
- Production code: not changed.
- Git/commit/push: not used.
- Audited database: `/Users/turshevr/toto-ai/data/toto.db`.
- Database size: 100,753,408 bytes.
- Database mtime: `2026-07-29T12:31:57+0300`.
- Database SHA-256 at audit time: `1a6c9f4d62ba2198852066405342769ebbfa8a057b0525661fc1b58f576fd0c9`.
- SQLite `PRAGMA quick_check`: `ok`.

## Schema found

The primary data model in this database is:

- `drawings`: visible `number`, internal `id`, `status`, `started_at`, `ended_at`.
- `events`: 15 ordered events per drawing; result and score live in `events.result` and `events.score`.
- `quotes`: per-event pool, BK, Pin and normalized 1/X/2 fields.
- `drawing_result_snapshots`: immutable post-draw result payload snapshots.
- `drawing_preparations`, `drawing_event_pins`: legacy systematic preparation and pin records.
- `archived_packages`, `package_settlements`: archived package and retrospective settlement records.

There is no separate `results` table and no table literally named `retrospective`.
`package_settlements` is the available package-retrospective table. The current
on-disk database does **not** contain the newer `drawing_pin_sets` or
`drawing_pin_set_items` tables; the reviewed mixed-provider live drill was run
on a copied drill database, not persisted into this production database.

## Exact coverage table: visible drawings 4940–4959

`Pool/BK` is the count of events with complete three-way pool/BK values.
`Results` counts stored final 1/X/2 signs; `*` is the explicit void result.
Times are the stored `ended_at` UTC values. Every row has `started_at = NULL`.

| # | Internal ID | Stored status | ended_at (UTC) | Events | Pool/BK | Results | Result snapshot | Preparation / pins | Package / settlement | Data-quality note |
|---:|---:|---|---|---:|---:|---|---|---|---|---|
| 4940 | 11941 | finished | 2026-07-10 15:30 | 15 | 15/15 | 0/15 | none | none | none | All 15 final results missing |
| 4941 | 11944 | finished | 2026-07-11 14:00 | 15 | 15/15 | 15/15 | none | none | none | Complete analytical/result row |
| 4942 | 11946 | finished | 2026-07-12 16:00 | 15 | 15/15 | 15/15 | none | none | none | Complete analytical/result row |
| 4943 | 11949 | finished | 2026-07-13 14:00 | 15 | 15/15 | 15/15 | none | none | none | Complete analytical/result row |
| 4944 | 11951 | finished | 2026-07-14 14:00 | 15 | 15/15 | 15/15 | none | none | none | Complete analytical/result row |
| 4945 | 11953 | finished | 2026-07-15 15:00 | 15 | 15/15 | 0/15 | none | none | none | All 15 final results missing |
| 4946 | 11955 | finished | 2026-07-16 15:00 | 15 | 15/15 | 14/15 | none | none | none | Event 12 has no result or score |
| 4947 | 11957 | finished | 2026-07-17 15:30 | 15 | 15/15 | 15/15 | none | none | none | Complete analytical/result row |
| 4948 | 11959 | finished | 2026-07-18 14:00 | 15 | 15/15 | 15/15 | none | none | none | Complete analytical/result row |
| 4949 | 11962 | finished | 2026-07-19 13:00 | 15 | 15/15 | 0/15 | none | none | none | All result signs missing; 5 scores are present |
| 4950 | 11964 | finished | 2026-07-20 14:30 | 15 | 15/15 | 0/15 | none | none | none | All 15 final results missing |
| 4951 | 11968 | finished | 2026-07-21 16:00 | 15 | 15/15 | 0/15 | none | none | none | All 15 final results missing |
| 4952 | 11970 | finished | 2026-07-22 16:00 | 15 | 15/15 | 0/15 | none | `ready 15/15`; 15 valid API-Sports pins | none | Results missing despite ready preparation |
| 4953 | 11972 | finished | 2026-07-23 15:30 | 15 | 15/15 | 15/15 | 1 complete | `unresolved 0/15`; no pins | none | Results complete; preparation unresolved |
| 4954 | 11975 | finished | 2026-07-24 15:30 | 15 | 0/0 | 14/15 + 1 void `*` | 1 complete | none | none | All 15 names blank; no quote rows; event 15 explicit `void` |
| 4955 | 11977 | finished | 2026-07-25 15:30 | 15 | 0/0 | 15/15 | 1 complete | none | none | All 15 names blank; no quote rows |
| 4956 | 11981 | finished | 2026-07-26 14:30 | 15 | 0/0 | 15/15 | 1 complete | none | none | All 15 names blank; no quote rows |
| 4957 | 11983 | finished | 2026-07-27 15:00 | 15 | 15/15 | 0/15 | none | `ready 15/15`; 15 valid API-Sports pins | none | Results missing despite ready preparation |
| 4958 | 11986 | finished | 2026-07-28 14:00 | 15 | 15/15 | 0/15 | none | `unresolved 0/15`; no pins | none | All 15 final results missing |
| 4959 | 11988 | active | 2026-07-29 14:00 | 15 | 15/15 | 0/15 | none | `unresolved 0/15`; no pins in main DB | 1 archive: 2 coupons, 60 RUB; no settlement | Archive source is `reports/rehearsal/manual-sim-4959-*`, so it is a simulation artifact, not evidence of a placed bet |

## Missing and incomplete data

### Drawing headers

- Missing visible drawing numbers in 4940–4959: **none**.
- Duplicate visible drawing numbers in 4940–4959: **none**.
- All 20 drawings have exactly one internal row and exactly 15 distinct event
  orders `0..14`.
- All 20 `ended_at` values are present.
- All 20 `started_at` values are `NULL`.

### Pool/BK analytical input

- Complete 15-event pool and BK input: **17/20 drawings**.
- Missing all quote rows: **4954, 4955, 4956**.
- The available pool/BK triples sum to 99–101 because of source rounding; no
  out-of-range structural anomaly was found.
- Drawings 4954–4956 are result-only shells in the main analytical tables:
  15 event rows exist, but every event name is blank and no quote row exists.

### Results

Among the 19 rows stored as `finished`:

- Complete 15×1/X/2 results: **9 drawings** — 4941, 4942, 4943, 4944,
  4947, 4948, 4953, 4955, 4956.
- Complete result set with an explicit void: **4954**; event 15 has
  `result='*'`, `result_status='void'`, blank score.
- Partial result set: **4946**; event 12 is missing.
- All 15 result signs missing: **4940, 4945, 4949, 4950, 4951, 4952,
  4957, 4958**.
- 4949 additionally has five stored scores but no mapped result signs.
- Complete immutable result snapshots exist only for **4953, 4954, 4955,
  4956**.

### Preparation, pins, packages and retrospectives

- Preparation rows exist only for 4952, 4953, 4957, 4958 and 4959.
- Current valid pins exist only for 4952 and 4957: 15 API-Sports pins each.
- Main DB still has 4959 as legacy `unresolved 0/15`; the successful mixed
  15/15 drill exists only in its copied rehearsal DB/report.
- One archived package exists for 4959: 2 coupons, stake 30, cost 60,
  provenance `pre_bet_runner`; its source path is under
  `reports/rehearsal/manual-sim-4959-*`. Treat it as simulation/test
  contamination, not a placed package.
- `package_settlements` contains **zero** rows for all 4940–4959.
- Therefore no package in this interval has a persisted retrospective
  settlement, best-hit result, payout or ROI in the main database.

## Conclusion

We are **not losing drawing numbers** in the inspected interval: every visible
number 4940–4959 exists exactly once with 15 event positions.

We **are losing or failing to backfill drawing content**:

1. eight finished drawings have no result signs at all;
2. one finished drawing has one missing result;
3. three finished drawings have no names and no pool/BK rows;
4. only four finished drawings have immutable result snapshots;
5. no package settlement/retrospective exists in this interval;
6. the main DB has not persisted the new mixed-provider 4959 readiness state.

So the correct answer is: **header coverage is 20/20, but historical analytical
and post-draw coverage is not complete and currently cannot support reliable
backtesting/retrospective analysis for all 20 drawings.**

## Reproduction commands

Run from `/Users/turshevr/toto-ai`.

### Locate and fingerprint the database

```bash
find . -path './.git' -prune -o -type f \
  \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print
stat -f 'size=%z modified=%Sm' -t '%Y-%m-%dT%H:%M:%S%z' data/toto.db
shasum -a 256 data/toto.db
sqlite3 -readonly data/toto.db 'PRAGMA quick_check;'
```

### List schema and relevant columns

```bash
sqlite3 -readonly -header -column data/toto.db \
  "SELECT name,type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type,name;"

for t in drawings events quotes drawing_preparations drawing_event_pins \
  drawing_result_snapshots archived_packages package_settlements; do
  sqlite3 -readonly -header -column data/toto.db "PRAGMA table_info($t);"
done
```

### Reproduce the 20-row coverage audit

```sql
WITH base AS (
  SELECT id, number, status, started_at, ended_at
  FROM drawings WHERE number BETWEEN 4940 AND 4959
),
ev AS (
  SELECT drawing_id,
         COUNT(*) event_count,
         COUNT(DISTINCT event_order) distinct_orders,
         MIN(event_order) min_order,
         MAX(event_order) max_order,
         SUM(CASE WHEN name IS NULL OR TRIM(name)='' THEN 1 ELSE 0 END) blank_names,
         SUM(CASE WHEN result IN ('1','X','2') THEN 1 ELSE 0 END) decided_results,
         SUM(CASE WHEN result IS NOT NULL AND TRIM(result)<>''
                       AND result NOT IN ('1','X','2') THEN 1 ELSE 0 END) void_other,
         SUM(CASE WHEN result IS NULL OR TRIM(result)='' THEN 1 ELSE 0 END) missing_results,
         SUM(CASE WHEN score IS NOT NULL AND TRIM(score)<>'' THEN 1 ELSE 0 END) scores_present
  FROM events GROUP BY drawing_id
),
qt AS (
  SELECT drawing_id,
         COUNT(*) quote_rows,
         COUNT(DISTINCT event_order) distinct_quote_orders,
         SUM(CASE WHEN pool_win_1 IS NOT NULL AND pool_draw IS NOT NULL
                       AND pool_win_2 IS NOT NULL THEN 1 ELSE 0 END) pool_complete,
         SUM(CASE WHEN bk_win_1 IS NOT NULL AND bk_draw IS NOT NULL
                       AND bk_win_2 IS NOT NULL THEN 1 ELSE 0 END) bk_complete
  FROM quotes GROUP BY drawing_id
),
prep AS (
  SELECT p.drawing_id, COUNT(*) prep_rows,
         (SELECT p2.status FROM drawing_preparations p2
          WHERE p2.drawing_id=p.drawing_id
          ORDER BY p2.updated_at DESC,p2.id DESC LIMIT 1) latest_status,
         (SELECT p2.mapped_count FROM drawing_preparations p2
          WHERE p2.drawing_id=p.drawing_id
          ORDER BY p2.updated_at DESC,p2.id DESC LIMIT 1) latest_mapped
  FROM drawing_preparations p GROUP BY p.drawing_id
),
pins AS (
  SELECT drawing_id, COUNT(*) pin_rows,
         SUM(CASE WHEN status='valid' AND invalidated_at IS NULL
                  THEN 1 ELSE 0 END) current_valid_pins,
         GROUP_CONCAT(DISTINCT provider) providers
  FROM drawing_event_pins GROUP BY drawing_id
),
rs AS (
  SELECT drawing_id, COUNT(*) snapshots,
         SUM(CASE WHEN complete=1 THEN 1 ELSE 0 END) complete_snapshots
  FROM drawing_result_snapshots GROUP BY drawing_id
),
ap AS (
  SELECT drawing_id, COUNT(*) packages, SUM(coupon_count) coupons, SUM(cost) cost
  FROM archived_packages GROUP BY drawing_id
),
ps AS (
  SELECT drawing_id, COUNT(*) settlements, MAX(best_hits) best_hits
  FROM package_settlements GROUP BY drawing_id
)
SELECT b.number,b.id,b.status,b.started_at,b.ended_at,
       COALESCE(ev.event_count,0) events,
       COALESCE(ev.distinct_orders,0) event_orders,
       COALESCE(ev.blank_names,0) blank_names,
       COALESCE(qt.quote_rows,0) quotes,
       COALESCE(qt.pool_complete,0) pool_complete,
       COALESCE(qt.bk_complete,0) bk_complete,
       COALESCE(ev.decided_results,0) results_1X2,
       COALESCE(ev.void_other,0) void_other,
       COALESCE(ev.missing_results,0) result_missing,
       COALESCE(ev.scores_present,0) scores_present,
       COALESCE(rs.snapshots,0) result_snapshots,
       COALESCE(rs.complete_snapshots,0) complete_snapshots,
       COALESCE(prep.prep_rows,0) preparations,
       COALESCE(prep.latest_status,'-') preparation_status,
       COALESCE(prep.latest_mapped,0) mapped_count,
       COALESCE(pins.pin_rows,0) pins,
       COALESCE(pins.current_valid_pins,0) valid_pins,
       COALESCE(pins.providers,'-') pin_providers,
       COALESCE(ap.packages,0) packages,
       COALESCE(ap.coupons,0) coupons,
       COALESCE(ap.cost,0) package_cost,
       COALESCE(ps.settlements,0) settlements,
       COALESCE(ps.best_hits,'') best_hits
FROM base b
LEFT JOIN ev ON ev.drawing_id=b.id
LEFT JOIN qt ON qt.drawing_id=b.id
LEFT JOIN prep ON prep.drawing_id=b.id
LEFT JOIN pins ON pins.drawing_id=b.id
LEFT JOIN rs ON rs.drawing_id=b.id
LEFT JOIN ap ON ap.drawing_id=b.id
LEFT JOIN ps ON ps.drawing_id=b.id
ORDER BY b.number;
```

Execute it with:

```bash
sqlite3 -readonly -header -column data/toto.db < audit.sql
```

### Reproduce void/cancelled results

```sql
SELECT d.number, e.event_order+1 AS position, e.result, e.score, e.name
FROM drawings d JOIN events e ON e.drawing_id=d.id
WHERE d.number BETWEEN 4940 AND 4959
  AND e.result IS NOT NULL AND TRIM(e.result)<>''
  AND e.result NOT IN ('1','X','2')
ORDER BY d.number,e.event_order;
```

For the snapshot-level status of 4954 event 15:

```sql
SELECT json_extract(j.value,'$.order')+1 AS position,
       json_extract(j.value,'$.result') AS result,
       json_extract(j.value,'$.result_status') AS result_status,
       json_extract(j.value,'$.score') AS score
FROM drawing_result_snapshots s, json_each(s.events_json) j
WHERE s.drawing_number=4954
ORDER BY position;
```
