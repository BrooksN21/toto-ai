# Architecture

## Passive nightly reconciliation

`nightly-reconciliation-run` wraps the proven finished reconciliation engine
without any package/betting dependency:

```text
global maintenance lock
-> latest 30 finished drawings
-> physical read-only dry-run
-> exact captured eligible allowlist (maximum 8)
-> repeated selection/drift check
-> online SQLite backup + known-good manifest/retention
-> one bounded non-force attempt per captured drawing
-> Data Health before/after + quick/FK checks
-> timestamped report/state/log
```

The shared lock path is `data/operations/global-maintenance.lock`; the morning
dispatcher uses the same fcntl boundary. Stale metadata is recovered only
after the OS lock is available. A live lock defers the nightly run without
network or backup.

No eligible work produces `DEFERRED/NOOP`, zero network calls, and no backup.
`source_incomplete` and transient per-drawing failures produce `PARTIAL` while
preserving cooldown/quarantine and allowing the bounded run to continue.
Selection drift, backup/integrity failure, or complete captured-work failure is
`FAILED`. Artifact generation is repository-local and never installs or loads
the LaunchAgent.

The reviewed deployment is separately installed as
`com.totoai.nightly-reconciliation.v1` in the current user's LaunchAgent
domain, daily at 03:20 host-local/Moscow time with `RunAtLoad=false`. Its
installed plist points only to the generated repository-local wrapper.
Launchd/runtime files live under the user's home directory and `data/` and are
not repository artifacts. The first smoke run was `PARTIAL`: seven of eight
captured drawings became complete and one authoritative 14/15 source response
entered cooldown. Exit code 2 therefore denotes persisted partial work; the
JSON run report remains the authoritative operational classification.

## Lifecycle-aware collection and reconciliation

Finished freshness is evidence-based: a drawing is current only with 15
terminal outcomes and a complete result snapshot linked to immutable RAW.
Lifecycle transitions invalidate active/expected cache reuse.

The collector and finished reconciliation share one full-detail importer:

```text
TotoBrief payload
-> relaxed exact 15-event identity validation
-> content-addressed append-only RAW + metadata/fsync
-> monotonic/non-destructive full-detail merge
-> terminal 15/15 check
-> immutable result snapshot linked to RAW hash
```

The importer preserves names, championship, sport, pool/BK/pin/norm quotes,
results, scores, and result status. Null/blank fields and zero probability
triples cannot erase stronger data. Terminal conflicts fail closed. VOID is
accepted only with explicit source status and HTTP(S) evidence.

`reconcile-finished` is a non-betting, bounded, resumable command contract for
recent/range incomplete finished drawings. Its dry-run uses a SQLite read-only
URI, never invokes schema setup/migration, treats an absent optional
reconciliation-state table as empty state, and performs no network or
persistent writes. `repair-canonical-raw` uses the same read-only database
boundary in dry-run and computes its importer delta without publishing RAW or
result evidence. Explicit apply mode initializes the additive schema before
the first mutation and retains RAW-first ordering. Neither command installs
automation or places bets.

Persistent reconciliation state is keyed by drawing, provider, and source in
`drawing_reconciliation_states`. It separates source-incomplete observations
from transient transport/429/5xx failures and records the last attempt,
cumulative attempts, canonical upstream payload fingerprint, terminal count,
classification, retry state, next eligible time, and last error code.
Unchanged source-incomplete fingerprints use bounded exponential cooldown and
eventual expiring quarantine. Transient failures use a shorter independent
cooldown. Improved local terminal count, changed observed fingerprint, policy
expiry, or explicit one-run force safely reopen eligibility. Blocked drawings
do not consume a range batch slot, so nightly reconciliation cannot hot-loop
or starve later eligible drawings. Dry-run reads this state but mutates neither
it nor RAW.

Controlled production backfill is an operator-bounded protocol layered over
that engine:

```text
explicit drawing allowlist
-> online SQLite backup + integrity manifest
-> physical read-only dry-run
-> one bounded network apply
-> Data Health and exact changed-row scope proof
-> non-force idempotency pass with zero network requests
```

The first accepted production batch covered 4946/4955/4956/4958. It made four
detail requests, restored complete evidence for 4955/4956/4958, and persisted
4946 as source-incomplete with cooldown. Waves 2/3 and a correction-once/no-op
idempotency replay then authorized only the bounded latest-30/eight-attempt
nightly deployment. No unrestricted historical mode is authorized. SQLite,
backups, RAW payloads, retry/runtime state and installed home plists remain
local operational data and are excluded from Git.

## Provider-neutral reviewed schedule fallback

API-Sports remains the primary schedule/market provider. When and only when a
complete required-date fetch proves an event is absent as
`source_missing_competition`, an explicitly supplied reviewed catalog may
provide schedule identity. Each reviewed record is bound to the exact drawing
ID, visible number, fingerprint, event order, and target event ID and contains
agreeing official and independent HTTPS claims backed by exact saved snapshot
hashes. It is schedule-only and cannot carry a synthetic API-Sports fixture or
team ID.

Mixed readiness is persisted in additive `drawing_pin_sets` and
`drawing_pin_set_items` tables. Publication is one transaction containing
orders 0 through 14, real per-pin source providers, deterministic source/pin
set hashes, provider distribution, and reviewed catalog identity. Existing
API-Sports-only rows remain readable through the legacy path; no destructive
legacy migration or invented backfill is performed.

