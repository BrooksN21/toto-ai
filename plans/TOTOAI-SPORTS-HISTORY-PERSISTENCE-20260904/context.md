# TOTOAI-SPORTS-HISTORY-PERSISTENCE-20260904 context

Date: 2026-09-04 (Europe/Moscow)

Scope: local, read-only context inspection plus this handoff file. No network,
scheduler execution, VCS operation, or drawing-4996 artifact access was used.

## Root cause

The zero rows are not caused by cleanup, a rolled-back transaction, or a
silent SQLite failure. Two separate sports pipelines exist and only one is
wired to `sports_stats_runs`:

1. The older API-Sports audit command calls
   `collect_and_store_sports_stats()` and then
   `save_sports_stats_snapshot()`. It is a standalone manual CLI path and is
   not called by morning dispatch.
2. Drawings 4990-4995 used the automatic GOAL research-shadow path. That path
   freezes raw and normalized JSON files, later constructs a valid
   `SportsStatsRunSnapshot` in memory, and writes a probability artifact for
   the parallel sidecar. It never calls `save_sports_stats_snapshot()`.

Therefore persistence was **never wired for the GOAL-derived snapshot**. The
GOAL path is deliberately feature-gated and shadow-only, but those gates do
not explain the six missing rows: the frozen `current.json` markers prove the
collector ran. The records are stored as filesystem artifacts, not in another
SQLite table.

Read-only SQLite evidence from `data/toto.db`:

| drawing | internal id | `sports_stats_runs` |
|---:|---:|---:|
| 4990 | 12077 | 0 |
| 4991 | 12081 | 0 |
| 4992 | 12083 | 0 |
| 4993 | 12086 | 0 |
| 4994 | 12089 | 0 |
| 4995 | 12092 | 0 |

The database has seven sports runs total, all with `provider='api-sports'`,
and 105 child feature rows (exactly 7 x 15). It has no
`provider='goal-api-v1'` run.

The six GOAL markers instead report:

| drawing | sports-eligible | history files |
|---:|---:|---:|
| 4990 | 14 | 28 |
| 4991 | 0 | 0 |
| 4992 | 15 | 30 |
| 4993 | 11 | 22 |
| 4994 | 13 | 26 |
| 4995 | 13 | 26 |

All are `PAPER_ONLY_COVERAGE_PROBE`, `package_influence=NONE`, and
`automatic_wagering=false`.

## Exact lifecycle and code paths

### Persistent API-Sports path

- CLI entry: `src/toto_ai/cli.py:6454-6500`, command
  `collect-sports-stats`. It only accepts `provider=api-sports`.
- Orchestration: `src/toto_ai/sports_stats/operation.py:25-134`.
  It initializes the DB, resolves the target and pins, calls
  `collect_sports_stats()`, calls `save_sports_stats_snapshot()` at line 132,
  then writes reports.
- Response normalization:
  `src/toto_ai/sports_stats/api_sports.py:22-145` converts API-Sports target
  fixtures/history to provider-neutral context and `CompletedFixture` rows,
  filtering target, future, and non-terminal fixtures.
- Feature/snapshot construction:
  `src/toto_ai/sports_stats/collection.py:93-311` builds team windows,
  standings, 15 event snapshots, and a content-addressed run snapshot.
- Transaction:
  `src/toto_ai/sports_stats/storage.py:22-99` verifies hashes and, inside one
  `session_factory.begin()` transaction, inserts one `SportsStatsRun` plus 15
  `SportsEventFeatureSnapshot` rows. Replays are idempotent by `run_id` and by
  `(drawing_id, drawing_fingerprint, provider, as_of)`; conflicts raise.

### Non-persistent GOAL path used by 4990-4995

- Automation flags: generated morning wrappers add `--goal-shadow-auto` and
  `--parallel-challenger-auto` in
  `src/toto_ai/runner/scheduler.py:8810-8827`; passive retry children do the
  same in `src/toto_ai/runner/morning_dispatch.py:1269-1279`.
- Gate and error boundary: `src/toto_ai/cli.py:4022-4035,4419-4464` runs the
  collector only for a prepared drawing whose dispatch result is `scheduled`
  or `reused`. The option defaults off for ad-hoc CLI use. Exceptions become
  `PAPER_ONLY_COLLECTION_FAILED` and do not block the primary scheduler.
- Public response and raw freeze:
  `GoalAPIClient.fetch_team_results()` in
  `src/toto_ai/external_odds/goal_api.py:336-428` validates HTTP/JSON/team
  identity and calls `_freeze()` at lines 538-574, producing immutable
  request/response JSON under the capture's schedule snapshot directory.
- Normalized frozen input:
  `collect_goal_probe_input()` in
  `src/toto_ai/sports_stats/goal_probe_collection.py:106-256` binds GOAL
  fixtures to 15 target events, fetches up to ten results for each covered
  home/away team, and calls `_write_normalized_history()` at lines 421-438.
  It writes content-addressed normalized history JSON plus
  `coverage-summary.json`. `ensure_goal_probe_input()` at lines 42-103 writes
  hash-bound `current.json` and reuses it on later runs.
