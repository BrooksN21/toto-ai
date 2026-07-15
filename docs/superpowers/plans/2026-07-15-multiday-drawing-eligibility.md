# Multi-Day Drawing Eligibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect missing-start events across a progressive two-to-five-day horizon and fail closed to `NO BET` unless all 15 events are proven to fit inside two Moscow calendar days.

**Architecture:** Add a provider-neutral eligibility classifier, make schedule collection preserve success/failure per date, persist all timing and horizon provenance, then extend fresh orchestration with a bounded expansion phase. The EV engine receives only an immutable timing eligibility verdict; external probabilities remain unable to promote or rank playable coupons.

**Tech Stack:** Python 3.12, Typer, SQLAlchemy/SQLite, pytest, Ruff, `zoneinfo.ZoneInfo`, existing TotoBrief/API-Sports clients.

## Global Constraints

- Historical TotoBrief collection and existing historical backtests do not change.
- Normal missing-start collection begins with two Moscow calendar days and expands to at most five only after a clean exact-pair miss.
- Known TotoBrief event starts retain exact-date collection even outside the five-day missing-start horizon.
- Eligibility uses the inclusive `Europe/Moscow` calendar span.
- Known span above two days is `multi_day`; otherwise unresolved starts are `unknown`; only 15 known starts within two days are `playable`.
- `multi_day`, `unknown`, absent, and target-mismatched eligibility suppress playable output to zero-cost `NO BET`.
- Research mode remains available.
- Provider timing metadata may veto `PLAY`; external probabilities remain audit-only.
- Category, bank, stake, EV, consensus, payout, and coverage-gate definitions do not change.
- Every collection attempt remains one immutable 15-disposition snapshot.
- No API key enters persistence, cache payloads, reports, or exception text.

---

## File Structure

- Create `src/toto_ai/external_odds/eligibility.py`: effective-start records, target fingerprint, Moscow span classifier, and immutable eligibility result.
- Create `tests/test_external_odds_eligibility.py`: classifier and fingerprint tests.
- Modify `src/toto_ai/external_odds/collection.py`: configurable horizon, per-date schedule isolation, provider starts, and schedule provenance.
- Modify `tests/test_external_odds_collection.py`: date isolation and horizon tests.
- Modify `src/toto_ai/external_odds/prospective.py`: bounded expansion phase and aggregate metadata.
- Modify `tests/test_external_odds_prospective.py`: expansion state-machine tests.
- Modify `src/toto_ai/db/models.py`, `src/toto_ai/db/session.py`, and `src/toto_ai/external_odds/storage.py`: append-only schema, backfill, and exact loading.
- Modify `tests/test_external_odds_storage.py`: migration, identity, round-trip, and legacy tests.
- Modify `src/toto_ai/external_odds/audit.py` and `src/toto_ai/external_odds/reports.py`: timing provenance and eligibility diagnostics.
- Modify `tests/test_external_odds_audit.py` and `tests/test_external_odds_reports.py`: deterministic report coverage.
- Modify `src/toto_ai/ev/models.py`, `src/toto_ai/ev/drawing.py`, `src/toto_ai/ev/reports.py`, and `src/toto_ai/cli.py`: fail-closed playable timing gate and CLI output.
- Modify EV and CLI tests for `NO BET` and unchanged research behavior.
- Update `memory-bank/`, `knowledge/`, and this plan after verification.

### Task 1: Provider-Neutral Eligibility Classifier

**Files:**
- Create: `src/toto_ai/external_odds/eligibility.py`
- Create: `tests/test_external_odds_eligibility.py`

**Interfaces:**
- Produces: `EffectiveEventStart(event_order: int, starts_at: datetime | None, source: Literal["totobrief", "provider", "unresolved"])`
- Produces: `DrawingEligibility(status, earliest_start, latest_start, span_days, missing_event_orders, totobrief_count, provider_count)`
- Produces: `classify_drawing_eligibility(starts) -> DrawingEligibility`
- Produces: `target_fingerprint(drawing_id, drawing_number, deadline, events) -> str`

- [x] **Step 1: Write classifier tests**