Final collection routes API-Sports and reviewed pins through separate source
revalidation. Reviewed pins reload the strict catalog with a 90-minute
freshness limit and use explicit TotoBrief BK probability fallback only after
identity succeeds. The reviewed catalog and every referenced snapshot are
protected inputs and are reloaded immediately before publication. Missing,
stale, cancelled, changed, conflicting, or TOCTOU evidence results in
fail-closed `NO BET`. CLI/scheduler catalog wiring is opt-in, morning remains
passive by default, and no automatic betting path exists.

## Atomic final scheduler protocol

Production final evidence uses a run-scoped canonical `FinalInputSnapshot`
containing the exact direct-detail payload, capture time, target fingerprint,
normalized 15×3 BK probability hash, detail hash, attempt/plan identity, and
optional timing-override hash. Loading revalidates the canonical document,
payload, probability matrix, drawing identity, deadline, and snapshot hash;
post-capture mutation fails closed. Captured payload ingestion is a local
database operation and does not perform another TotoBrief request.

Scheduler plan schema v4 defines T−45 warmup, T−30 refresh, T−20 final,
T−16 retry, and T−12 hard publication times plus explicit final-runtime,
publication-reserve, attempt-count, and bounded-backoff configuration.
Generated LaunchAgent candidates contain all five triggers and remain
generation-only; automated upload and betting are absent.

Each normal `scheduler-execute` invocation is a short-lived idempotent tick
under a plan-scoped file lock. Hash-chained persistent state records every
attempt and supports orphan recovery. Warmup/refresh failures are diagnostic;
final attempts have isolated directories and bounded transient retry. A final
tick captures one detail snapshot at response completion, refreshes unchanged
15-pin preparation evidence from it, and injects the same payload into EV
without another detail request. Runner manifest v5, package archive manifest
v2, and durable archive columns bind the snapshot and normalized probability
hashes. Final calculation completion, subprocess timeout, and every retry
admission use the actionable cutoff
`T−12 − publication_reserve_seconds`. The remaining interval through hard
T−12 is reserved exclusively for package/archive-manifest writing, durable
archive, recovery, status, and `.bet-ready` marker work. Those publication
steps use hard T−12. Recovery may finish within the reserve, including exactly
at T−12; after T−12 it removes stale package and archive-manifest files before
recording coupon-free zero-cost `NO BET`.

Retry classification is structural: typed scheduler errors, TotoBrief HTTP
status, and explicit categories are inspected; message text is never parsed.
HTTP 503/timeouts remain retryable, while typed final-input, identity, manifest,
package, and hash integrity failures are terminal. Production schema-v4
execution is tick-only; explicit `--run-id` is reserved for simulation.
Persistent `bet_ready`/`publish=complete` state is committed only after the
exclusive `.bet-ready` marker exists and verifies. A non-deadline marker
failure removes actionable package bytes and becomes terminal `failed`; a
hard-T−12 crossing removes the same bytes and becomes zero-cost `NO BET`.
Later ticks cannot mistake either case for a published package. Archive
recovery also compares the persisted atomic-final timing-override hash with the
current semantic override hash before publication.

## Dynamic morning dispatcher protocol

The recurring morning boundary is drawing-neutral. One generic
`morning-dispatch` invocation resolves exactly one current drawing from a fresh
page-one response, validates one exact detail payload, performs systematic
preparation from that pinned identity, and records the visible number, internal
ID, deadline, fingerprint, detail hash, readiness, and eligibility. It creates
or reuses one schema-v4 evening plan only when preparation is 15/15,
eligibility is playable, and the complete five-tick schedule can still start
before T−45.

The dispatcher has a process lock and persistent per-drawing state keyed by
drawing ID, deadline, and fingerprint, independent of the morning date.
Repeated morning
triggers are idempotent; a deferred preparation may be retried, while
ambiguous selection, missing identity/deadline, timing spans outside policy,
conflicting state, or a late dispatch fail closed. Time is reacquired after
network preparation before the T−45 plan-generation gate. The recurring
wrapper never contains a drawing number. The generated evening plan owns the
exact drawing identity and its independent T−45/T−30/T−20/T−16/T−12 ticks.

Plan, wrapper, and plist bytes are generated once. The dispatcher persists
`scheduled/generated` before activation. A retry after bootstrap failure or a
crash verifies and reuses the exact plan, wrapper, and plist bytes before
invoking activation, then advances only the activation state. A conflicting,
tampered, or partial artifact set fails closed.

Unresolved preparation is a separate passive preflight state machine. It
writes a fingerprint-bound attention marker, append-only attempts, candidate
and provider diagnostics, a strict reviewed-schedule queue when the provider
has no identity-bearing fixture, and an idempotent retry plan at
T−360/T−240/T−180/T−120/T−90. Every retry carries exact expected drawing
identity, stops before T−60, performs no busy sleep, and omits activation.
`preflight-status --open` reads the current DB and these artifacts without
schema initialization or mutation. Attention clears only when the same
fingerprint reaches atomic READY 15/15.

