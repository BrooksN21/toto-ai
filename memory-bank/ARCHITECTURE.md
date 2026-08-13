# Architecture

## Operator export gateway

The only operator-facing package flow is:

```text
fresh final PLAY
-> run-scoped package.csv
-> durable package-archive.json + SQLite ArchivedPackage
-> run-scoped baltbet-upload.txt + actionable operator-result.json
-> .bet-ready written last
-> operator-export revalidates all bindings before T-10
-> explicit project-local output file for manual BaltBet upload
```

`operator-export` is read-only with respect to package selection and never
places a wager. It rejects `NO BET`, paper/research/LKG files, missing or
foreign paths, hash/identity drift, archive mismatch, and T-10 expiry. The
ordinary scheduler command no longer prints internal/audit package paths as
operator packages. At T-10 the upload surface is deleted and the operator
result becomes non-actionable; archive/marker bytes remain audit evidence.

Morning preparation keeps identity coverage and kickoff evidence distinct.
A baseline-only identity row with no kickoff produces a `timing_unknown`
dependency even when preparation is READY 15/15. It enters the same
fingerprint-bound attention/review/retry system, requires reviewed schedule
evidence, and cannot create an evening plan until a retry is fully playable.

## Last-known-good package boundary

Schema-v6 tick execution now has an append-only `last-known-good/checkpoints/`
store plus an atomically replaced `last-known-good/current.json` pointer.
Checkpoint validation binds plan/drawing identity, deadline, stake/bank,
coupon count/cost/uniqueness, package hash, drawing fingerprint, probability
input hash, capture time, and explicit non-actionability. `operator-result.json`
exposes `FINAL_FRESH`, `LAST_KNOWN_GOOD_DEGRADED`, or `NO_BET`; a validated
package uses a separate BaltBet upload-text path. The T-45 warmup child receives
`final_lead_minutes = 45` and starts immediately at the triggering phase; it
must not inherit the T-30 fallback lead and wait past its parent deadline.
Every scheduler package phase, including the T-45 warmup and T-30 refresh
fallback paths, captures a run-scoped immutable probability snapshot and binds
that snapshot, the schedule-evidence ledger, and the scheduler plan into
selector provenance. Non-atomic fallback execution is not allowed to pass only
digest values without their referenced artifacts. Because these phases now
produce `FinalInputProvenance`, their runner reports use current manifest
schema v5; scheduler ingestion keeps one current schema contract for warmup,
refresh, and final package phases.
Warmup publication establishes operator availability before final work. The
T-20 primary final owns the full runtime through T-10 minus the publication
reserve. T-16 can retry only after the earlier process releases the scheduler
lock and leaves retryable state; it cannot truncate or overlap a running T-20
calculation.

An authoritative final DNS/transport outage never turns cached data into a
fresh final result. TotoBrief retains its bounded transport retries; after they
fail, scheduler execution preserves and publishes only a previously validated
T-45/T-30 last-known-good package with explicit degraded provenance. If no LKG
exists, the result remains zero-cost `NO BET`.

The safety-repair swap-delta kernel preserves exact integer lexicographic
semantics while evaluating all event/outcome contributions as one `int16`
matrix product. It does not prune candidates, lower sample counts, change the
bank, or reorder tie-breaking. The full 4973 offline profile uses the same
512 quality candidates, 2,048 optimization samples, 8,192 evaluation samples,
and four sensitivity scenarios.

## Current prediction boundary

The package probability matrix is currently the normalized 15-by-3 TotoBrief
BK matrix. TotoBrief pool probabilities are a separate crowd model used by EV
and payout assumptions; they are not sports-performance probabilities.

API-Sports currently contributes event identity, kickoff/schedule evidence,
eligibility, and immutable audit snapshots. Form, goals, and standings are
collected but are not passed into `EVInput` and cannot change coupon ranking or
selection. API-Sports bookmaker consensus is audit evidence only. Injuries,
lineups, xG, and Elo are not implemented.

