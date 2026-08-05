# TOTO-COLLECTOR-LIFECYCLE-FRESHNESS-V1 — context

## Scope and constraints

This document is context collection only. No production code, database,
network, scheduler, Git, commit, or push operation was performed.

Task objective:

- establish the exact collector lifecycle freshness defect;
- map the current summary/detail/result/snapshot/retry flows;
- define the minimum safe TDD scope for lifecycle-aware finished-drawing
  reconciliation;
- preserve all existing prospective and scheduler safety boundaries.

Primary context:

- `AGENTS.md`;
- every file in `memory-bank/`;
- `plans/TOTO-FULL-HISTORY-DATA-AUDIT/REPORT.md`;
- `plans/TOTO-FULL-HISTORY-DATA-AUDIT/REMEDIATION_PLAN.md`;
- current collector, detail-cache, finished-result, data-health, CLI,
  morning-sync, post-draw, scheduler, and related tests.

## Confirmed data state

The full-history audit established:

- 2,199 locally stored `baltbet-main` drawings;
- 32,985 event rows;
- 369 finished drawings with incomplete results;
- 754 missing event outcomes;
- 215 drawings with unusable 15× `0/0/0` pool triples;
- only 15 drawings with any locally discoverable detail evidence;
- only four drawings with immutable result snapshots;
- no settlements.

The defect predates recent drawings. It was present in the original historical
corpus and is not limited to 4940–4959.

## Exact root cause

### 1. Lifecycle is absent from the collector freshness decision

`Collector.sync()` first persists page-list summaries and only then calls
`drawing_needs_detail()`:

- `src/toto_ai/collector/sync.py:109-132`
- `src/toto_ai/collector/sync.py:163-184`

`drawing_needs_detail()` considers a drawing current when:

- 15 unique event orders `0..14` exist;
- 15 quote rows exist;
- pool and BK triples are finite, non-negative, and have positive totals.

It does **not** inspect:

- `Drawing.status`;
- terminal result count;
- a complete immutable `DrawingResultSnapshot`;
- whether the saved detail was captured before or after the transition to
  `finished`.

Relevant code:

- `src/toto_ai/collector/sync.py:289-317`

Therefore this sequence is possible and confirmed by the audit:

```text
active detail saved with 15 events + pool/BK + no results
-> page summary later changes status to finished
-> summary status commits
-> drawing_needs_detail() returns false
-> no final detail request
-> results remain missing indefinitely
```

This is the primary freshness defect.

### 2. A fresh pre-result cache can suppress the required finished fetch

Normal historical sync invokes detail with `prefer_cache=True`:

- `src/toto_ai/collector/sync.py:128-132`

The non-strict cache/summary validator checks identity, number, and deadline,
but not lifecycle status:

- `src/toto_ai/collector/sync.py:200-219`
- `_validate_detail_matches_summary()` in the same module.

Thus an operational cache captured while `active` can be accepted after the
fresh summary says `finished`. The summary status remains `finished` because
summary fields override cache fields during merge, but the cached payload still
contains no final results.

The current test
`test_fresh_cached_detail_cannot_roll_back_newer_page_status` explicitly
accepts this stale-result behavior: it expects no network call when the summary
is finished but the cache is an active payload. That test must be replaced or
split into:

- status cannot be rolled back;
- an active/pre-result cache cannot satisfy finished reconciliation.

### 3. The operational detail cache is mutable, not historical RAW

`write_drawing_detail_cache()` writes one pair:

```text
data/raw/drawing_<id>.json
data/raw/drawing_<id>.meta.json
```

The pair is atomic and hash-checked, but a newer observation replaces the
previous pair. It is a safe operational cache, not an append-only archive.

Relevant code:

- `src/toto_ai/api/detail_cache.py:35-158`
- `src/toto_ai/api/detail_cache.py:249-285`

Consequences:

- pre-match evidence can be overwritten by a post-draw payload;
- partial and corrected result observations are not retained as separate RAW;
- a crash/retry cannot always prove exactly which source payload preceded an
  operational SQL mutation;
- most historical SQLite rows cannot be reconstructed offline.

### 4. Finished-result ingestion is result-only

`sync_finished_drawing()` performs an explicit exact fetch and creates an
append-only complete result snapshot:

- `src/toto_ai/operations/finished_draw.py:155-254`

However `_persist_operational_result()` updates only:

- drawing number/status/pool sum/jackpot;
- event `result`;
- event `score`.