Generation is deliberately separate from activation. Generic morning
artifacts are passive by default and omit `morning-dispatch --activate`;
`morning-preanalysis-plan --activate-evening` is the explicit post-drill
opt-in. A passive recurring job may synchronize, prepare, record diagnostics,
and generate an exact evening plan, but cannot install that plan. Neither a
schema-v4 evening scheduler nor automatic bet path is installed. The passive
generic dispatcher is installed as `com.totoai.morning-dispatcher.v1` at
08:00/10:30 Moscow time. New generated candidates default to
08:00/10:30/12:00 and remain uninstalled. The five obsolete drawing-specific
LaunchAgents were
removed on 2026-07-28.

## Emergency pre-bet safety boundary

- `package.audit.evaluate_package_safety` is the pure exposure/probability
  decision gate and returns hash-bound thresholds, reason codes, and the exact
  uploadable coupon set.
- `ev.drawing` applies it only when `EVConfig.package_safety_enabled` is true;
  `DrawingRunnerConfig` enables it by default for production-playable runs.
- Runner reports serialize hash-bound `package_safety` probabilities,
  thresholds, reasons, original evaluated coupons/package SHA-256, and
  separately approved uploadable coupons. Scheduler ingestion uses the same
  canonical `PackageSafetyConfig` and `evaluate_package_safety` implementation
  to recompute every non-null record before either PLAY or NO BET processing;
  declared manifest decisions are not trusted.
- Scheduler `NO BET` accepts valid recomputed safety in either state: rejected
  by safety, or passed before a later timing/self-dilution rejection. The
  machine-readable package/terminal reason identifies the actual gate; the
  scheduler never emits package bytes or `.bet-ready` for either form.
- `SchedulerPlan` owns the canonical package-safety thresholds and includes
  them in its semantic payload/plan identity. Generated package commands pass
  the same values to `run-drawing`; manifest parsing compares against and
  recomputes with this trusted plan config rather than manifest thresholds.
- Preparation readiness summaries bind the 15 TotoBrief probability rows and
  source fetch time. Production resource loading requires ready 15/15 pins,
  no unresolved orders, playable eligibility, a matching probability hash,
  and input age within 24 hours.
- Unsafe but structurally valid packages become zero-cost `NO BET`.
  Invalid/stale operational evidence raises a machine-readable
  `preparation_fail:*` failure and produces no package.
- Post-draw result refresh is a separate non-betting boundary. It accepts only
  one explicit drawing ID/number, appends immutable result snapshots, archives
  reproducible package bytes, and writes hash-bound immutable settlements.
  Its bounded retry state never selects an open/next drawing or emits betting
  markers.
- Actionable scheduler publication durably writes canonical pre-bet package
  evidence before `.bet-ready`. Settlement requires matching pre-existing
  archive evidence; legacy imports are explicit and cannot be relabeled as
  pre-bet runner provenance.
- Systematic preparation and production preflight share one exact persisted
  drawing identity (internal ID, visible number, and `ended_at`). Scheduler
  publication verifies that identity during archive import and enforces T−12
  again directly after the database write and directly before marker creation;
  late publication bytes/markers are removed while the archive remains.

Current pipeline:

```text
TotoBrief API
-> Collector
-> SQLite
-> Validation/Audit
-> Baseline Brief Generator
-> Cover Engine
-> Exact Cover Verifier
-> Direct Package Optimizer
-> Strategy Backtest / Frozen Experiment Manifest
-> Hybrid Development Seal
-> Backtest Engine
-> Future Research/ML
-> Package Export
```

Approved target pipeline for the Hybrid Package Program:

```text
Morning exact drawing preparation
-> Frozen market + lawful sports-statistics snapshots
-> Calibrated event probabilities with explicit market-only fallback
-> Cover + EV + Hybrid package candidates under one dynamic bank
-> Common probability/EV/Hamming/concentration audit and comparison
-> Evening exact revalidation and one atomic manual-upload recommendation
-> Append-only prospective package archive
-> Post-draw forced result/payout refresh
-> Settlement of every archived package
-> Immutable expected-vs-actual ledger and prospective gates
```

The three strategy boundaries are explicit:

- Cover owns the brief, target category, compact package, and exact conditional
  Hamming verification.
- EV owns exact full-space monetary-EV ranking and does not inherit a category
  guarantee from its derived union brief.
- Hybrid owns the future multi-objective package selection that combines
  calibrated final probabilities, category-hit probability, Hamming/coverage,
  EV, and frozen concentration/diversity constraints.

The common probability boundary will persist source timestamps, market prior,
optional sport-model output, calibrated final probabilities, model/config
hashes, fallback reason, and provenance for each of the 15 events. Official or
reputable sports data is collected/cache-frozen in the morning and backfilled
under the same as-of rules. Evening generation may refresh eligible inputs but
must remain able to fall back explicitly to the last valid snapshot or market
prior rather than depend on a last-minute provider request.

The common package boundary will persist strategy, phase, dynamic
requested/effective/used bank, stake, exact ordered coupons, probability/pool/
sports snapshots, algorithm/config/code versions, package hash, union brief,
event frequencies, concentration, Hamming and conditional category coverage.
The post-draw boundary force-refreshes authoritative results, settles every
archived package for hits/categories/cost, and records payout/profit/ROI only
when actual payout evidence is available. Package, result, and settlement
records are append-only and idempotent.

