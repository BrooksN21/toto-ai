# TOTO Reviewed Schedule Fallback — Implementation Plan

> **Task:** `TOTO-REVIEWED-SCHEDULE-FALLBACK`
> **Execution mode:** TDD, one stage at a time, with a review gate after every
> stage. This document is planning-only; it does not authorize Git operations,
> scheduler activation, package generation, or betting.

**Goal:** Safely allow an otherwise complete drawing preparation to use a
strictly reviewed schedule record for an event absent from API-Sports, while
preserving atomic `15/15` publication and fail-closed final revalidation.

**Architecture:** Separate the identity of one authoritative 15-pin set from
the source provider of each pin. API-Sports remains the primary provider.
Reviewed schedule evidence is a distinct, schedule-only source with its own
strict catalog, provenance, freshness, and revalidation adapter. All 15 pins
are published in one transaction and independently revalidated by their source
adapter before `PLAY`.

**Tech stack:** Python, Typer, SQLAlchemy/SQLite, Pydantic/dataclasses according
to existing repository patterns, pytest, Ruff, Rich, JSON/CSV runner artifacts.

## Global constraints

- Work only in `/Users/turshevr/toto-ai`.
- Do not use Arcadia, Yandex/internal skills, or external project memory.
- Do not change BK/EV/Cover/package mathematics in this task.
- Do not change API-Sports fuzzy/confidence thresholds.
- Do not weaken the two-day playable policy or the T−12 hard cutoff.
- Do not invent API-Sports fixture or team IDs.
- Do not store reviewed evidence with `source_provider="api-sports"`.
- Do not treat a timing override as fixture evidence.
- Do not authorize fallback after ambiguity, transport failure, date failure,
  quota exhaustion, or incomplete API-Sports date coverage.
- A ready preparation publishes exactly 15 pins with event orders `0..14`, or
  publishes zero authoritative pins.
- `PLAY` requires source-aware final revalidation of all 15 pins.
- Morning automation remains passive by default.
- Evening activation remains out of scope until a separate,
  activation-disabled live `15/15` drill passes.
- No claim of profitability follows from this feature. It improves schedule
  coverage and provenance only.

## Explicit non-goals

- Automatic scraping of arbitrary websites.
- Automatic betting or account interaction.
- Hardcoded handling of drawings 4958/4959, event orders, leagues, or teams.
- Replacing the existing API-Sports resolver with fuzzy cross-provider
  matching.
- Using TotoBrief BK data to prove fixture identity.
- Enabling unsupported multi-day drawings.

## Frozen design decisions

### Reviewed evidence is not a synthetic fixture

A reviewed pin has:

- `source_provider="reviewed-schedule"`;
- `source_fixture_id=NULL` unconditionally;
- a mandatory `reviewed_evidence_id`;
- a mandatory semantic evidence hash;
- an explicit `schedule_only=true` capability.

Native fixture/team IDs published by official or independent sources remain
claim-level provenance inside the evidence record. They are never collapsed
into one synthetic reviewed fixture ID. The evidence ID is never copied into
an API-Sports fixture-ID field.

### Production-valid reviewed evidence requires two agreeing claims

One record is production-valid only when it contains:

1. one official federation/competition/club schedule claim;
2. one independent public schedule claim;
3. exact agreement after UTC normalization on sport, competition class,
   gender/age class, home/away orientation, start time, and scheduled status.

A one-source record may be loaded for diagnostics, but cannot close the
`15/15` gate.

### Freshness policy

- Preparation: newest claim capture must be no older than 12 hours.
- Final runner: every claim capture must be no older than 90 minutes.
- `captured_at <= reviewed_at <= evaluated_at < drawing_deadline`.
- Any claim with `cancelled`, `postponed`, `abandoned`, `void`, unknown status,
  or a conflicting start is invalid.
- A changed catalog or changed snapshot after final preflight is a TOCTOU
  failure and produces `NO BET`.

The 12-hour preparation window supports passive morning work. The 90-minute
final window forces a recent review before publication.

### Catalog provenance

Each source claim contains:

- source name and role (`official` or `independent`);
- HTTPS source URL;
- capture timestamp;
- relative path to a saved source snapshot;
- SHA-256 of the exact snapshot bytes;
- extracted home/away names, competition, status, and UTC start;
- native fixture/team IDs only when the source genuinely publishes them.

