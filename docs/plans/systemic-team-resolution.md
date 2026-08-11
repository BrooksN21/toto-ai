# Systemic Team Resolution Plan (TotoAI)

## Heartbeat / state
- **Phase 2 implementation status (2026-07-21): complete.** Production defaults
  to atomic prepared pins; legacy name matching
  is explicit opt-in only. Manifest schema v4 carries mandatory fresh 15/15
  pinned revalidation and the scheduler fails closed to `.no-bet`.
- **Matcher v3 drawing-4972 regression (2026-08-11): complete.** Reusable
  country-scoped exact team identities and translated domestic competition
  taxonomy resolve the frozen schedule 15/15 with playable two-day timing.
  Reversed, ambiguous, wrong-country, out-of-window, and genuinely absent
  candidates remain fail-closed. Production code contains no drawing/order/
  fixture-ID special case, and ready baseline pins remain immutable against a
  later provider refresh.
- **Deterministic replay:** `run-drawing --offline-replay` accepts strict saved
  TotoBrief target and API-Sports schedule envelopes plus an injected aware
  `--replay-as-of`. It runs the same prepare/pin/revalidate/runner/manifest-v4
  path without live clients, packages, or scheduler markers and is permanently
  research-only. A mandatory isolated `--replay-root` owns its derived SQLite,
  reports, provider cache, and temporary files; overlap with live project state
  or symlink traversal is rejected before writes. Cache hashes and exact
  drawing fingerprint/event ordering are checked before execution. Scheduler
  consumption records the replay as non-production/ignored without any marker.
- **Plan file status:** written to `docs/plans/systemic-team-resolution.md` (this file).
- **Architecture inspected:** `AGENTS.md` + all `memory-bank/*` + matching/collection/storage/CLI/scheduler/prospective/runner/DB models/session.
- **Current command surface noted:** team matching is executed indirectly through `run-drawing` -> `collect_fresh_open_external_odds` (`prospective.py`) -> `build_external_collection` (`collection.py`) -> `match_event` (`matching.py`), with `scheduler-plan/scheduler-execute` orchestration (`runner/scheduler.py`).
- **Blocker:** no migration framework in repo; schema changes are done through SQLAlchemy models + `_add_missing_columns` in `db/session.py`. New registry tables must respect this existing upgrade pattern.
- **Remaining sections in-progress:** finalize detailed commit slices + test additions + rollout/rollback plan (below).

## Design principles
1. Move from per-drawing alias patching to a canonical, persistent team/entity registry.
2. Keep matching conservative: exact > high-confidence transliteration/normalization; never use generic translation as sole identity.
3. Pin mapping at draw-prep time; final runner never re-runs name matching.
4. Persist and replay timing snapshots for deterministic, reproducible eligibility.
5. Fail-closed on ambiguity/mismatch and route into a review queue.

## Acceptance (non-negotiable)
- A drawing is playable only with `15/15` pinned provider IDs + a `15/15` deterministic timing snapshot with `span_days <= 2`.
- Before EV/actionable publication, all 15 pins must be revalidated from fresh
  provider schedule data against provider, fixture ID, oriented team IDs, and
  start-time tolerance; every required schedule date must have succeeded.
- For drawing **4951 (id=11968, drawing 4951)** keep existing acceptance behavior:
  - exact full match to 15 provider IDs in a self-contained replay;
  - current-drawing team aliases are deliberately absent from production data.

## Target architecture (implementable)

### 1) Canonical team/entity registry
Add a new registry layer under `src/toto_ai/external_odds/registry.py` + DB tables:
- `TeamEntity`: canonical identity record.
- `TeamAlias`: reviewed alias row with normalizer chain, transliteration form, provenance source, confidence,
  reviewed flag, reviewer/time, active flag.
- `TeamRegistryCandidate`: optional unresolved candidate evidence for auto-detection (for review queue).