The completed first implementation slice adds only strategy metadata and the
common package audit/report contract. It is implemented in
`toto_ai.package.audit` and `toto_ai.package.audit_reports`, with CLI
`package-audit`. Exact union-brief distance/category coverage uses an
independent exact streaming distance calculation. The slice does not change
package selection, probabilities, live scheduler behavior, or bet publication.

Coordinated morning synchronization path:

```text
TotoBrief page one through cross-process request coordinator
-> Atomic SQLite summary/status commit for every listed drawing
-> Select exact next playable drawing only from that fresh page-one response
-> Fresh validated exact raw detail cache OR coordinated drawing-info request
-> Idempotent drawing/event/quote upsert and cache provenance
-> Existing API-Sports date expansion and systematic preparation
-> Atomic ready preparation + 15 pins OR explicit deferred/unresolved exit
```

The request coordinator stores schema-versioned timing/backoff state with
`written_at`, block source, and server-authoritative `Retry-After` in
`data/totobrief-cache/request-state.json`. A process lock, symlink-safe root
containment, fsynced atomic replacement, a maximum plausible-state policy, and
a bounded local wait protect separate invocations without shortening a valid
server block. Summary persistence is not rolled back when detail is deferred.
Raw detail is operational only with its fsynced sidecar commit marker and valid
schema/hash/identity/freshness. It must contain exactly 15 unique contiguous
event orders (`0..14`) and complete pool/BK quote triples. `prepare-drawing` is
local/cache-first by default; network refresh is explicit, avoiding an
immediate duplicate detail request after synchronization.

Systematic production identity path:

```text
Exact TotoBrief drawing fingerprint and 15 event IDs
-> Reviewed/context-scoped team registry and provider-team IDs
-> Progressive cached provider schedule dates with isolated failures
-> Conservative oriented candidate resolver (context + uniqueness + margin)
-> Unresolved diagnostics/review queue OR atomic ready preparation + 15 pins
-> Final recent schedule revalidation by fixture/team IDs and starts_at
-> Authoritative fresh 15/15 revalidation summary (manifest schema v4)
-> Pinned collection without display-name rematching
-> Existing timing/audit/EV runner
-> Scheduler T−12 publication cutoff when the final package remains valid
```

Reviewed alias catalog schema v2 can bind a canonical team to provider team ID,
country, and competition context. Team identity never hardcodes a fixture.
Domestic competition resolution rejects global provider competitions.
Sufficient observed provider coverage may distinguish
`source_missing_competition` from a generic missing candidate, but both remain
unresolved and publish no pin.

Deterministic offline replay uses the same identity boundary without live
adapters:

```text
Strict saved TotoBrief target + strict saved provider schedule + aware as-of
-> Mandatory isolated replay root and contained mutable paths
-> Cache hash and exact drawing/fingerprint/event-order validation
-> Atomic preparation + exactly 15 pins
-> Fresh cached provider/fixture/team/orientation/start revalidation (15/15)
-> Standard runner timing/audit/diagnostic EV
-> Manifest schema v4 with non-actionable replay provenance
-> Runner JSON/Markdown only (no package and no scheduler markers)
```

Replay roots are validated without writes, must not overlap repository/live
data/report/cache/marker roots, and may not traverse symlinks. The root is then
created and revalidated before SQLite initialization. Scheduler ingestion of a
replay manifest terminates as `ignored` with status evidence only and no marker;
the normal production error path continues to publish `.failed`.

Evening scheduler plans use schema v2 and bind one absolute `project_root`.
The generated shell wrapper changes to that root, the LaunchAgent candidate
sets it as `WorkingDirectory`, and production subprocesses receive it as
`cwd`. Systematic preflight consumes the shared warmed project raw/API-Sports
caches, while fallback and final package generation continue to use immutable
run-scoped caches. Schema-v1 plans remain readable through strict root
inference; artifact regeneration is required to add wrapper/plist defenses to
an already generated candidate.

The compatibility matcher remains available only for an explicitly opted-in
direct run. Scheduler preflight always prepares the open drawing and scheduler
package phases cannot silently use legacy name matching.

Fresh playable EV path:

```text
TotoBrief API page one
-> Nearest future active/expected drawing
-> Immediate drawing-info snapshot
-> Strict 15-event BK/pool input
-> Reusable exact EV components
-> Prize-factor surfaces and dynamic-bank selection
-> Read-only exact drawing/fingerprint timing lookup
-> Playable only when all 15 effective starts fit within two Moscow dates
-> Rollback-safe CSV/Markdown package reports
```

Historical modeled-EV path:

```text
Validated frozen strategy manifest
-> Holdout IDs excluded in the Drawing query
-> Finished SQLite candidates scanned newest-first until N complete results
-> Strict 15-event BK/pool inputs without result columns
-> One reusable EVComponents build per drawing
-> One complete surface/ranking per prize factor
-> Dynamic-bank and threshold packages plus deterministic hashes
-> Actual results loaded only after every package hash is complete
-> Completed-row checkpoint with coupon manifests bound to canonical row contexts
-> Diagnostic skips are always re-evaluated
-> Configuration-hash-scoped modeled CSV/Markdown reports
```

Important modules:
- `toto_ai.api.client`: TotoBrief API client.
- `toto_ai.api.rate_limit`: coordinated retry, `Retry-After`, backoff, and
  cross-process minimum-interval state for all normal TotoBrief requests.