Catalog and snapshots are protected runner inputs. Relative paths cannot escape
the catalog directory.

### Versioned operational schemas

- Reviewed catalog: `schema_version=1`.
- Runner manifest: introduce version 3 for source-aware pin revalidation.
- Scheduler plan: introduce version 5 for reviewed-catalog binding.
- Morning dispatch record: introduce version 2 for immutable pin-set/catalog
  identity.
- Historical schema readers remain read-only compatible.
- Mixed-provider `PLAY` is permitted only with the new schema versions.

---

## Target file map

### New files

- `src/toto_ai/external_odds/reviewed_schedule.py`
  Strict catalog parser, canonical hashing, snapshot verification, target
  binding, freshness checks, and reviewed revalidation.
- `src/toto_ai/external_odds/schedule_sources.py`
  Provider-neutral schedule/revalidation protocols and source registry.
- `tests/test_reviewed_schedule.py`
- `tests/test_schedule_sources.py`
- `tests/test_mixed_provider_preparation.py`
- `tests/test_mixed_provider_revalidation.py`
- `tests/fixtures/reviewed_schedule/valid_catalog.json`
- `tests/fixtures/reviewed_schedule/official_snapshot.json`
- `tests/fixtures/reviewed_schedule/independent_snapshot.json`

### Existing files expected to change during implementation

- `src/toto_ai/external_odds/domain.py`
- `src/toto_ai/db/models.py`
- `src/toto_ai/db/session.py`
- `src/toto_ai/external_odds/team_registry.py`
- `src/toto_ai/external_odds/preparation.py`
- `src/toto_ai/external_odds/collection.py`
- `src/toto_ai/external_odds/prospective.py`
- `src/toto_ai/external_odds/eligibility.py`
- `src/toto_ai/runner/morning_dispatch.py`
- `src/toto_ai/runner/orchestration.py`
- `src/toto_ai/runner/scheduler.py`
- `src/toto_ai/runner/reports.py`
- `src/toto_ai/cli.py`
- `tests/test_team_registry.py`
- `tests/test_progressive_preparation.py`
- `tests/test_team_resolution_4958.py`
- `tests/test_team_resolution_4959.py`
- `tests/test_external_event_matching.py`
- `tests/test_runner_end_to_end.py`
- `tests/test_runner_scheduler.py`
- `tests/test_morning_dispatch.py`
- `memory-bank/ARCHITECTURE.md`
- `memory-bank/CURRENT_STATE.md`
- `memory-bank/DECISIONS.md`
- `memory-bank/ROADMAP.md`

---

## Stage 0 — Freeze the existing safety contract

**Purpose:** Establish regression tests before adding any fallback behavior.
This stage changes tests only.

**Files:**

- Modify: `tests/test_progressive_preparation.py`
- Modify: `tests/test_external_event_matching.py`
- Modify: `tests/test_runner_end_to_end.py`
- Modify: `tests/test_morning_dispatch.py`

### TDD steps

- [ ] Add a characterization test for an all-API-Sports drawing proving that
  the existing preparation publishes one exact 15-pin set.
- [ ] Add a characterization test for a `14/15` drawing proving that it writes
  an unresolved preparation and zero authoritative pins.
- [ ] Add tests proving that ambiguity, required-date failure, quota failure,
  and transport failure cannot be classified as source absence.
- [ ] Add a runner test proving that failed pin revalidation prevents EV,
  package, marker, and `PLAY`.
- [ ] Add a morning test proving that passive mode never installs an evening
  plan.
- [ ] Run the focused tests and verify they pass before production changes:

```bash
.venv/bin/python -m pytest -q \
  tests/test_progressive_preparation.py \
  tests/test_external_event_matching.py \
  tests/test_runner_end_to_end.py \
  tests/test_morning_dispatch.py
```

### Acceptance criteria

- Existing API-Sports behavior is captured without changing production code.
- A `14/15` preparation is explicitly verified to have zero authoritative
  pins.
- No test assumes reviewed evidence is available.

---

## Stage 1 — Strict reviewed schedule catalog, dormant by default

**Purpose:** Build and adversarially test evidence parsing without connecting
it to preparation, persistence, runner, or scheduler.

**Files:**