It does not restore:

- event name;
- championship;
- sport;
- pool/BK/Pin/normalized quote rows.

Relevant code:

- `src/toto_ai/operations/finished_draw.py:1116-1149`

This is the confirmed cause of the 4954–4956 shells: their saved finished
payloads contain complete names and quotes, while operational SQLite has blank
names and no quotes.

### 5. The two import paths have incompatible validation and merge semantics

Collector detail validation requires exactly 15 events and positive pool/BK
quotes for every event:

- `src/toto_ai/api/detail_cache.py:161-193`
- `src/toto_ai/api/detail_cache.py:283-308`

Finished-result normalization requires exactly 15 events and complete terminal
results/scores, but does not require or import names and quotes:

- `src/toto_ai/operations/finished_draw.py:966-1064`

The collector's `_save_drawing()` copies every present key directly, including
`None`, empty values, or weaker values:

- `src/toto_ai/collector/sync.py:402-477`

There is no shared full-detail parser and no field-strength merge. A future
unification must distinguish:

- structural identity requirements;
- phase-specific requirements for active probability input;
- phase-specific requirements for finished terminal results;
- optional fields that may be recovered without destructively downgrading
  stronger existing values.

### 6. Reconciliation is explicit, package-bound, and not part of collection

Available result flows:

1. `sync-finished-results`:
   - exact one drawing;
   - one fetch;
   - complete 15/15 or error;
   - manual VOID arguments;
   - no general backlog traversal.

2. `post-draw-run`:
   - exact one drawing;
   - bounded retry;
   - requires an already archived package file;
   - settles that package after complete results;
   - state is local to that package/drawing.

3. `post-draw-plan`:
   - generates an uninstalled, non-betting LaunchAgent candidate;
   - it is not the general collector lifecycle.

There is no generic nightly/result reconciliation service in `src/` or
`tests/`. The evening betting scheduler imports pre-bet packages but does not
own historical result repair.

Relevant code:

- `src/toto_ai/cli.py:299-544`
- `src/toto_ai/operations/finished_draw.py:637-928`
- `tests/test_finished_lifecycle.py`

### 7. Complete snapshots are append-only, but partial observations are lost

`DrawingResultSnapshot` is immutable/idempotent by
`(drawing_id, snapshot_sha256)`. It stores canonical payload JSON and supports
later authoritative corrections.

But `_normalize_finished_payload()` rejects incomplete results before snapshot
creation. A 14/15 response can be retried, but the partial observation is not
stored as immutable RAW. Only the mutable operational cache may retain it.

Relevant code:

- `src/toto_ai/db/models.py:49-79`
- `src/toto_ai/operations/finished_draw.py:177-240`
- `src/toto_ai/operations/finished_draw.py:1002-1053`

## Current data flows

### Historical collector

```text
GET drawings page
-> commit summary/status rows
-> boolean drawing_needs_detail()
-> optionally accept mutable cache
-> otherwise GET drawing-info
-> overwrite mutable cache pair
-> upsert Drawing/Event/Quote
```

Missing boundary: lifecycle-aware result reconciliation and append-only RAW.

### Morning prospective synchronization

```text
fresh page one
-> exact nearest open drawing
-> force exact detail
-> cache age <= 60 seconds
-> strict active/expected identity + future deadline
-> operational upsert
-> external preparation
```

Relevant code:

- `src/toto_ai/operations/sync_prepare.py:28-95`

This active path is intentionally strict and must not be weakened by finished
reconciliation work.

### Explicit finished synchronization

```text
exact stored drawing identity
-> GET drawing-info/<id>
-> require status=finished + exact identity/deadline + 15 terminal results
-> append complete DrawingResultSnapshot
-> update result/score only
```

### Data-health

`data-health` already distinguishes:

- invalid structure;
- blank names;
- missing/zero pool;
- incomplete BK;
- missing/partial/VOID results;
- missing RAW;
- missing complete result snapshot;
- unsettled actionable package.

It is read-only and does not schedule repair. Current
`backtest_probability` eligibility does not require pre-deadline immutable RAW,
which remains a documented provenance limitation.

## Safety invariants

The implementation must preserve all of the following.

1. **RAW first.** A successful source payload is durably archived with exact
   identity, endpoint, fetch time, canonical hash, and phase before any
   operational row changes.
2. **Append-only evidence.** A new payload never overwrites an old historical
   snapshot. The existing single-file detail cache may remain as an
   operational convenience, but it is not evidence.