- `toto_ai.api.detail_cache`: exact schema/hash/identity/freshness validation
  and atomic raw drawing-detail cache persistence.
- `toto_ai.collector.sync`: historical drawing collector.
- `toto_ai.operations.sync_prepare`: minimal page-one plus exact-detail
  synchronization used by morning preparation without duplicate detail fetch.
- `toto_ai.db.models`: SQLite schema with SQLAlchemy models.
- `toto_ai.db.session`: database initialization and session helpers.
  Development diagnostics use its SQLite `mode=ro` engine and never initialize
  or migrate the selected database.
- `toto_ai.analytics.history`: historical summary and research metrics.
- `toto_ai.analytics.audit`: database audit and quality checks.
- `toto_ai.analytics.calibration`: bookmaker and pool calibration research.
- `toto_ai.analytics.brief_oracle`: oracle brief research for completed
  drawings using BK probabilities and actual results.
- `toto_ai.analytics.budget_oracle`: budget-constrained oracle benchmark that
  compares oracle package hits with the baseline brief generator, with progress,
  timeout, partial CSV, per-drawing timing diagnostics, and optional candidate
  workload profiling. Unsafe dominance and full-cover cost pruning are disabled;
  only strict hit-bound incumbent pruning is allowed.
- `toto_ai.analytics.api_inspector`: raw API inspection and drawing resolution.
- `toto_ai.analytics.validation`: raw JSON vs SQLite validation.
- `toto_ai.analytics.research_bk_vs_norm`: BK vs normalized odds study.
- `toto_ai.package.mvp`: MVP covering approximation package generator.
- `toto_ai.package.backtest`: MVP package backtest engine.
- `toto_ai.ev.models`, `toto_ai.ev.prize`, and `toto_ai.ev.reference`:
  immutable EV domain types, official prize/crowd math, and the independent
  brute-force oracle.
- `toto_ai.ev.ternary`: exact complete-space EV components and light prize-fund
  materialization without coupon truncation.
- `toto_ai.ev.package`: deterministic complete-surface ranking and Research or
  Playable dynamic-bank package selection. Package selection and bounded top
  diagnostics can share one complete ranking without truncating the surface.
- `toto_ai.ev.drawing`: page-one-only fresh open-drawing resolution, strict
  drawing-info parsing, reusable sensitivity orchestration, and the 1%
  self-dilution support gate. Sensitivity surfaces are processed sequentially;
  only scalar summaries and the requested main surface/package are retained.
  It does not consult SQLite.
- `toto_ai.external_odds.timing_overrides`: reviewed timing override catalog
  loading, strict catalog provenance, and overlay validation.
- `toto_ai.external_odds.domain` and `toto_ai.external_odds.targets`:
  provider-neutral immutable external-odds records, strict TotoBrief
  drawing-target parsing with explicit nullable event start times, explicit
  sport classification, and preserved
  TotoBrief BK fallback probabilities for the API-Sports coverage audit.
- `toto_ai.external_odds.consensus`: strict football full-time and hockey
  regulation-time three-way market validation, duplicate bookmaker rejection,
  per-book de-vig, median consensus, and explicit minimum-bookmaker fallback.
- `toto_ai.external_odds.timing_overrides` and `toto_ai.external_odds.collection` and `toto_ai.external_odds.storage`:
  deterministic 15-event prospective external-odds collection, explicit
  event-level TotoBrief BK fallback, provider quota/request/cache provenance,
  and append-only SQLAlchemy persistence for immutable collection snapshots.
  Matcher v4 keeps exact/reviewed-alias matching first and adds a constrained
  transliterated fallback only for Cyrillic targets with missing English names.
  It requires minimum pair/team scores and a deterministic lead over the
  runner-up. Low-confidence candidates remain unconsumed. Unique same or
  reversed matches record orientation; reversed matches swap only consensus
  `1`/`2` probabilities into TotoBrief orientation while raw provider prices
  remain unchanged. Orientation and matching evidence are part of collection
  identity, storage, and reports.
  Collection run `fetched_at` is the external observation time and is at least
  as late as every consumed provider market fetch timestamp; the fresh
  TotoBrief drawing-info timestamp is stored separately as `target_fetched_at`.
  Event dispositions persist matched schedule payload hash/fetch time and the
  complete matching decision. Quote rows persist market payload hash/fetch
  time and canonical source provenance. Exact duplicate bookmaker/market keys
  are consensus-ineligible and coalesced into one deterministic anomaly row so
  the mandated database uniqueness constraint does not discard the collection.
  Quote order is canonical before identity, comparison, insertion, and load.
  When immutable snapshots have the same external observation timestamp,
  SQLite latest-snapshot reads use append order before collection-ID order so
  a completed progressive expansion cannot be superseded by its base pass.
- `toto_ai.external_odds.team_registry`,
  `toto_ai.external_odds.team_resolution`, and
  `toto_ai.external_odds.preparation`: context-scoped reviewed identities,
  conservative provider candidate evidence, unresolved review persistence, and
  atomic exact-drawing preparation. A ready preparation owns exactly 15
  fixture-unique pins. Final collection revalidates provider fixture/team IDs,
  start time, and schedule freshness without consulting changed display names.
  Preparation can consume saved local schedule caches for deterministic replay
  or fetch progressive per-date schedules through the provider cache/retry and
  quota boundary. TotoBrief championships are conservatively parsed into
  sport/country/competition/league context. Country values pass through shared
  stable identities covering Russian, English, and ISO forms before comparison;
  mismatched identities and competition levels still fail closed. After every
  successful date, the accumulated schedule is resolved without publishing.
  Fetching stops only at unique 15/15 resolution with normal playable two-day
  timing. Later unrequested dates are not failures; every attempted failure
  before readiness prevents atomic READY publication.