- Create: `src/toto_ai/external_odds/reviewed_schedule.py`
- Create: `tests/test_reviewed_schedule.py`
- Create: `tests/fixtures/reviewed_schedule/valid_catalog.json`
- Create: `tests/fixtures/reviewed_schedule/official_snapshot.json`
- Create: `tests/fixtures/reviewed_schedule/independent_snapshot.json`

### Interfaces

The module should expose immutable values equivalent to:

```python
@dataclass(frozen=True)
class ReviewedSourceClaim:
    source_name: str
    role: Literal["official", "independent"]
    source_url: str
    snapshot_path: Path
    snapshot_sha256: str
    captured_at: datetime
    home_name: str
    away_name: str
    competition: str
    sport: str
    gender_age_class: str
    starts_at: datetime
    status: Literal["scheduled"]
    native_fixture_id: str | None
    native_home_team_id: str | None
    native_away_team_id: str | None


@dataclass(frozen=True)
class ReviewedScheduleEvidence:
    evidence_id: str
    drawing_id: int
    drawing_number: int
    target_fingerprint: str
    event_order: int
    target_event_id: int
    reviewer: str
    reviewed_at: datetime
    claims: tuple[ReviewedSourceClaim, ...]
    semantic_hash: str


@dataclass(frozen=True)
class ReviewedScheduleCatalog:
    schema_version: Literal[1]
    catalog_id: str
    generated_at: datetime
    semantic_hash: str
    records: tuple[ReviewedScheduleEvidence, ...]


def load_reviewed_schedule_catalog(
    path: Path,
    *,
    evaluated_at: datetime,
    max_age: timedelta,
) -> ReviewedScheduleCatalog: ...


def select_reviewed_evidence(
    catalog: ReviewedScheduleCatalog,
    *,
    drawing_id: int,
    drawing_number: int,
    target_fingerprint: str,
    event_order: int,
    target_event_id: int,
) -> ReviewedScheduleEvidence: ...
```

### TDD steps

- [ ] Write failing tests for a valid two-source catalog and deterministic
  semantic hashes.
- [ ] Write failing tests rejecting duplicate JSON keys, unknown fields,
  duplicate evidence IDs, duplicate target bindings, and duplicate sources.
- [ ] Write failing tests rejecting HTTP URLs, absolute snapshot paths, path
  traversal, missing snapshots, and snapshot hash mismatch.
- [ ] Write failing tests rejecting non-UTC timestamps, captures from the
  future, `reviewed_at` before capture, and stale claims.
- [ ] Write failing tests rejecting one-source evidence for production use,
  two claims with the same role, and two claims from the same source.
- [ ] Write failing tests for orientation, competition, sport, gender/age,
  start-time, and status disagreement.
- [ ] Write failing tests rejecting cancelled/postponed/abandoned/void/unknown
  statuses.
- [ ] Write failing tests for wrong drawing ID, visible number, fingerprint,
  event order, and target event ID.
- [ ] Implement only enough parser/validator logic to pass these tests.
- [ ] Verify that the module has no imports from preparation, DB, runner, or
  scheduler.
- [ ] Run:

```bash
.venv/bin/python -m pytest -q tests/test_reviewed_schedule.py
.venv/bin/python -m ruff check \
  src/toto_ai/external_odds/reviewed_schedule.py \
  tests/test_reviewed_schedule.py
```

### Acceptance criteria

- The catalog is a dormant, strict local evidence contract.
- A valid record has exactly one official and at least one independent claim.
- Semantic hash and snapshot hashes are deterministic and verified.
- A reviewed record cannot present itself as API-Sports.
- No production path consumes the catalog yet.

---

## Stage 2 — Mixed-provider pin-set persistence and migration

**Purpose:** Separate authoritative pin-set identity from per-pin source
identity while retaining all existing API-Sports preparations.

**Files:**

- Modify: `src/toto_ai/external_odds/domain.py`
- Modify: `src/toto_ai/db/models.py`
- Modify: `src/toto_ai/db/session.py`
- Modify: `src/toto_ai/external_odds/team_registry.py`
- Modify: `tests/test_team_registry.py`
- Create/modify migration tests following existing `db/session.py` patterns.

### Data model

Add canonical fields:

**Drawing preparation**