Suggested normalized fields:
- canonical key (canonical UTF-8 normalized name + optional script-transliterated key)
- provider `team_key` + optional provider team id
- sport + league/country context (`country`, `league`, `sport`)
- first-seen / last-seen
- provenance JSON (`source`, `source_path`, `source_fingerprint`, `raw_input_event_id`, `provider_event_id`)

Matching precedence:
1. exact canonical match (target canonical -> registry canonical)
2. reviewed alias chain (same as current deterministic alias behavior)
3. transliterated/normalization candidate
4. otherwise fallback/queue

### 2) Deterministic candidate discovery
Replace broad candidate matching with explicit discovery in `collection.py` + `matching.py`:
- Filter schedule candidates by:
  - **drawing-level constraints**: same sport and event order horizon,
  - **date**: exact `starts_at` day window when available; missing-start window as configured,
  - **league**: exact normalized league token overlap/canonicalization,
  - **home-away orientation**: separate same/reversed channels.
- Transliteration/token normalization can produce evidence only; it is never treated as exact identity by itself.

Suggested function boundaries:
- `collect_candidates(target_event, horizon, schedules_by_sport) -> tuple[ProviderEvent, ...]`
- `score_candidate(target_team, candidate_team, registry, context)` returning evidence types + numeric score and evidence tags.

### 3) Auto-accept policy
In `matching.match_event`:
- Keep current exact-only auto-accept for exact/canonical/alias path.
- Auto-accept transliterated path only when:
  - pair score >= configured threshold,
  - both-team min score >= threshold,
  - top-vs-second score margin >= threshold,
  - evidence includes registry contextual constraints (sport/league/home-away/date).
- Ambiguous/missing/high-risk outcomes produce `match_status="ambiguous"` and produce **ReviewQueue records**:
  - event-level row stores all candidate IDs, reasons, score gap, and matching hash.
  - queue is persisted and idempotent.

### 4) Persistent prepare-drawing command
Add CLI command `prepare-drawing` (new, non-blocking):
- Resolves and pins drawing target (or supplied drawing id).
- Runs constrained matching and schedule lookup once.
- Writes immutable `DrawingPreparation` record with:
  - target fingerprint,
  - per-event pinned provider event IDs,
  - per-event mapping evidence (canonical IDs, alias/translit evidence, candidate provenance, ambiguity flag),
  - timing snapshot (`provider` starts + `totobrief` starts + eligibility status).
- Reuses existing cache/session setup flow; safe-writes with path-protection checks.

### 5) Morning/periodic schedule + T-60 readiness gate
- Add scheduled orchestrator command (or scheduler extension):
  - **morning bootstrap**: run `prepare-drawing` for current and upcoming openings.
  - **periodic refresh** every N minutes: re-run prepare for open/near-open draws and advance readiness state.
  - readiness gate at **T-60**: require `15/15` mapped fixtures and `15/15` timing snapshot (or explicit unresolved reason with no fallback action).
- Record readiness in DB/manifest for downstream runner.

### 6) Final runner consumes pinned IDs only
In `runner/orchestration.py`/`cli.py`:
- At final pass, if a valid preparation exists and is current:
  - load pinned fixtures directly,
  - skip name rematching,
  - collect markets by `provider_event_id` only.
- If pin invalid/expired/missing:
  - no rematch fallback;
  - return `NO BET` with explicit terminal reason (`pins_invalid`, `pin_missing`, `pin_stale`).

### 7) Invalidation model
- Invalidate prepared pin when any changes detected:
  - drawing fingerprint changed,
  - event order/starts changed,
  - provider team/provider fixture canonical identity changed.
- Persist `preparation_state` with `valid_until` and `invalidated_at`.
- Final runner must check validity and refuse to proceed on stale pins.

### 8) Backfill + unseen-team holdout evaluation
- Add `python -m toto_ai.cli backfill-team-registry`-style job:
  - replay historical drawings and fixtures,
  - auto-ingest matches into reviewed/unreviewed pools,
  - emit unseen-team report.