- `toto_ai.external_odds.prospective`: fresh-by-default multi-pass collection.
  It resolves one TotoBrief target, creates one isolated cache session, and
  reuses that session across new provider clients after minute-quota resets.
  Only quota, provider schedule, and provider odds failures trigger another
  pass. Missing-start exact-pair misses may enter a separate bounded expansion
  phase through day five; known-start misses do not. Every pass remains an
  immutable stored 15-disposition snapshot.
- `toto_ai.external_odds.audit` and `toto_ai.external_odds.reports`:
  read-only coverage auditing over the latest complete stored external-odds
  snapshot per drawing, registered prospective GO/PENDING/STOP gate predicates,
  diagnostic overall/sport/league/drawing metrics, exact canonical fallback
  classification, fallback-reason summaries, quota/request summaries, and
  rollback-safe deterministic CSV/Markdown coverage reports. Aggregate CSV and
  every Markdown scope table expose the complete coverage metric schema,
  including bookmaker availability at thresholds one, two, and three. These
  modules do not call providers and do not affect playable package decisions.
  Disposition CSV rows expose stored schedule and market fetch provenance plus
  per-run actual HTTP request attempts, cache-hit counts, target fetch
  provenance, and quota counters. CSV and Markdown expose the fixed collection
  consensus configuration and ordered gate actual/threshold/pass evidence.
  End-to-end acceptance covers mixed success/fallback, provider failure, quota
  cutoff, interruption rollback, deterministic report evidence, EV
  non-interference, and API-key absence across persisted data, cache artifacts,
  CLI output, recursive exception chains, and reports. The timing acceptance
  matrix additionally covers ordinary two-day, day-five expansion, partial
  schedule failure, confirmed multi-day, and unresolved drawings through
  collection, SQLite reload, audit/report, and playable/research output.
- `toto_ai.runner.reports`, `toto_ai.runner.orchestration`,
  `toto_ai.runner.scheduler`, `toto_ai.runner.scheduler_state`,
  `toto_ai.runner.final_input`, `toto_ai.runner.morning_dispatch`, and
  `toto_ai.runner.models`: runner manifest v5, immutable one-fetch final input,
  mandatory exact 15/15 schedule/identity evidence, strict parsing,
  hash-chained state, plan-scoped locking, restart/recovery, dynamic
  drawing-neutral morning dispatch, and independent scheduler ticks at T−45,
  T−30, T−20, T−16, and T−12 with terminal markers (`.bet-ready`, `.no-bet`,
  `.failed`).
- `toto_ai.ev.backtest`: chronological modeled-EV evaluation with SQL-level
  frozen-holdout exclusion, pre-result package hashing, complete factor
  rankings reused across dynamic banks and thresholds, cumulative realized
  9..15 indicators, live-compatible 1% self-dilution suppression, and hardened
  exact-config completed-drawing checkpoints. Latest-N selection backfills past
  incomplete or invalid newer candidates without reading result values before
  package hashes exist. Checkpoint-only package manifests bind each hash to its
  exact canonical 15-outcome coupons and sorted unique `(drawing, bank,
  threshold, factor)` row contexts. Resume rejects missing, duplicate, orphan,
  swapped, non-canonical, or tampered records. Diagnostic checkpoint skips are
  never resumable state; final report rows contain no manifest payloads.
- `toto_ai.ev.reports`: deterministic EV package CSV/Markdown rendering and
  modeled-backtest reporting with rollback-safe atomic pair publication,
  including rollback for interruptions and other `BaseException` failures
  after publication begins.
- `toto_ai.optimizer.cover`: Cover Engine and exact cover verification, with
  cached parsed positions, suffix expansion reuse, and cached coverage bitsets.
- `toto_ai.optimizer.cover_benchmark`: representative Cover Engine benchmark
  with optional cProfile output.
- `toto_ai.optimizer.brief`: baseline brief generator.
- `toto_ai.optimizer.brief_backtest`: baseline brief generator backtest engine.
- `toto_ai.optimizer.coupon_probabilities`: normalized BK probability matrices,
  coupon probabilities, and exact deterministic top-k coupon enumeration.
- `toto_ai.optimizer.coupon_candidates`: deterministic scenario sampling and
  direct coupon candidate generation.
- `toto_ai.optimizer.direct_package`: weighted scenario-coverage package
  optimizer with deterministic budget filling.
- `toto_ai.optimizer.hybrid_evaluation`: deterministic hybrid development
  sealing, fixed five-fold evaluation rows, aggregate fold metrics,
  deterministic GO/STOP selection, development-only evaluation runner, and
  atomic deterministic CSV/Markdown reports for the approved core fractions.
  The seal separately binds the canonical development CSV, pre-drawing
  development inputs, development results, fixed hybrid protocol, and clean Git
  code version. Its CSV/manifest pair uses rollback-safe atomic publication.