- `pin_set_id`: immutable deterministic identifier.
- `pin_set_hash`: SHA-256 over exact drawing binding and 15 canonical pins.
- `provider_distribution_json`: canonical counts by real source provider.
- `reviewed_catalog_hash`: nullable; required when any reviewed pin exists.

**Drawing event pin**

- `pin_set_id`: links the pin to one preparation set.
- `source_provider`: actual source, e.g. `api-sports` or
  `reviewed-schedule`.
- `source_fixture_id`: required for API-Sports and always null for reviewed
  evidence.
- `reviewed_evidence_id`: nullable; required for reviewed evidence.
- `source_identity_hash`: canonical identity/provenance hash.
- `schedule_only`: boolean.

Keep legacy `provider` and `provider_fixture_id` readable during migration, but
new loaders and writers must use canonical fields.

Add uniqueness:

- `(pin_set_id, event_order)`;
- `(pin_set_id, target_event_id)`;
- API provider identity:
  `(pin_set_id, source_provider, source_fixture_id)` when fixture ID exists;
- reviewed identity:
  `(pin_set_id, reviewed_evidence_id)` when reviewed evidence exists.

### Migration rules

- Backfill each legacy API-Sports ready preparation only when exactly 15 pins
  with orders `0..14` are present.
- Set `source_provider=provider` and
  `source_fixture_id=provider_fixture_id`.
- Compute deterministic `pin_set_id` and `pin_set_hash`.
- Do not fabricate missing rows or IDs.
- Legacy partial/corrupt groups remain non-ready and do not receive a
  canonical ready pin set.
- Migration is idempotent and safe on an already migrated DB.

### TDD steps

- [ ] Write failing migration tests from an API-Sports-only legacy database.
- [ ] Write failing tests for idempotent second migration.
- [ ] Write failing tests proving corrupt legacy `14/15`, duplicate order, and
  duplicate fixture groups do not become ready.
- [ ] Write failing model validation tests for the exclusive identity modes:
  API pin requires fixture ID and forbids reviewed evidence ID; reviewed pin
  requires evidence ID and forbids synthetic API fixture identity.
- [ ] Write failing atomic publish tests for `14 API + 1 reviewed`.
- [ ] Write failing rollback tests: any invalid pin causes one transaction to
  publish zero pins and a non-ready preparation.
- [ ] Write failing load tests returning exact orders `0..14` from one
  `pin_set_id`, regardless of source distribution.
- [ ] Write failing invalidation tests for drawing fingerprint changes.
- [ ] Implement additive schema migration, canonical hashing, atomic writer,
  and loader.
- [ ] Keep compatibility wrappers for API-Sports-only callers until Stage 6.
- [ ] Run:

```bash
.venv/bin/python -m pytest -q tests/test_team_registry.py
.venv/bin/python -m ruff check \
  src/toto_ai/db/models.py \
  src/toto_ai/db/session.py \
  src/toto_ai/external_odds/team_registry.py \
  tests/test_team_registry.py
```

### Acceptance criteria

- Existing valid API-Sports ready preparations remain loadable.
- Mixed-provider sets are loaded by exact `pin_set_id`, not by one provider.
- No partial set can be authoritative.
- Reviewed evidence is first-class provenance, not a fake provider fixture.
- Feature remains operationally dormant; preparation still produces only
  API-Sports pins.

---

## Stage 3 — Provider-neutral schedule capability boundary

**Purpose:** Separate schedule identity/revalidation from market retrieval so a
schedule-only reviewed pin can never be sent to an API-Sports odds endpoint.

**Files:**

- Create: `src/toto_ai/external_odds/schedule_sources.py`
- Modify: `src/toto_ai/external_odds/domain.py`
- Modify: `src/toto_ai/external_odds/reviewed_schedule.py`
- Create: `tests/test_schedule_sources.py`

### Interfaces

```python
@dataclass(frozen=True)
class SchedulePinRevalidation:
    event_order: int
    source_provider: str
    matched: bool
    fresh: bool
    identity_valid: bool
    status_valid: bool
    evidence_id: str | None
    evidence_hash: str
    reason: str | None


class ScheduleSource(Protocol):
    source_name: str

    def revalidate_pins(
        self,
        pins: Sequence[DrawingEventPin],
        *,
        evaluated_at: datetime,
        deadline: datetime,
    ) -> Sequence[SchedulePinRevalidation]: ...


class MarketSource(Protocol):
    source_name: str

    def fetch_event_markets(
        self,
        source_fixture_id: str,
        *,
        cutoff: datetime,
    ) -> ProviderMarketSnapshot: ...
```