- Add holdout evaluator that compares:
  - unresolved-before-registry vs resolved-after-registry,
  - no-loss or improvement on exact-match precision,
  - reduction in ambiguous matches and fallback volume.

### 9) DB/migration/API boundaries + compatibility
- DB tables likely additions in `db/models.py` + `_add_missing_columns` migration path in `db/session.py`.
- No rewrite of existing `external_collection_*` tables; add FK links from collection snapshot to preparation id.
- Keep collection payloads canonical and replayable for audit.
- API boundaries:
  - `external_odds/matching.py`: pure matcher, returns `MatchDecision` + evidence.
  - `external_odds/registry.py`: registry lookup/building.
  - `external_odds/prospective.py` + `collection.py`: consume registry/pin-aware decision.
  - `external_odds/storage.py`: persist pin records and review queue metadata.
  - `runner/orchestration.py`: enforce pin validity and no-rematch-at-final.

## Implementation slices (independent write sets)

### Commit 1 — Registry schema + read model (models/session)
- `src/toto_ai/db/models.py`: add registry/review/prepare state tables + lightweight indexes.
- `src/toto_ai/db/session.py`: add compatibility migration for new tables/columns.
- `src/toto_ai/external_odds/registry.py`: typed readers/writers + normalization helpers.

### Commit 2 — Matching + registry-aware candidate discovery
- `src/toto_ai/external_odds/matching.py`: add registry/context-aware candidate scoring, evidence typing, reject-ambiguous queue hooks.
- `src/toto_ai/external_odds/collection.py`: candidate discovery with league/date/sport/home-away filtering.

### Commit 3 — Prepare command + pin persistence
- `src/toto_ai/external_odds/storage.py`: persist `DrawingPreparation`, per-event pin rows, review queue rows.
- `src/toto_ai/cli.py`: add `prepare-drawing` command.
- `src/toto_ai/runner/scheduler.py` and/or `src/toto_ai/runner/reports.py`: add readiness artifacts + schedule hooks.

### Commit 4 — Runner consume-only behavior
- `src/toto_ai/runner/orchestration.py`: add final-stage pin loader + rematch bypass.
- `src/toto_ai/cli.py`: `run-drawing` uses preparation as primary source at final.
- `src/toto_ai/external_odds/prospective.py`: optional `collect_from_pins` path used after T-60/T-15.

### Commit 5 — Invalidation + schedule/periodic gates
- `src/toto_ai/runner/scheduler.py`: add T-60 readiness phase and explicit gate failures.
- `src/toto_ai/cli.py`: add periodic morning/refresh command wrapper.

### Commit 6 — Backfill/holdout analysis tooling
- `src/toto_ai/external_odds/backfill.py` (new): historical replay + unseen-team report + holdout metrics.
- `src/toto_ai/cli.py`: add CLI entry for backfill/holdout command.

### Commit 7 — Tests
- `tests/test_registry_matching.py` (new): registry precedence, translit evidence rules, ambiguity queue.
- `tests/test_prepare_drawing.py` (new): prepare command + pin persistence + invalidation.
- `tests/test_runner_pin_consumption.py` (new): final runner rejects stale pins and avoids rematch.
- `tests/test_4951_systemic.py` (new): preserve 4951 exact IDs and 15/15 readiness invariant with prep output checks.

## Test gates (required)
- Keep all existing matching invariants (`tests/test_external_event_matching*`) passing.
- Add/refresh tests around prospective expansion behavior when pin exists.
- Add targeted regression for 4951 exact tuple and for ambiguous/unknown cases to force review queue.

## Rollback / compatibility
- Rollback path: disable new command scheduling and fall back to current `run-drawing` behavior by feature flag (env + config).
- DB compatibility: all new columns/tables defaulted; legacy rows load with `status="unknown"` and no pinned mapping.
- All old paths (match-by-name) remain available for non-production/diagnostic use until flag cutover.