The provider-neutral sports probability provider is implemented in shadow
mode. It derives a 15-by-3 experimental matrix from frozen pre-deadline
evidence, keeps event-level BK fallback, and publishes source provenance in a
machine-readable `NOT_ACTIVATED` artifact. It is not connected to `EVInput`.

The shadow projection is an untrained Jeffreys-smoothed venue-only W-D-L
estimate. It uses the home team's home W-D-L and the away team's away W-D-L;
aggregate W-D-L is never substituted when either required venue window is
empty. Such an event is explicitly labelled `non_venue_unavailable` and uses
BK fallback, so it cannot count as venue-model coverage. Its candidate blend
uses only the matched venue sample count for evidence weighting against
normalized BK. Aggregate form, goals, rest, and standings are retained in the
artifact as diagnostics, not fitted coefficients. Strict
as-of/deadline, content hash, target fingerprint, event identity, fixture/team
orientation, pin, and source chronology checks fail back to BK per event.

The chronological evaluator compares BK, sports-shadow, and candidate blend by
multiclass log loss, Brier, confidence ECE, coverage, fallback, and validation
counts. OOS BK rows come only from the hash-bound frozen authoritative drawing
snapshot embedded in each pre-`as_of` shadow artifact; mutable current `Quote`
rows are never prediction input. Missing/late authority, fingerprint drift,
future sources, and missing/mismatched orientation are blocking. Ordinary
missing sports history may fall back to BK and lowers coverage without being
mislabeled as leakage. The hard floor of 30 drawings, 450 events, and 70%
sports coverage cannot be weakened by CLI/config; calibration tolerance may
only be stricter than the documented 0.02 maximum. The gate cannot activate
production: even a pass is only `PASS_REVIEW_REQUIRED`, while the artifact
remains `NOT_ACTIVATED`.

The active scheduler contract is schema v6. Quality-v2 is fail-closed
`NO BET / TRAINING-PAPER` and cannot publish an actionable wager-ready marker.
Legacy schema-v5 and marker descriptions later in this file are retained only
as implementation history and are not current behavior. No profitability is
proven.

## Deterministic safety-aware EV package selection

Playable EV selection keeps the complete coupon EV surface, ranking,
threshold, payout and probability mathematics unchanged. When package safety
is enabled, selection starts from exactly `selection_budget // stake`
highest-ranked eligible coupons and applies deterministic constrained swaps.
Each material event/outcome receives at least one coupon, and every
event/outcome count is bounded by
`ceil(near_fixed_share * coupon_count) - 1`, matching the existing safety
gate's strict `share >= near_fixed_share` rejection boundary.

The candidate prefix is drawing-neutral and bank-neutral: at least 32,768
eligible coupons and 128 candidates per requested coupon, expanding fourfold
to at most one million or the complete eligible set. Repair reduces integer
constraint violation first, minimizes gross-EV loss within each deterministic
step, and then restores higher-ranked coupons through feasible one-swap local
improvements. A bounded search that cannot find a feasible exact-cardinality
package returns coupon-free `NO BET` with diagnostics; it never weakens or
bypasses safety. The existing independent final package-safety veto remains
unchanged and authoritative.

Selection diagnostics bind pre/post package hashes, pre/post concentrations,
material-outcome repairs, replacements, gross-EV delta, candidate-universe
size and feasibility reasons. Frozen chronological regressions separate
pre-cutoff quote fixtures from finished outcomes and reproduce the exact old
drawing-4967 package hash before retrospective scoring.

Quality-v2 replaces the binary selector-side material floor with the
configurable continuous target `K*s*p**alpha` and integer floor, constrained by
`0 < s <= 1` and `alpha >= 1` for per-event sum feasibility. The hard safety
cap remains unchanged. A lower soft cap creates concentration headroom and is
optimized before package quality; unresolved headroom is reported.