Implement:

- `ApiSportsScheduleSource`, preserving current exact schedule checks.
- `ReviewedCatalogScheduleSource`, loading/revalidating catalog evidence.
- `ScheduleSourceRegistry`, rejecting unknown or duplicate source names.
- Existing API-Sports market provider remains separate.

### TDD steps

- [ ] Write failing contract tests for source registry lookup and duplicate
  registration.
- [ ] Write failing API-Sports regression tests proving fixture/team/start/date
  checks are unchanged.
- [ ] Write failing reviewed-source tests for exact evidence ID/hash and
  freshness.
- [ ] Write failing tests for missing catalog, missing record, changed record,
  stale capture, status change, source disagreement, and deadline violation.
- [ ] Write a spy market provider test proving reviewed pins cannot reach
  `fetch_event_markets()`.
- [ ] Implement the protocols and adapters without changing preparation.
- [ ] Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_schedule_sources.py \
  tests/test_external_event_matching.py
.venv/bin/python -m ruff check \
  src/toto_ai/external_odds/domain.py \
  src/toto_ai/external_odds/schedule_sources.py \
  src/toto_ai/external_odds/reviewed_schedule.py \
  tests/test_schedule_sources.py
```

### Acceptance criteria

- Schedule and market capabilities are separate.
- API-Sports behavior is unchanged.
- Reviewed evidence has no market capability.
- Unknown source providers fail closed.

---

## Stage 4 — Conservative preparation fallback and atomic 15/15 publication

**Purpose:** Enable fallback only after complete API-Sports collection proves a
specific event is absent from source coverage.

**Files:**

- Modify: `src/toto_ai/external_odds/preparation.py`
- Modify: `src/toto_ai/external_odds/eligibility.py`
- Modify: `src/toto_ai/external_odds/team_registry.py`
- Create: `tests/test_mixed_provider_preparation.py`
- Modify: `tests/test_progressive_preparation.py`
- Modify: `tests/test_team_resolution_4958.py`
- Modify: `tests/test_team_resolution_4959.py`

### Preparation algorithm

1. Fetch every required API-Sports schedule date with existing bounded retry
   and quota policy.
2. Run the existing API-Sports resolver unchanged.
3. Build an admission list only from targets whose status is exactly
   `source_missing_competition` or an existing semantically equivalent
   proven-absence status.
4. Reject fallback for any target or drawing with ambiguity, failed required
   date, quota stop, transport failure, incomplete fetch, competing
   API-Sports candidate, wrong gender/age/competition, or unstable target.
5. Strictly load the reviewed catalog using the 12-hour preparation age.
6. Require exactly one production-valid reviewed record for every admitted
   target.
7. Construct all 15 draft pins in memory.
8. Compute canonical provider distribution, catalog hash, `pin_set_id`, and
   `pin_set_hash`.
9. Recompute eligibility from immutable effective starts.
10. Publish preparation and all 15 pins in one DB transaction only when:
    exact orders are `0..14`, target binding is exact, eligibility is
    `playable`, and every pin identity validates.
11. On any failure, publish an unresolved preparation and zero authoritative
    pins.

### TDD steps

- [ ] Write failing `14 API + 1 reviewed` happy-path test.
- [ ] Write failing tests proving no catalog, diagnostic-only one-source
  evidence, malformed catalog, stale record, or wrong target publishes zero
  pins.
- [ ] Write failing tests proving fallback cannot replace ambiguous
  API-Sports candidates.
- [ ] Write failing tests proving fallback cannot mask transport/date/quota
  failures.
- [ ] Write failing conflict test where API-Sports has a competing candidate
  but reviewed evidence claims another fixture.
- [ ] Write failing tests for reversed orientation, wrong competition, wrong
  gender/age, and conflicting start.
- [ ] Write failing tests for two reviewed events and a general mixed
  distribution to prevent `14+1` hardcoding.
- [ ] Convert 4958/4959 regressions into sanitized fixtures proving the generic
  behavior without hardcoded drawing logic.
- [ ] Write transaction interruption tests proving no partial pins survive.
- [ ] Implement minimal fallback admission and atomic publication.
- [ ] Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_mixed_provider_preparation.py \
  tests/test_progressive_preparation.py \
  tests/test_team_resolution_4958.py \
  tests/test_team_resolution_4959.py \
  tests/test_team_registry.py
```