Cover exactly 15 ordered starts, Moscow midnight conversion, a contiguous two-day span, two known dates separated by a gap, a confirmed multi-day subset plus unresolved events, unresolved starts inside a two-day known span, source counts, duplicate/missing orders, naive timestamps, and deterministic fingerprint changes.

- [x] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_external_odds_eligibility.py
```

Expected: import failure because the module does not exist.

- [x] **Step 3: Implement immutable classifier**

Use `ZoneInfo("Europe/Moscow")`. Classify in this priority order:

```python
known = tuple(item for item in starts if item.starts_at is not None)
span_days = (max(local_dates) - min(local_dates)).days + 1
if span_days > 2:
    status = "multi_day"
elif len(known) < 15:
    status = "unknown"
else:
    status = "playable"
```

Require event orders `0..14`, aware timestamps, and source/time consistency. Canonical fingerprint input binds drawing ID, number, deadline, and ordered event ID/order/home/away/start fields while excluding fetch time.

- [x] **Step 4: Verify GREEN**

Run the new test file and Ruff on both files.

- [x] **Step 5: Commit**

```bash
git add src/toto_ai/external_odds/eligibility.py tests/test_external_odds_eligibility.py
git commit -m "Add drawing timing eligibility classifier"
```

### Task 2: Per-Date Schedule Collection and Provenance

**Files:**
- Modify: `src/toto_ai/external_odds/collection.py`
- Modify: `tests/test_external_odds_collection.py`

**Interfaces:**
- Adds: `build_external_collection(..., missing_start_horizon_days: int = 2)`
- Produces: `ScheduleDateResult(sport, requested_date, events, error)` internal immutable record.
- Adds snapshot fields: target fingerprint, horizon, requested/successful/failed schedule dates, eligibility.
- Adds event fields: `provider_starts_at`, `effective_starts_at`, `effective_start_source`.

- [x] **Step 1: Write failing collection tests**

Prove:

- a normal target requests only its required two-day UTC coverage;
- a five-day horizon requests only newly selected dates supplied by that call;
- one date raising `APISportsError` does not erase another successful date;
- `QuotaExhausted` marks the current and unattempted dates without further requests;
- a known-start event is affected only by failure of its own date;
- an unmatched missing-start event with any failed date receives a canonical partial-schedule fallback;
- a uniquely matched provider start fills effective time but leaves TotoBrief `starts_at` empty;
- schedule provenance participates in collection identity.

- [x] **Step 2: Verify RED**

Run focused collection tests and confirm missing parameters/fields fail.

- [x] **Step 3: Implement per-date fetching**

Call `provider.fetch_schedule(sport, (requested_date,))` once per date in deterministic sport/date order. Aggregate successful events with the existing provider-event dedupe. Preserve sanitized per-date failures instead of assigning one sport-wide failure.

Generate UTC request dates covering the selected Moscow horizon. Keep explicit TotoBrief dates in the request set. Validate `missing_start_horizon_days` as an integer in `1..5`.

- [x] **Step 4: Build effective starts and eligibility**

Use TotoBrief start first and matched provider start second. Compute the Task 1 eligibility result after all 15 match decisions. Bind schedule metadata and eligibility into collection identity.

- [x] **Step 5: Verify GREEN**

Run all collection, matching, and consensus tests plus Ruff.

- [x] **Step 6: Commit**

```bash
git add src/toto_ai/external_odds/collection.py tests/test_external_odds_collection.py
git commit -m "Isolate external schedule collection by date"
```

### Task 3: Append-Only Storage, Migration, and Audit Reports

**Files:**
- Modify: `src/toto_ai/db/models.py`
- Modify: `src/toto_ai/db/session.py`
- Modify: `src/toto_ai/external_odds/storage.py`
- Modify: `src/toto_ai/external_odds/audit.py`
- Modify: `src/toto_ai/external_odds/reports.py`
- Modify: `tests/test_external_odds_storage.py`
- Modify: `tests/test_external_odds_audit.py`
- Modify: `tests/test_external_odds_reports.py`

**Interfaces:**
- Stores collection-level target fingerprint, horizon, schedule-date JSON, and eligibility fields.
- Stores event-level provider/effective start and source.
- Produces: `load_current_drawing_eligibility(session_factory, drawing_id, target_fingerprint) -> DrawingEligibility | None`.

- [ ] **Step 1: Write failing schema and round-trip tests**

Test new database creation, migration from the legacy external tables, full canonical round-trip, changed schedule metadata changing identity, idempotent resave, and exact rejection of malformed JSON or inconsistent eligibility.

- [ ] **Step 2: Verify RED**

Run storage/session tests and confirm missing columns/attributes fail.

- [ ] **Step 3: Add schema and migration**

Add nullable legacy-compatible columns through `_add_missing_columns`. Backfill legacy run eligibility to `unknown`, legacy event effective source to `unresolved`, and never infer legacy snapshots as playable.

- [ ] **Step 4: Implement storage and current lookup**

Canonicalize schedule-date structures before JSON encoding. Current lookup chooses the latest complete run for the exact drawing/fingerprint and returns `None` for absence or mismatch.

- [ ] **Step 5: Extend audit/report tests and implementation**

Expose horizon, schedule failures, effective starts/sources, eligibility status/span/missing orders, and counts by eligibility. Keep ordinary two-day provider coverage separate from expanded, multi-day, and unknown scopes. Preserve deterministic atomic report publication.

- [ ] **Step 6: Verify GREEN**

Run storage/audit/report tests, repeat report generation byte-for-byte, and run Ruff.

- [ ] **Step 7: Commit**

```bash
git add src/toto_ai/db src/toto_ai/external_odds/storage.py \
  src/toto_ai/external_odds/audit.py src/toto_ai/external_odds/reports.py \
  tests/test_external_odds_storage.py tests/test_external_odds_audit.py \
  tests/test_external_odds_reports.py