3. **Idempotency by content.** Reprocessing the same payload creates no
   duplicate logical snapshot and no second operational change.
4. **No destructive downgrade.** Null, blank, missing, or `0/0/0` values never
   erase a stronger existing name, identity, quote, result, or score.
5. **Finished is not reconciled.** `status=finished` is only listing metadata;
   it is not proof of 15 terminal outcomes.
6. **Terminal evidence.** A finished drawing is current only with 15 terminal
   outcomes and a hash-verified complete result snapshot.
7. **Unknown is not VOID.** Missing/cancelled/postponed source state is not
   automatically converted to `*`. VOID requires authoritative source
   semantics or explicit reviewed evidence with provenance.
8. **Exact identity.** Drawing ID/number/deadline, 15 unique event IDs, and
   orders `0..14` must agree before import.
9. **No future leakage.** Post-draw quotes may repair operational inventory,
   but must not be represented as pre-deadline probability evidence.
10. **Failure is resumable.** Network/archive/import failure cannot mark a
    drawing reconciled. A later run must remain eligible for retry.
11. **No source absence from transport failure.** Timeout, 429, 5xx, malformed
    transport, and interruption are retryable/errors, never
    `source_missing`.
12. **Prospective isolation.** Active morning preparation, mixed-provider
    schedule pins, final 15/15 revalidation, passive activation policy, and
    manual-only betting remain unchanged.
13. **No automatic betting.** Result reconciliation is non-betting and must
    not create a package, marker, upload, or bet.

## Minimum safe implementation scope

The smallest safe change is larger than changing one boolean. Fixing only
`drawing_needs_detail()` would still allow a stale active cache to suppress
the final fetch and would continue losing RAW and analytical fields.

### Slice 1 — pure lifecycle freshness decision

Replace the boolean-only decision with a pure structured evaluation, for
example:

```text
current
needs_structure
needs_probability_input
needs_finished_refresh
needs_terminal_results
needs_result_snapshot
```

Inputs:

- stored drawing status;
- 15-event structure;
- nonblank identity/name coverage;
- 15 valid pool/BK triples, with `0/0/0` invalid;
- terminal result count;
- complete verified result snapshot count;
- current page-summary status and transition.

Required behavior:

- an observed transition to `finished` forces finished reconciliation;
- finished 0–14/15 terminal outcomes remain retryable;
- finished 15/15 plus a complete verified snapshot is current unless forced;
- active/expected behavior remains compatible with the strict morning path.

### Slice 2 — append-only RAW detail archive

Add a content-addressed immutable archive separate from the mutable operational
cache. The recommended minimum record contains:

- schema version;
- drawing ID and visible number;
- canonical deadline/status at observation;
- endpoint;
- phase: `pre_match`, `post_draw_partial`, or `post_draw_terminal`;
- fetched/retrieved time;
- canonical payload SHA-256;
- canonical payload bytes;
- event count and terminal result count;
- archive commit/hash metadata.

Publication order:

```text
validate identity/structure
-> append/verify immutable RAW
-> import operational fields in a separate transaction
```

If import crashes, the durable RAW remains and the next invocation resumes from
it. Duplicate payload hash is a verified no-op.

The existing mutable cache can continue serving prospective operation, but it
must not be the only copy of a network response.

### Slice 3 — shared full-detail importer with field-strength merge

Introduce one reusable parser/importer used by collector and finished-result
sync.

It must:

- validate exact drawing and event identity;
- recover name/championship/sport when the stored value is blank;
- recover valid pool/BK/optional quote values when stored rows are absent or
  unusable;
- import available results/scores;
- never replace good values with null/blank/zero;
- preserve pre-deadline probability provenance separately from post-draw
  recovery;
- append a complete `DrawingResultSnapshot` only at terminal 15/15;
- preserve current append-only correction semantics for later complete,
  authoritative result snapshots;
- commit operational updates atomically.

For 4954–4956, replaying the existing immutable payload must fill the blank
names and missing quotes without changing the already stored results.

### Slice 4 — cache and lifecycle policy

For a fresh summary that says `finished`:

- a cached `active`/`expected` payload is diagnostic/pre-match evidence only;
- it cannot satisfy finished reconciliation;
- a cached finished payload may be used only if its exact identity is valid
  and it is archived immutably before import;
- network failure leaves freshness unresolved and retryable.

For active morning preparation:

- keep the existing <=60-second strict cache policy;
- keep `force=True` and strict active/expected summary matching;
- do not route active preparation through post-draw logic.

### Slice 5 — retry, resume, and idempotency

For this task, safe retry does not require the future historical backfill
engine. Minimum behavior:

- one collector run attempts each selected finished candidate at most once;
- failed/incomplete candidates remain unhealthy and are selected again later;
- the existing TotoBrief request coordinator owns bounded HTTP retries and
  `Retry-After`;
- archive-before-import allows restart after interruption;
- duplicate payloads and repeated runs are no-ops;
- no `reconciled` state is written on transport, validation, archive, or import
  failure.

A rate-limited historical backlog/checkpoint engine and nightly automation
remain the following P1 task, not an implicit part of normal backtests.

### Slice 6 — data-health integration

Reuse the same terminal/quote predicates in collector freshness and
`data-health`; do not maintain divergent definitions.

After each test scenario, assert data-health changes:

- partial finished response:
  - immutable RAW present;
  - `incomplete_results`;
  - `missing_result_snapshot`;
- terminal response:
  - 15 terminal outcomes;
  - complete result snapshot;
  - no result incompleteness reasons;
- `0/0/0` remains invalid even when quote rows exist;
- post-draw quote recovery does not manufacture pre-deadline provenance;
- rehearsal packages remain outside settlement requirements.

## Required TDD cases

All tests use fake clients, temporary SQLite databases, and temporary archive
roots. No network is allowed.

### Freshness characterization/red tests

1. Active drawing with 15 events/quotes and no results transitions in the page
   summary to `finished`; detail fetch is mandatory.
2. Finished drawing with 14 terminal outcomes remains eligible for another
   fetch.
3. Finished drawing with 15 terminal outcomes but no complete immutable result
   snapshot remains eligible.
4. Finished drawing with 15 terminal outcomes and a verified complete snapshot
   is skipped unless `force=True`.
5. 15 quote rows containing pool `0/0/0` do not satisfy freshness.
6. Replace the existing test that accepts a cached active payload after a
   finished summary; assert that the cache cannot suppress the network fetch.

### RAW-first and fault injection

7. Successful network response is archived before operational mutation.
8. Injected failure after archive but before SQL import leaves operational
   rows unchanged and one valid immutable archive.
9. Repeating the same payload resumes import and does not create a second
   logical archive.
10. Wrong identity, duplicate/missing order, conflicting deadline, or corrupt
    archive fails before operational mutation.

### Full-detail recovery

11. A 4954–4956-shaped finished payload restores 15 names, championships,
    sports, and quote rows while preserving results.
12. Null/blank/zero source fields do not overwrite stronger stored values.
13. Valid source quotes fill missing or invalid operational quote rows.
14. A post-draw quote repair is marked as post-draw and cannot qualify as
    historical pre-match probability evidence.
15. Reimport is a logical no-op.

### Results and VOID

16. Partial finished payload is archived, imports safe fields, creates no
    complete result snapshot, and remains retryable.
17. A later 15/15 payload creates a complete snapshot and marks freshness
    current.
18. A later complete correction appends a second snapshot and updates
    operational results through the existing verified correction rule.
19. Blank unresolved result is not converted to VOID automatically.
20. Explicit reviewed VOID with valid provenance produces `*`, terminal 15/15,
    and reproducible snapshot evidence.
21. Invalid or inconsistent VOID evidence fails without operational mutation.

### Retry/resume/CLI/regressions

22. First transport failure followed by a later successful run converges.
23. 429/5xx/timeout remains an error/deferred state, not source absence or
    reconciliation success.
24. Repeated page summaries and repeated payloads are idempotent.
25. `collect` summary reports attempted/current/deferred/reconciled counts and
    machine-readable reasons without exposing URLs/secrets.
26. `sync-finished-results` uses the shared archive/import path and preserves
    exact-identity behavior.
27. `post-draw-run` retry/settlement behavior remains unchanged.
28. `sync-prepare` active cache and 15/15 preparation tests remain green.
29. Evening scheduler tests prove no new package/marker/bet side effect.
30. Data-health assertions match the same freshness predicates.

## Affected files

Likely production files:

- `src/toto_ai/collector/sync.py`
  - lifecycle decision, summary transition handling, result reconciliation
    routing, diagnostics.
- `src/toto_ai/api/detail_cache.py`
  - keep operational cache semantics explicit; reuse validation/path helpers.