Within the unchanged deterministic candidate universe, quality repair uses
incremental exposure, pairwise-Hamming, independently sampled P(9+), and exact
weighted-outcome-union P(13+/14+/15) statistics. After hard safety and
non-worsening headroom, the comparison is genuinely lexicographic: P(13+),
P(14+), P(15), evaluation-independent optimization-stream P(9+), diversity,
robust log-EV, then stable rank. Per-tier deadbands prevent numerical noise;
lower tiers never compensate for a meaningful higher-tier loss. Nested
category unions are never added or collapsed into a weighted score.

Optimization and evaluation use domain-separated deterministic MC streams and
report both seeds/sample counts. Diagnostics and manifests bind the exact
probability snapshot, normalized input, ledger byte/semantic hashes, canonical
schema-v6 plan bytes, complete selector configuration, package hash and
self-hash. Missing, mutated, arbitrary or syntactic-only provenance fails
closed. The independent final safety veto remains authoritative.

Quality-v2 produces only a `STRUCTURAL_PASS`/`STRUCTURAL_FAIL` assessment and
explicit `TRAINING/PAPER` coupon fields. Every actionable top-level decision is
`NO BET`; scheduler publication cannot create a wager-ready marker. There is
no trusted local prospective-evidence registry, so release IDs/hashes cannot be
self-declared. A separate independently validated registry/protocol would be a
future architecture change, not a selector field toggle.

## Immutable scheduler ledger binding

Scheduler schema v6 binds the canonical contained schedule-evidence ledger
path, its exact content SHA-256 and its canonical semantic hash into the plan
payload and `plan_id`. Plan creation and loading require a regular,
non-symlink ledger. Schema v5 is permanently unbound and is rejected with an
explicit regenerate-v6 diagnostic rather than being reinterpreted.

Every scheduler tick and phase runner revalidates the bound path, bytes and
semantic identity before phase work. Generated `prepare-drawing` and
`run-drawing` commands carry the same path and both expected hashes. The child
commands validate that binding before provider/package work, and prospective
collection validates it again before every pass. Schedule-evidence pins are
revalidated only against the supplied bound ledger; missing ledgers, hash or
semantic drift, malformed content and immutable pin conflicts are typed
integrity failures.

Emergency retries use `scheduler-recover-plan --source-plan ... --output-dir
...`. The recovery builder clones the current immutable `SchedulerPlan` and
changes only its output scope; it does not expose manual target, bank,
probability, ledger, or reviewed-catalog inputs. This prevents a retry from
silently dropping `reviewed_catalog_hash` or another future plan field.

Child integrity failures use exit code 78 and become
`SchedulerIntegrityError`. They terminalize scheduler state at any stage and
are never retried. Network, TLS, quota and refresh transport failures retain
their existing transient classification. Monotonic baseline-to-reviewed
upgrades, strict provider pins, reversed schedule-only orientation, TotoBrief
`1/X/2` ordering and final fail-closed package safety remain unchanged.

## Atomic monotonic canonical pin enrichment

A ready canonical pin-set is immutable except for one transactionally guarded
upgrade: an unchanged 15-event drawing may replace a `totobrief-baseline`
no-schedule row with a validated `reviewed-schedule` or `schedule-evidence`
row. The preparation merge reuses all non-upgraded rows exactly, including
their source identity hashes and provenance, so a later provider fetch cannot
rewrite strict fixture/team identity merely because transport metadata changed.

For each upgraded order, target event ID/order and canonical home/away team IDs
remain in TotoBrief orientation. A reversed official fixture is represented
only by `provenance.orientation=reversed`; it remains schedule-only and has no
external fixture/team or odds/statistics identity. The publication boundary
independently verifies that every selected reviewed row carries the exact
catalog/ledger hash supplied for the new set. The old rows and parent set are
deleted only inside the same transaction that validates and inserts all 15 new
rows, so any downgrade, ambiguity, schedule conflict or identity/hash drift
leaves the previous ready set intact.