git commit -m "Persist external schedule eligibility provenance"
```

### Task 4: Progressive Two-to-Five-Day Orchestration

**Files:**
- Modify: `src/toto_ai/external_odds/prospective.py`
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_external_odds_prospective.py`
- Modify: `tests/test_external_odds_cli.py`
- Modify: `tests/test_external_odds_end_to_end.py`

**Interfaces:**
- Adds: `expansion_horizon_days: int = 5`
- Adds: `max_expansion_passes: int = 3`
- Extends result with `expanded`, `final_horizon_days`, and schedule failure totals.

- [ ] **Step 1: Write failing orchestration tests**

Test no expansion for a clean two-day result, immediate expansion after a clean exact miss on a null-start target, no expansion for known-start misses, operational retry before expansion, quota retry inside expansion, cache path reuse across both phases, bounded expansion exhaustion, and aggregate counters/timing.

- [ ] **Step 2: Verify RED**

Run prospective tests and confirm missing options/state fail.

- [ ] **Step 3: Implement the two-phase state machine**

Keep the existing base `max_passes` meaning. Expansion starts only after a stable base snapshot contains a canonical no-exact-pair miss for a target event whose TotoBrief start is null. Expansion uses the same pinned target and invocation cache, calls collection with horizon five, and has its own bounded pass count. Sleep only for operational failures, not merely to enter expansion.

- [ ] **Step 4: Add CLI controls and output**

Add `--expand-missing-starts/--no-expand-missing-starts`, `--expansion-horizon-days 5`, and `--max-expansion-passes 3`. Print phase/pass totals, final horizon, expanded flag, schedule-date failures, and eligibility. Keep secrets sanitized.

- [ ] **Step 5: Verify GREEN**

Run prospective/CLI/end-to-end tests and CLI help. Confirm no real sleeps or network calls in tests.

- [ ] **Step 6: Commit**

```bash
git add src/toto_ai/external_odds/prospective.py src/toto_ai/cli.py \
  tests/test_external_odds_prospective.py tests/test_external_odds_cli.py \
  tests/test_external_odds_end_to_end.py
git commit -m "Expand missing-start collection through day five"
```

### Task 5: Fail-Closed Playable Timing Gate