- `toto_ai.optimizer.strategy_backtest`: comparable baseline-brief,
  top-probability, and weighted-coverage strategies; chronological backtesting;
  paired holdout evaluation; frozen experiment manifests and report exports.
- `toto_ai.optimizer.strategy_diagnostics`: fail-closed development-only
  regeneration, frozen package-hash/result validation, package structure and
  overlap metrics, paired threshold transitions, and deterministic reports.
- `toto_ai.cli`: Typer CLI entry point.

Important CLI commands:
- `supported`: list supported TotoBrief drawing communities.
- `drawings`: fetch drawing pages from TotoBrief.
- `info`: fetch one drawing-info payload.
- `collect`: collect historical drawings into SQLite.
- `sync-prepare --open`: commit page-one status metadata, synchronize the exact
  open drawing from validated cache or one coordinated detail request, then run
  systematic API-Sports preparation. Deferred detail exits fail-closed.
- `sync-prepare --open --sync-only`: run the same strict TotoBrief selection,
  detail validation, and persistence but stop before API-Sports, preparation,
  or pin writes.
- `sync-prepare --open --expected-drawing-number N`: require the fresh
  page-one open candidate to have visible number `N` before detail fetch,
  preparation, or pin publication. A missing or different drawing fails
  closed.
- `research`: print historical analytics.
- `inspect-events`: inspect event-level pool/BK/result diagnostics.
- `audit`: audit database quality and completeness.
- `inspect-api`: inspect raw API JSON by id, number, latest, live, or open draw.
- `predict --open`: placeholder for future prediction engine.
- `validate`: validate raw API data against SQLite and analytics.
- `study-bk`: study BK probabilities vs normalized odds.
- `calibration`: measure bookmaker and pool probability calibration.
- `brief-oracle`: find minimum oracle briefs that contain actual results.
- `budget-oracle`: benchmark the best oracle package under budget against the
  baseline generator. Use `--profile-workload` for candidate workload
  diagnostics.
- `package-mvp`: generate an MVP covering approximation from a manual brief.
- `backtest`: backtest the older MVP package generator.
- `cover`: generate a greedy cover package from a manual brief.
- `verify-cover`: exactly verify cover package coverage against a brief.
- `benchmark-cover`: profile Cover Engine performance on a representative brief.
- `benchmark-ev`: verify and profile the exact EV engine.
- `ev-package --open`: resolve and fetch one fresh TotoBrief payload, compute
  exact modeled EV, and resolve timing eligibility from SQLite in read-only
  mode using that same payload fingerprint. Playable output is published only
  for exact `playable` eligibility; all other timing states return zero-cost
  `NO BET`. Research retains EV/ranking and reports the timing warning.
- `backtest-ev`: evaluate dynamic banks, prize factors, and gross-EV thresholds
  chronologically while requiring and excluding a frozen strategy holdout.
- `collect-external-odds --open`: collect fresh prospective API-Sports odds for
  one pinned drawing, automatically retry approved operational fallbacks,
  progressively expand null-start exact misses from two through five days,
  and store every 15-disposition pass. `--reuse-cache` explicitly enables the
  old shared-cache diagnostic path.
- `audit-external-coverage`: audit stored complete external-odds snapshots in
  read-only mode and publish deterministic coverage reports.
- `build-brief --open`: build a baseline brief and package for the next playable
  drawing.
- `backtest-brief`: backtest the baseline brief generator on finished drawings.
- `freeze-strategy-experiment`: freeze exact drawing IDs, protocol/data hashes,
  and code version before a direct-strategy evaluation.
- `backtest-strategies`: compare package strategies on a frozen chronological
  development/holdout experiment.
- `diagnose-strategies`: regenerate and verify frozen packages, then diagnose
  strategy structure and paired 13+ transitions on development drawings only.
- `seal-hybrid-development`: stream the development prefix of a frozen strategy
  CSV and write a development-only CSV plus an augmented manifest from a
  read-only database.
- `evaluate-hybrid`: regenerate and evaluate fixed hybrid packages only on the
  sealed development segment, write atomic reports, and print the GO/STOP
  decision from an enforced read-only SQLite database.
- `run-drawing --open`: safely preflight and pin one open drawing, wait for the
  T-20 final window, revalidate the target, collect fresh API-Sports odds,
  check exact stored timing, audit the latest 30 snapshots, build the existing
  EV package, and publish linked runner reports. Preflight validates every
  candidate output against the database, aliases, cache root, and sibling
  outputs before provider construction or waiting; publication repeats the
  check. The injected T-5 boundary reaches schedule/odds pages and transport
  retries, completing the immutable pass with explicit safety-stop fallbacks
  and no later provider calls. A second fresh EV payload must still match the
  pinned target before heavy work. Publication is a final deadline-aware
  all-artifact transaction: pre-commit `BaseException` restores/removes every
  child and runner artifact, while a committed publication is success. Every
  `NO BET` omits the EV child report and linked coupon strings. Runner manifest
  now uses schema v4: v3 raw/effective timing and budget provenance plus an
  authoritative pinned-revalidation summary. Historical schema v2/v3 output
  files are legacy and fail closed for actionable scheduling. The command
  never submits a bet.