## Deadline identity and publication boundary

Expected drawing deadlines cross the CLI as strict timezone-aware ISO-8601
strings. The project parser accepts `Z` and explicit offsets, normalizes the
exact instant to UTC, and then performs fail-closed drawing identity
comparison. Naive or malformed values never enter dispatch.

The current evening scheduler uses one `PUBLICATION_LEAD_MINUTES = 10`
contract. Plans and status expose `t_minus_10`; the final launchd calendar is
rendered explicitly in `Europe/Moscow`. The actionable computation cutoff is
T−10 minus the configured publication reserve, while the remaining interval
is reserved for durable package publication and a manual-upload marker. No
automatic bet placement exists.

New plans bind a 300-second minimum final runtime, based on the measured
optimized full 4973 run. Admission is checked before a final attempt and again
after immutable final-input capture, immediately before the heavy subprocess.
The scheduler-bound `run-drawing` CLI repeats the check so a manual invocation
cannot bypass the latest safe start.

At the hard T-10 tick, any non-actionable LKG operator upload text expires even
when scheduler state is already terminal. The scheduler deletes the upload
text and current LKG pointer, rewrites the operator result without coupons, and
retains only the source CSV/diagnostics for audit. A manually copied file
outside the plan tree is never a scheduler publication.

Scheduler schema v6 binds `publication_lead_minutes = 10` and the complete
`120/90/60/45/30/20/16/10` trigger-offset vector into the semantic payload and
plan ID alongside the ledger binding. T−120/T−90/T−60 are diagnostic
TLS/API/freshness preflights; they cannot publish a package. Each stage is
persisted and idempotent, while all TotoBrief requests retain shared
cross-process pacing. Generated LaunchAgent labels are explicitly versioned
`v6`, while status uses schema v6 and the same exact deadline map. Schema v4
is the stale T−12 contract and schema v5 lacks ledger identity; both are
rejected with regenerate-v6 diagnostics before production execution or
artifact reuse. No implicit migration is allowed.

Every scheduler failure records a redacted transport message, structural
exception-type chain, transport category, HTTP status when present, and attempt
count. The final phase always requires fresh verified-network TotoBrief detail;
stale cache and successful diagnostic preflights cannot authorize PLAY.

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

After lock acquisition, one timezone-aware eligibility reference instant is
captured for the whole nightly run. Both read-only selection passes and every
per-drawing cooldown admission check use that exact instant; elapsed wall time
cannot add newly eligible drawings to the immutable captured set. The set is
also bound to a deterministic local drawing/event/result fingerprint before
backup or network access. Actual drawing/result identity mutation still fails
closed as selection drift.

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

API-Sports remains the primary schedule/market provider. Provider completeness
is evaluated per target event and API-Sports UTC request date, not across the
whole expanded drawing horizon. When and only when the event's relevant
UTC-date fetch proves it absent as
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

The relevant date is derived from the target start, matched provider fixture,
or strict reviewed evidence, always normalized to UTC because API-Sports
schedule requests use UTC. An unrelated later expansion-date failure cannot
veto an otherwise strict event-level fallback, including local-calendar
cross-midnight cases. A missing or failed relevant UTC date, unknown effective
date, stale/mismatched evidence, identity drift, or ineligible multi-day
drawing still fails closed.

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

Scheduler plan schema v5 defines T−45 warmup, T−30 refresh, T−20 final,
T−16 retry, and T−10 hard publication times plus explicit final-runtime,
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
`T−10 − publication_reserve_seconds`. The remaining interval through hard
T−10 is reserved exclusively for package/archive-manifest writing, durable
archive, recovery, status, and `.bet-ready` marker work. Those publication
steps use hard T−10. Recovery may finish within the reserve, including exactly
at T−10; after T−10 it removes stale package and archive-manifest files before
recording coupon-free zero-cost `NO BET`.