**Files:**
- Modify: `src/toto_ai/ev/models.py`
- Modify: `src/toto_ai/ev/drawing.py`
- Modify: `src/toto_ai/ev/reports.py`
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_ev_drawing.py`
- Modify: `tests/test_ev_reports.py`
- Modify: `tests/test_ev_end_to_end.py`

**Interfaces:**
- Adds immutable `PlayTimingEligibility(status, reason, target_fingerprint)` to EV run provenance.
- Adds optional eligibility resolver to `build_open_ev_package` that receives the exact fresh drawing payload.
- Adds `--db data/toto.db` to `ev-package` for read-only eligibility lookup.

- [ ] **Step 1: Write failing EV tests**

For playable mode, prove `multi_day`, `unknown`, absent, and fingerprint mismatch return empty zero-cost `NO BET`; `playable` preserves the existing package; research preserves coupons but reports the timing status. Prove an external probability triplet cannot enter EV input or ranking through this resolver.

- [ ] **Step 2: Verify RED**

Run focused EV tests and confirm missing eligibility provenance/gate fail.

- [ ] **Step 3: Implement timing veto without changing EV math**

Invoke the resolver on the same fresh drawing payload used for `EVInput`. Apply the timing veto after normal package selection through a dedicated suppression helper. Store an explicit reason. Do not replace BK probability rows or crowd rows.

- [ ] **Step 4: Wire read-only CLI lookup and reports**

Open the selected database read-only for eligibility. Research mode may continue when lookup is absent; playable mode fails closed. Reports and Rich summary disclose status, fingerprint match, and reason.

- [ ] **Step 5: Verify GREEN**

Run focused EV/CLI/report tests, `ev-package --help`, and Ruff.

- [ ] **Step 6: Commit**

```bash
git add src/toto_ai/ev src/toto_ai/cli.py tests/test_ev_drawing.py \
  tests/test_ev_reports.py tests/test_ev_end_to_end.py
git commit -m "Gate playable packages on drawing duration"
```

### Task 6: Acceptance, Documentation, and Live-Safe Verification

**Files:**
- Modify: `tests/test_external_odds_end_to_end.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/DATA_NOTES.md`
- Modify: `memory-bank/DECISIONS.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `knowledge/totobrief.md`
- Modify: this plan

**Interfaces:**
- Proves the full collection-to-eligibility-to-play-veto boundary.

- [ ] **Step 1: Add end-to-end acceptance**

Build synthetic ordinary, day-five, partial-date, multi-day, and unresolved drawings through collection, SQLite reload, audit report, and playable/research output. Assert exact 15-event preservation, immutable identity, deterministic reports, and no secret leakage.

- [ ] **Step 2: Run focused verification**

```bash
.venv/bin/python -m pytest -q \
  tests/test_external_odds_eligibility.py \
  tests/test_external_odds_collection.py \
  tests/test_external_odds_storage.py \
  tests/test_external_odds_prospective.py \
  tests/test_external_odds_audit.py \
  tests/test_external_odds_reports.py \
  tests/test_external_odds_cli.py \
  tests/test_external_odds_end_to_end.py \
  tests/test_ev_drawing.py tests/test_ev_reports.py tests/test_ev_end_to_end.py
```

- [ ] **Step 3: Update project memory**

Document the implemented classifier, progressive horizon, migration, CLI protocol, audit scopes, playable veto, and unchanged probability/EV definitions. Mark the roadmap task complete and record exact verification counts.

- [ ] **Step 4: Run full verification**

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
.venv/bin/python -m toto_ai.cli collect-external-odds --help
.venv/bin/python -m toto_ai.cli ev-package --help
git diff --check
```

- [ ] **Step 5: Optional live dry run**

Only when an open drawing and lawful API key remain available, run fresh collection without printing the key. Do not place a bet. Record whether expansion was needed and retain explicit fallback evidence.

- [ ] **Step 6: Commit**

```bash
git add tests memory-bank knowledge docs/superpowers/plans/2026-07-15-multiday-drawing-eligibility.md
git commit -m "Complete multi-day drawing eligibility"
```