- `run-drawing --offline-replay --drawing-id ... --target-cache ...
  --schedule-cache ... --replay-as-of ... --replay-root ... --mode research`:
  run one exact saved
  drawing through preparation, pins, cached fresh revalidation, runner, and
  manifest v4 with an injected clock. This branch does not read environment
  credentials or instantiate network clients. It validates strict cache
  schemas/hashes, exact target identity, and a symlink-free isolation root;
  emits `RESEARCH ONLY`; writes only beneath that root; and is ignored without
  markers by scheduler ingestion.
- `prepare-drawing --open` or `--drawing-id`: prepare one exact drawing from
  synchronized local TotoBrief identity/detail cache and live cached schedule
  dates or `--schedule-cache`, persist review diagnostics when unresolved, and
  atomically publish a ready preparation plus 15 pins. It performs no
  TotoBrief detail request by default; `--refresh-totobrief` is explicit.
  Explicit `--target-cache` is operational only with `--drawing-id`, canonical
  `drawing_<id>.json` naming, a valid mandatory sidecar, and an exact playable
  drawing already synchronized in SQLite.
  Unresolved output is machine-readable and exits nonzero.
- `scheduler-plan`: build immutable scheduler plans, wrapper scripts, and
  LaunchAgent candidates for the fixed phase boundaries (`T−45`, `T−30`,
  `T−20`, `T−16`, `T−12`). The plan's gross-EV threshold is passed through the exact
  `run-drawing --min-gross-ev` CLI contract. Optional `--env-file` produces a
  wrapper that validates and sources a user-owned regular non-symlink file
  whose mode is no broader than `0600`; the plist contains only the wrapper
  path and no credentials.
- `morning-preanalysis-plan`: generate, but never install, a separate launchd
  candidate beneath `reports/rehearsal`. Its wrapper uses the same secure env
  contract and invokes drawing-neutral `morning-dispatch` at configured times.
  A ready invocation creates or reuses one exact per-drawing schema-v4 plan;
  it never uploads a package or places a bet.
- `morning-dispatch`: resolve, validate, pin, prepare, and persist one current
  drawing under a lock, then generate one idempotent evening plan only before
  T−45.
- `scheduler-execute`: run one short-lived resumable tick, capture one immutable
  final detail for a final attempt, strictly verify the bound runner/archive
  evidence, recover safely from restart, and publish `.bet-ready` only before
  T−12.

## Audit-only sports-statistics evidence

The first sports-statistics vertical slice is isolated under
`toto_ai.sports_stats`:

```text
ready exact 15/15 drawing pins
-> API-Sports football target context
-> completed fixtures strictly before min(as_of, target kickoff)
-> optional league standings
-> immutable provider-neutral feature records
-> append-only SQLite snapshot
-> JSON/CSV/Markdown audit report
```

`collect-sports-stats` supports one exact selector (`--open`, `--drawing-id`,
or `--drawing-number`) and an explicit cache-only `--historical-as-of`.
Prospective collection fails closed at the drawing deadline. Target fixtures,
future fixtures, and non-finished/cancelled/postponed fixtures are excluded
locally regardless of provider ordering.

Historical mode resolves drawing identity only from SQLite, loads a
hash-verified TotoBrief raw-detail cache/sidecar captured no later than
`as_of`, and invokes API-Sports with `cache_only=True` for every endpoint. It
does not construct or call a TotoBrief network client. Missing or newer frozen
detail is a command error; missing provider history remains explicit
market-only evidence.

Run construction enforces exact run/event parity for drawing ID/number,
fingerprint, provider, captured-at, as-of, and deadline. Source providers and
the run's request-fingerprint set must match event evidence. Provider history
rows for unrelated teams are discarded. Empty/error/plan-denied history is
stored as an unavailable (`None`) window, so report feature cells are blank
rather than numeric zeros. API-Sports standings support is read from the
actual `league.standings` field.

The additive `sports_stats_runs` and `sports_event_feature_snapshots` tables
are append-only. The package does not import prediction, package, runner,
scheduler, result, or settlement code. Reports state `AUDIT ONLY`,
`package influence: NONE`, and `fallback: MARKET ONLY`.

API-Sports free-plan denials are represented as
`provider_plan_unavailable`, never as zero-valued features. Sports evidence
cannot affect bookmaker probabilities or PLAY until a separately frozen
chronological out-of-sample gate passes.

## Data-health contract v1

`toto_ai.analytics.data_health` is the reusable read-only quality boundary for
the SQLite history. Contract version `1.0.0` evaluates every selected drawing,
emits stable reason codes, and computes independent eligibility for
`historical_inventory`, `backtest_probability`, `result_settlement`, and
`prospective_generation`.

The contract distinguishes missing quote rows, invalid `0/0/0` pools,
incomplete BK, result gaps, explicit terminal VOID, canonical RAW/result
snapshots, and unsettled canonical `pre_bet_runner` packages. Numeric gaps and
duplicate visible numbers are report-level metadata rather than invented
drawing rows. Canonical RAW discovery is deliberately limited to the sibling
`data/raw` tree; rehearsal, report, and test-fixture JSON do not satisfy
provenance.

`data-health` opens SQLite in read-only mode and exports detail plus aggregates
to CSV/JSON/Markdown. Baseline prospective brief generation and the
MVP/baseline/strategy backtests call the same API. Generation always fails
closed. Historical commands may continue only through the explicit
`--allow-unhealthy-research` override, which is persisted in summaries and
printed as research-only.