Retry classification is structural: typed scheduler errors, TotoBrief HTTP
status, and explicit categories are inspected; message text is never parsed.
HTTP 503/timeouts remain retryable, while typed final-input, identity, manifest,
package, and hash integrity failures are terminal. Production schema-v5
execution is tick-only; explicit `--run-id` is reserved for simulation.
Persistent `bet_ready`/`publish=complete` state is committed only after the
exclusive `.bet-ready` marker exists and verifies. A non-deadline marker
failure removes actionable package bytes and becomes terminal `failed`; a
hard-T−10 crossing removes the same bytes and becomes zero-cost `NO BET`.
Later ticks cannot mistake either case for a published package. Archive
recovery also compares the persisted atomic-final timing-override hash with the
current semantic override hash before publication.

## Dynamic morning dispatcher protocol

The recurring morning boundary is drawing-neutral. One generic
`morning-dispatch` invocation resolves exactly one current drawing from a fresh
page-one response, validates one exact detail payload, performs systematic
preparation from that pinned identity, and records the visible number, internal
ID, deadline, fingerprint, detail hash, readiness, and eligibility. It creates
or reuses one schema-v5 evening plan only when preparation is 15/15,
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
exact drawing identity and its independent T−45/T−30/T−20/T−16/T−10 ticks.

The canonical reusable schedule-evidence input is
`data/schedule-evidence/ledger.json` under the validated `project_root`.
`morning-dispatch` consumes it by default and supports a contained explicit
override; passive retries carry the exact resolved path. This input is not the
legacy per-drawing reviewed-schedule catalog and the two schemas are never
interchanged. A ready baseline-only pin set may be monotonically enriched when
new exact ledger evidence becomes available: replacement is one transaction,
permits only baseline-only to reviewed schedule transitions for the same
target event/order, and rebinds the canonical reviewed hash. Any other pin,
identity, schema, hash or ambiguity change remains fail-closed.

Plan, wrapper, and plist bytes are generated once. The dispatcher persists
`scheduled/generated` before activation. A retry after bootstrap failure or a
crash verifies and reuses the exact plan, wrapper, and plist bytes before
invoking activation, then advances only the activation state. A conflicting,
tampered, or partial artifact set fails closed.

Unresolved preparation is a separate passive preflight state machine. It
writes a fingerprint-bound attention marker, append-only attempts, candidate
and provider diagnostics, a strict reviewed-schedule queue when the provider
has no identity-bearing fixture, and an idempotent retry plan at
T−360/T−240/T−180/T−100/T−90. Every retry carries exact expected drawing
identity, stops before T−60, performs no busy sleep, and omits activation.
`preflight-status --open` reads the current DB and these artifacts without
schema initialization or mutation. Attention clears only when the same
fingerprint reaches atomic READY 15/15.