### Acceptance criteria

- Valid `14 API + 1 reviewed` produces one exact mixed 15-pin set.
- Every unsupported or inconsistent case produces zero authoritative pins.
- API-Sports resolver thresholds and ambiguity handling remain unchanged.
- No drawing number, team name, league, or event order is hardcoded.
- `_ineligibility_reason()` is not bypassed.

---

## Stage 5 — Per-pin final revalidation and probability provenance

**Purpose:** Independently revalidate each pin by its real source immediately
before runner publication.

**Files:**

- Modify: `src/toto_ai/external_odds/collection.py`
- Modify: `src/toto_ai/external_odds/prospective.py`
- Modify: `src/toto_ai/external_odds/schedule_sources.py`
- Create: `tests/test_mixed_provider_revalidation.py`
- Modify: `tests/test_external_event_matching.py`
- Modify: `tests/test_runner_end_to_end.py`

### Final revalidation algorithm

1. Load one ready pin set by exact drawing/fingerprint/`pin_set_id`.
2. Require exactly 15 pins and orders `0..14`.
3. Group pins by `source_provider`.
4. API-Sports group:
   - fetch all required dates;
   - reject any date/fetch/quota failure;
   - perform existing exact fixture/team/orientation/start/freshness checks.
5. Reviewed group:
   - load catalog with 90-minute final max age;
   - verify exact catalog, record, snapshot, semantic, and source hashes;
   - verify scheduled status and exact target binding;
   - reject missing/new/changed/conflicting evidence.
6. Aggregate exactly 15 per-event revalidation rows.
7. Recompute `ready_for_play`; do not trust a stored aggregate boolean.
8. Fetch markets only for pins whose source has market capability.
9. For reviewed schedule-only events, use explicit
   `TOTOBRIEF_BK_FALLBACK` probability provenance after identity passes.
10. Reload catalog and protected snapshots before publication and compare
    hashes captured at final preflight.
11. Any mismatch suppresses EV/package/marker and yields `NO BET`.

### TDD steps

- [ ] Write failing happy-path final revalidation test for 14 API pins and one
  reviewed pin.
- [ ] Write failing tests for API fixture/team/start changes.
- [ ] Write failing tests for reviewed record removal, evidence hash change,
  snapshot tampering, stale capture, cancellation, postponement, and claim
  disagreement.
- [ ] Write failing TOCTOU test changing catalog after final preflight.
- [ ] Write failing source-registry test for an unknown pin provider.
- [ ] Write spy tests proving no market request receives a reviewed evidence
  ID.
- [ ] Write probability-provenance test requiring the reviewed event to state
  `TOTOBRIEF_BK_FALLBACK`.
- [ ] Write aggregate tampering test: 14 matching rows plus a forged
  `ready_for_play=true` must still fail.
- [ ] Write end-to-end failure tests proving no EV/package/marker artifacts.
- [ ] Implement grouped revalidation, market-capability routing, and aggregate
  recomputation.
- [ ] Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_mixed_provider_revalidation.py \
  tests/test_external_event_matching.py \
  tests/test_runner_end_to_end.py