- Derived in-memory snapshot:
  `load_goal_probe_shadow()` in
  `src/toto_ai/sports_stats/goal_probe_research.py:102-523` validates paths,
  identities, timestamps, hashes, and history. `_load_history_snapshot()` at
  lines 1005-1095 maps terminal statuses, excludes the target and any row at
  or after `as_of`/kickoff, and creates provider-neutral fixtures. Lines
  477-489 build a complete `SportsStatsRunSnapshot` with
  `provider='goal-api-v1'`; lines 490-496 derive the shadow probabilities.
- Missing persistence call:
  `src/toto_ai/cli.py:4464-4491` obtains `bundle.snapshot` and immediately
  passes it to `build_sports_v2_shadow_artifact()` / file output. There is no
  DB initialization or `save_sports_stats_snapshot()` call in this branch.
- Consumer split: `load_latest_eligible_snapshot()` defaults to
  `provider='api-sports'` (`src/toto_ai/sports_stats/storage.py:142-170`),
  whereas the operational GOAL sidecar consumes frozen files directly.

### Schema, migration, and cleanup

- Schema: `SportsStatsRun` and `SportsEventFeatureSnapshot` are already
  provider-neutral (`src/toto_ai/db/models.py:664-740`). Their uniqueness
  includes provider, so GOAL and API-Sports rows can coexist.
- Database initialization uses `Base.metadata.create_all()`
  (`src/toto_ai/db/session.py:14-22`). The legacy-DB regression in
  `tests/test_sports_stats_storage.py` verifies both tables are added without
  losing existing data. No new schema is required for the minimal fix.
- There is no production delete/cleanup path for either sports table. GOAL
  artifacts use write-once `_write_exact`; a successful `current.json` is
  reused. A failed capture can leave an unreferenced immutable capture
  directory for audit/retry, but cannot delete SQLite rows. Scheduler cleanup
  targets scheduler/package outputs, not `reports/sports-analytics/<drawing>`.

## Minimal systematic fix

1. Make GOAL normalization/persistence a single reusable helper: validate the
   hash-bound current marker, compute the same chronology-safe `as_of`, call
   `load_goal_probe_shadow()`, then call
   `save_sports_stats_snapshot(session_factory, bundle.snapshot)`.
2. In `morning_dispatch_command`, invoke that helper immediately after
   successful `ensure_goal_probe_input()` and before sidecar artifact creation.
   Reuse the returned bundle for Sports v2. Do this whenever
   `--goal-shadow-auto` succeeds, not only when parallel sidecar preparation is
   enabled.
3. Preserve the shadow fail-open boundary: a persistence error must be visible
   in `sports_shadow` status (include `persistence_status`, `run_id` on success,
   and a bounded error on failure), must suppress use of an unpersisted GOAL
   candidate, and must never affect the primary scheduler/operator path.
4. Keep provider selection explicit. New rows use `goal-api-v1`; existing
   API-Sports consumers keep their default, and any history/v3 consumer that
   wants GOAL must request that provider explicitly rather than silently
   changing model authority.

This uses the existing content-addressed transaction and requires no new
table/column migration.

## Regression tests

Add the following focused cases:

1. GOAL capture -> `load_goal_probe_shadow()` -> persistence: assert one
   `goal-api-v1` run and exactly 15 child rows with matching hashes/statuses.
2. Idempotent marker reuse: persist twice and assert one run/15 children and
   the same `run_id`.
3. Morning CLI integration with `--goal-shadow-auto`: assert persistence occurs
   even without `--parallel-challenger-auto`, and status exposes the run id.
4. Parallel integration: assert the sidecar reuses the exact persisted bundle
   rather than rebuilding a divergent snapshot.
5. Persistence failure: assert explicit shadow failure, no sidecar candidate,
   no partial DB rows, and unchanged successful primary dispatch.
6. Transaction rollback/conflict: force a child uniqueness failure and assert
   neither parent nor partial children remain.
7. Provider isolation: `load_latest_eligible_snapshot()` returns API-Sports by
   default and GOAL only when explicitly requested.

Existing tests cover each half separately but not the missing bridge:
`tests/test_sports_stats_storage.py`,
`tests/test_sports_stats_operation.py`,
`tests/test_goal_probe_collection.py`, and
`tests/test_morning_dispatch.py`.

## Backfill policy for 4990-4995

- Offline only: never refetch or synthesize history.
- Enumerate only the six hash-bound `goal-auto/current.json` records. For each
  drawing, verify marker, coverage, schedule, normalized history, target
  identity, provider identity, and strict pre-kickoff chronology through the
  same production helper.
- Use the exact `as_of` bound to the historical sports-seed artifact when
  available. If the exact historical target/detail binding cannot be verified,
  reject that drawing and report the gap; do not advance timestamps or use
  mutable post-draw data merely to make the import pass.
- Insert through `save_sports_stats_snapshot()` only. Report
  `inserted`/`reused`/`rejected` per drawing. The unique provider/as-of identity
  makes repeated backfills safe.
- Preserve factual missingness. In particular, drawing 4991's verified
  zero-coverage snapshot may be stored as a failed/fallback run, but missing
  histories must not be invented.
- Do not alter or duplicate the seven existing API-Sports rows and do not
  delete the frozen filesystem artifacts after backfill.

## Conclusion

Classification: **feature-gated, shadow-only GOAL collection whose derived
snapshot persistence was never wired**. For drawings 4990-4995 the feature did
run; data was frozen on disk and used in memory, but the only SQLite writer was
the separate API-Sports audit command. No evidence supports cleanup, silent
transaction failure, or alternate SQLite storage as the cause.