- new `src/toto_ai/api/raw_archive.py` or equivalent
  - append-only content-addressed RAW detail archive.
- new `src/toto_ai/collector/detail_import.py` or equivalent
  - shared full-detail normalization and field-strength merge.
- `src/toto_ai/operations/finished_draw.py`
  - route explicit finished sync through shared archive/import logic while
    retaining settlement and snapshot verification.
- `src/toto_ai/db/models.py`
  - only if immutable RAW/import-attempt provenance is indexed in SQLite.
- `src/toto_ai/db/session.py`
  - additive migration only if a model/table is added.
- `src/toto_ai/analytics/data_health.py`
  - shared predicates and immutable RAW/pre-deadline provenance recognition.
- `src/toto_ai/cli.py`
  - lifecycle diagnostics/options only; no automatic betting.
- `src/toto_ai/operations/sync_prepare.py`
  - expected to require regression protection, not behavioral weakening.

Likely tests:

- `tests/test_collector.py`;
- new `tests/test_collector_lifecycle.py` or equivalent;
- `tests/test_finished_lifecycle.py`;
- `tests/test_data_health.py`;
- `tests/test_sync_prepare_operation.py`;
- `tests/test_sync_prepare_cli.py`;
- `tests/test_runner_scheduler.py`;
- `tests/test_scheduler_atomic_final_end_to_end.py`;
- fixtures representing active, partial finished, terminal finished, corrected,
  and reviewed-VOID payloads.

## Acceptance criteria

1. A fresh `finished` summary can never be considered current solely because
   15 events and quotes already exist.
2. A pre-result active cache can never satisfy finished reconciliation.
3. A finished drawing is current only with 15 terminal outcomes and a verified
   complete immutable result snapshot.
4. Every accepted detail payload is durably archived before operational SQL
   mutation.
5. Immutable RAW is append-only and content-idempotent.
6. Interrupted archive/import resumes without duplicate snapshots or partial
   operational publication.
7. Full finished payloads recover all unambiguously available event identity,
   names, championship, sport, quotes, results, scores, and drawing metadata.
8. Weak/missing source values never destructively overwrite stronger stored
   data.
9. `0/0/0` never satisfies quote freshness or data-health.
10. Missing results never become VOID without valid evidence.
11. 4954–4956 local payloads are offline-repairable by the shared importer.
12. Transport and validation failures remain explicit and retryable; they do
    not mark reconciliation complete.
13. Data-health and collector use one consistent definition of structure,
    quote validity, terminal outcomes, and immutable evidence.
14. Existing active morning preparation and all scheduler fail-closed tests
    remain unchanged in behavior.
15. Tests perform zero network access.
16. No automatic betting/upload behavior is introduced.

## Explicit non-goals

Not part of this task:

- running historical network backfill;
- repairing `data/toto.db`;
- installing nightly automation;
- changing package optimization;
- enabling sports-statistics influence;
- changing the passive morning/evening activation policy;
- automatically settling packages without canonical placed-package evidence;
- inventing missing historical outcomes, quotes, timestamps, or VOID states.

## Sports-statistics relationship

The sports-statistics vertical slice already exists:

- provider-neutral domain and storage;
- API-Sports adapter;
- as-of filtering;
- recent form/home-away/rest/standing features;
- immutable audit reports;
- `collect-sports-stats` CLI.

It is deliberately `AUDIT ONLY` and has no package influence. The configured
API-Sports free plan did not provide current-season team history/standings for
the acceptance drawing, so observed feature coverage was insufficient and the
system correctly used market-only fallback.

Collector lifecycle remediation is a prerequisite for trustworthy historical
sports-statistics evaluation because historical replay requires immutable,
time-valid drawing inputs. It does not itself solve the provider-coverage
problem or authorize a sports/market probability blend.

## Recommended next implementation order

1. Add red lifecycle/cache tests and the pure freshness evaluator.
2. Add append-only RAW archive with fault-injection tests.
3. Add the shared full-detail importer and route collector through it.
4. Route explicit finished sync through the same archive/import boundary.
5. Integrate data-health predicates/provenance.
6. Run focused collector/finished/data-health/morning/scheduler suites.
7. Run the full test suite and Ruff.
8. Only after this task passes, perform offline 4954–4956 repair.
9. Then implement a bounded resumable historical network backfill.
10. Then implement nightly listing/result reconciliation and mandatory
    post-draw settlement/reporting.