Generation is deliberately separate from activation. Generic morning
artifacts are passive by default and omit `morning-dispatch --activate`;
`morning-preanalysis-plan --activate-evening` is the explicit post-drill
opt-in. A passive recurring job may synchronize, prepare, record diagnostics,
and generate an exact evening plan, but cannot install that plan. Neither a
schema-v5 evening scheduler nor automatic bet path is installed. The passive
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
- The preparation probability hash is the immutable 15-row TotoBrief BK
  matrix. Pool rows are live crowd observations: a newer synchronized pool may
  replace the morning snapshot without changing the canonical identity,
  schedule, or BK pins. Baseline-only pin revalidation therefore compares BK
  and event identity, while the readiness summary atomically advances the
  latest combined BK/pool evidence hash. Final EV/package construction reads
  the pool from the same fresh final TotoBrief payload, never from pin
  provenance. BK drift, equal-time conflicting pool evidence, stale refreshes,
  identity/order/schedule drift, and reviewed-hash drift remain fail-closed.
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
  publication verifies that identity during archive import and enforces T−10
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
-> Scheduler T−10 publication cutoff when the final package remains valid
```

Reviewed alias catalog schema v2 can bind a canonical team to provider team ID,
country, and competition context. Team identity never hardcodes a fixture.
Domestic competition resolution rejects global provider competitions.
Sufficient observed provider coverage may distinguish
`source_missing_competition` from a generic missing candidate, but both remain
unresolved and publish no pin.

Systematic resolver v3 also has small code-owned reviewed identity taxonomies
for reusable exact team aliases and translated domestic competition labels.
Both are keyed by stable country identity and contain no drawing/event/fixture
coordinates. Taxonomy-assisted acceptance retains the existing sport, gender,
country, date-window, uniqueness, and margin checks and additionally requires
same orientation plus strong identity evidence for both teams. Reversed,
ambiguous, cross-country, and out-of-window candidates remain unresolved.

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
  T−30, T−20, T−16, and T−10 with terminal markers (`.bet-ready`, `.no-bet`,
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
  `T−20`, `T−16`, `T−10`). The plan's gross-EV threshold is passed through the exact
  `run-drawing --min-gross-ev` CLI contract. Optional `--env-file` produces a
  wrapper that validates and sources a user-owned regular non-symlink file
  whose mode is no broader than `0600`; the plist contains only the wrapper
  path and no credentials.
- `scheduler-recover-plan`: clone one current immutable scheduler plan into a
  fresh output scope while preserving every target/config/evidence binding.
- `morning-preanalysis-plan`: generate, but never install, a separate launchd
  candidate beneath `reports/rehearsal`. Its wrapper uses the same secure env
  contract and invokes drawing-neutral `morning-dispatch` at configured times.
  A ready invocation creates or reuses one exact per-drawing schema-v5 plan;
  it never uploads a package or places a bet.
- `morning-dispatch`: resolve, validate, pin, prepare, and persist one current
  drawing under a lock, then generate one idempotent evening plan only before
  T−45.
- `scheduler-execute`: run one short-lived resumable tick, capture one immutable
  final detail for a final attempt, strictly verify the bound runner/archive
  evidence, recover safely from restart, and publish `.bet-ready` only before
  T−10.

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

## Test execution tiers

Project pytest configuration excludes `heavy` by default. The release tier
uses small deterministic contract surfaces and hash-bound frozen artifacts.
The three full 4967/4969/4970 selector recomputations, full bank-4,980
four-sensitivity runtime build, and real offline replay remain executable in
the opt-in/nightly `heavy` research tier. Historical drawing-4951 pinning and
stale-schedule and scheduler prepare/final pipeline replays use the same tier.
Marker selection changes test
orchestration only; production safety, objective ordering, provenance and the
candidate universe are identical.

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

## Public result and bound-selection-context boundaries (2026-08-10)

`DrawingRunnerResult` normalizes any legacy/manual `PLAY` package before the
object can cross a public boundary. Actionable coupon/cost/payout fields become
empty `NO BET`; retained diagnostics are explicitly `TRAINING/PAPER`. Direct
runner report writing and transactional aggregate publication repeat this
normalization, so bypassing orchestration cannot create a wager-ready artifact.
The direct EV package writer calls the same sanitizer before rendering: its
coupon CSV is header-only and any retained coupons are confined to an explicit
training/paper Markdown section. Valid `NO BET`/`STRUCTURAL_PASS` artifacts are
not discarded or relabelled.

`bound_selection_context(EVConfig)` is the canonical selector authorization
object. It binds requested bank/stake/capacity, effective budget/capacity,
minimum EV, concentration/probability policy, safety/provenance enablement, and
the complete nested quality-v2 algorithm configuration. Provenance validates
the exact object and canonical hash against current selector inputs and the
referenced SchedulerPlan; the runner manifest and selector diagnostics must
match the same plan context. Any absence or mismatch is fail-closed.