```

### Acceptance criteria

- All 15 pins are revalidated by their actual source adapter.
- Reviewed evidence failure cannot be replaced by BK probabilities.
- Market calls are impossible for reviewed schedule-only identities.
- Any stale/cancelled/changed/missing evidence yields `NO BET`.
- Successful mixed-provider revalidation has explicit per-event provenance.

---

## Stage 6 — CLI, runner manifest, scheduler, and morning binding

**Purpose:** Carry catalog identity through every protected operational layer
without changing passive-default automation.

**Files:**

- Modify: `src/toto_ai/cli.py`
- Modify: `src/toto_ai/runner/morning_dispatch.py`
- Modify: `src/toto_ai/runner/orchestration.py`
- Modify: `src/toto_ai/runner/scheduler.py`
- Modify: `src/toto_ai/runner/reports.py`
- Modify: `tests/test_runner_scheduler.py`
- Modify: `tests/test_morning_dispatch.py`
- Modify: `tests/test_runner_end_to_end.py`

### CLI contract

Add an optional explicit input:

```text
--reviewed-schedule-catalog PATH
```

to:

- `prepare-drawing`;
- `morning-dispatch`;
- `run-drawing`;
- scheduler-plan/artifact generation commands that build those calls.

Omitting the option must preserve existing API-Sports-only behavior.

### Protected identity

Bind the following into scheduler plan v5, plan ID, morning dispatch record v2,
final input snapshot, runner manifest v3, report, and durable archive:

- normalized catalog path;
- catalog semantic hash;
- hashes of every referenced snapshot;
- preparation `pin_set_id` and `pin_set_hash`;
- provider distribution;
- reviewed evidence IDs and semantic hashes;
- final per-pin `source_provider` and revalidation method.

Strict manifest parsing must reject unknown/missing fields and independently
derive readiness from 15 per-event rows.

### TDD steps

- [ ] Write failing CLI tests for option propagation to prepare and final
  commands.
- [ ] Write failing tests proving no catalog option preserves old behavior.
- [ ] Write failing scheduler-plan tests proving catalog hash changes alter
  semantic plan ID.
- [ ] Write failing protected-input tests for catalog/snapshot path and content
  mutation.
- [ ] Write failing manifest v3 parser tests for missing per-pin provider,
  evidence hash, or inconsistent provider distribution.
- [ ] Write historical-read tests for existing runner/scheduler schemas.
- [ ] Write failing morning tests proving preparation must be real
  `READY/15/playable`; catalog presence alone is insufficient.
- [ ] Write failing tests proving morning remains passive unless the existing
  explicit activation option is supplied.
- [ ] Write archive rollback tests for publication failure.
- [ ] Implement CLI wiring, schema bumps, protected input binding, and strict
  parsers.
- [ ] Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_runner_scheduler.py \
  tests/test_morning_dispatch.py \
  tests/test_runner_end_to_end.py
```

### Acceptance criteria

- Scheduler and runner cannot silently use a changed catalog.
- Old all-API-Sports invocation remains valid when no catalog is supplied.
- Mixed-provider runs require new schemas and exact provenance.
- Morning dispatcher remains passive by default.
- No evening automation is activated by this stage.

---

## Stage 7 — Full acceptance, migration smoke, and activation-disabled drill

**Purpose:** Prove the feature end to end before considering any scheduler
activation in a separate task.

**Files:**

- Update: `memory-bank/ARCHITECTURE.md`
- Update: `memory-bank/CURRENT_STATE.md`
- Update: `memory-bank/DECISIONS.md`
- Update: `memory-bank/ROADMAP.md`
- Add only sanitized test fixtures/reports required by existing repository
  conventions.

### Automated acceptance matrix

| Scenario | Preparation | Final revalidation | Package/marker |
|---|---:|---:|---:|
| 15 API-Sports | READY 15 | PASS 15 | permitted by later gates |
| 14 API + 1 valid reviewed | READY 15 | PASS 15 | permitted by later gates |
| Reviewed record absent | unresolved, 0 pins | not run | none |
| One-source evidence | unresolved, 0 pins | not run | none |
| API ambiguity | unresolved, 0 pins | not run | none |
| API date/quota/transport failure | unresolved, 0 pins | not run | none |
| Catalog stale at preparation | unresolved, 0 pins | not run | none |
| Catalog stale at final | READY may exist | FAIL | none |
| Cancelled/postponed at final | READY may exist | FAIL | none |
| Catalog/snapshot TOCTOU | READY may exist | FAIL | none |
| Mixed pin market routing | READY 15 | PASS 15 | reviewed pin uses BK fallback |
| Multi-day ineligible drawing | unresolved/ineligible | not run | none |

### TDD and verification steps

- [ ] Run the complete focused fallback suite.
- [ ] Run the entire test suite:

```bash
.venv/bin/python -m pytest -q
```

- [ ] Run Ruff:

```bash
.venv/bin/python -m ruff check .
```

- [ ] Run migration smoke on a copy of a legacy SQLite DB; verify row counts,
  exact 15-pin sets, idempotency, and no partial-ready migration.
- [ ] Run an all-API-Sports activation-disabled rehearsal and compare output
  with the pre-feature baseline.
- [ ] Run a sanitized mixed-provider activation-disabled rehearsal.
- [ ] Run one real active-drawing morning preparation with activation disabled.
- [ ] If and only if preparation is exact `READY/15/playable`, run the final
  activation-disabled path before T−12 using fresh reviewed captures.
- [ ] Confirm manifest v3 independently reports:
  15 matched pins, real provider distribution, exact catalog/pin-set hashes,
  no market call for reviewed pins, and no protected-input mutation.
- [ ] Confirm no LaunchAgent/evening scheduler was installed or changed.
- [ ] Record exact results, failures, and remaining risks in the memory bank.

### Acceptance criteria

- Full pytest and Ruff pass.
- Migration is idempotent and preserves valid legacy API-Sports sets.
- All-API-Sports output is behaviorally unchanged.
- Sanitized mixed-provider acceptance passes every fail-closed case.
- A real activation-disabled drill reaches exact `15/15` or safely defers.
- A defer/NO BET is considered correct when any evidence is missing or stale.
- Evening activation remains a separate explicit decision and task.

---

## Required adversarial test inventory

The implementation is incomplete until every item below has a named test:

- Duplicate JSON keys and unknown catalog fields.
- Catalog/snapshot path traversal and hash mismatch.
- One source, duplicate source, duplicate role, duplicate record.
- Wrong drawing ID/number/fingerprint/event ID/order.
- Reversed home/away.
- Wrong sport, competition, league level, gender, or age class.
- Source start-time disagreement.
- Cancelled, postponed, abandoned, void, or unknown status.
- Capture in the future, stale capture, review before capture.
- API-Sports ambiguity.
- API-Sports required-date, transport, or quota failure.
- Competing API-Sports candidate.
- Duplicate fixture identity inside one source namespace.
- Mixed pin set missing one order or containing a duplicate order.
- Legacy DB with 15 valid pins, 14 pins, duplicate pins, and repeated migration.
- API fixture/team/start mutation at final.
- Reviewed record/snapshot mutation at final.
- Catalog TOCTOU between final preflight and publication.
- Unknown source adapter.
- Reviewed evidence passed to a market endpoint.
- Missing explicit TotoBrief BK probability provenance.
- Forged aggregate `ready_for_play`.
- Manifest/provider-distribution mismatch.
- Scheduler plan catalog hash/path tampering.
- Morning passive-default regression.
- Failed fallback producing EV/package/marker.

---

## Rollout and rollback

### Rollout

1. Merge Stage 1 dormant parser only after adversarial tests pass.
2. Merge Stage 2 additive migration only after legacy DB smoke passes.
3. Merge Stage 3 capability split only after all API-Sports regressions pass.
4. Enable preparation fallback only when an explicit catalog path is supplied.
5. Enable final mixed revalidation only with runner manifest v3 and scheduler
   plan v5.
6. Keep morning passive.
7. Perform activation-disabled live drill.
8. Consider evening activation only in a separate reviewed task.

### Immediate rollback switch

Omit `--reviewed-schedule-catalog`. The system must then use the existing
API-Sports-only path without reading reviewed evidence.

### Data rollback safety

- Existing legacy columns remain readable.
- New canonical pin-set fields are additive.
- A failed migration or failed mixed preparation cannot mark partial pins
  ready.
- No downgrade migration is required for operational rollback; the feature is
  disabled by omitting the catalog input.

---

## Definition of done

The task is complete only when:

1. A valid reviewed catalog cannot be confused with API-Sports identity.
2. Mixed-provider preparation atomically publishes exactly 15 pins or zero.
3. Existing API-Sports-only preparations remain compatible.
4. Final revalidation independently validates every pin by source.
5. Stale, cancelled, changed, missing, or conflicting evidence produces
   `NO BET`.
6. Reviewed schedule-only pins never reach a market endpoint.
7. Scheduler, morning, manifests, reports, and archives carry immutable
   catalog and pin-set provenance.
8. Full tests, Ruff, migration smoke, and activation-disabled live drill pass.
9. Memory-bank documents accurately record the implementation and evidence.
10. Evening scheduler activation and betting remain outside this task.
