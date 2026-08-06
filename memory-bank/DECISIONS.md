# Decisions

## Monotonic pin-set upgrade boundary (2026-08-06)

- A canonical ready pin-set is not rebuilt from fresh provider provenance when
  only missing schedule evidence improves. Existing strict rows are reused
  exactly after revalidation.
- Only `totobrief-baseline` rows may transition to strict reviewed schedule
  rows for the same target event/order and canonical target team orientation.
- A reversed reviewed fixture is schedule-only metadata. It must not create an
  external provider identity or swap TotoBrief `1/X/2` probabilities.
- A known baseline kickoff may be enriched only by the same kickoff; a
  different time is a conflict. An unknown `baseline-only` sentinel may gain a
  validated kickoff.
- The supplied reviewed hash must equal the hash embedded in every selected
  reviewed row. Mixed, missing, unrelated or ambiguous evidence is rejected.
- Upgrade publication remains a single transaction; downgrade or any strict
  fixture/team/identity drift preserves the old complete set.

## TotoBrief TLS resilience and early scheduler preflight (2026-08-05)

- The schema-v5 scheduler trigger identity is extended to
  `120/90/60/45/30/20/16/10`. T−120, T−90, and T−60 are diagnostic,
  non-package-producing TotoBrief TLS/API/freshness preflights.
- Early preflights are plan-scoped, persistent, idempotent, and execute at most
  once per stage. A missed older diagnostic is not replayed from a later tick.
  All requests continue through the shared TotoBrief coordinator.
- Early success or cached preparation never authorizes PLAY. The final phase
  still requires a fresh direct TotoBrief detail response; unavailability
  remains coupon-free, zero-cost `NO BET`.
- TotoBrief TLS verification is invariant and cannot be disabled. `verify=False`
  is prohibited.
- Transport failures retain only a redacted original message, structural
  exception-type chain, category (`ssl_verify`, `ssl_handshake`, `dns`,
  `connect`, `timeout`, or `http`), status, endpoint without query data, and
  attempt count. Headers, credentials, query secrets, and bearer values are
  never persisted or logged.
- Scheduler state and stderr JSON logs retain the same safe failure detail for
  every failed stage. Exception causes are preserved where an underlying
  transport or decoding exception exists.

## Deadline parsing and publication timing (2026-07-31)

- CLI identity deadlines are strings at the Click/Typer boundary and are
  parsed by the project as strict timezone-aware ISO-8601. This avoids
  Click's timezone-incompatible datetime parser.
- `Z` and explicit offsets preserve exact-instant semantics and normalize to
  UTC before `MorningExpectedIdentity` comparison. Naive or malformed values
  are rejected; identity mismatch remains terminal.
- `PUBLICATION_LEAD_MINUTES = 10` is the single production publication offset.
  Plans/status use `t_minus_10`, and launchd renders the corresponding
  `Europe/Moscow` wall-clock trigger deterministically.
- This timing contract is scheduler schema v5. Its plan identity includes the
  schema, ten-minute lead, and exact `45/30/20/16/10` trigger offsets;
  generated LaunchAgent labels and status are v5-bound.
- Scheduler schema v4 is permanently the stale T−12 contract. It must fail
  closed with a regenerate-v5 diagnostic and must not be loaded as T−10,
  migrated, reused, or executed.
- This timing correction does not authorize automatic betting, does not alter
  the passive preflight T−60 hard stop, and does not install launchd jobs.

## Passive preflight retry launchd boundary

- A persisted retry plan may generate only a drawing-ID/fingerprint-specific
  LaunchAgent whose wrapper calls `preflight-retry-run`.
- Installed status requires byte equality with the generated candidate;
  loaded status requires `launchctl print` success for the exact label.
- This boundary cannot contain `--activate`, `run-drawing`, betting, package,
  or `.bet-ready` operations.

## Passive nightly reconciliation decisions (2026-07-30)

- Nightly automation is results-only. It cannot import or call package,
  scheduler-activation, upload, or betting code.
- "Last 30" means the last 30 finished drawings first; incomplete/cooldown
  filtering happens only inside that bounded scope.
- Apply is authorized only for the exact allowlist captured by a physical
  read-only dry-run and confirmed unchanged by a second read-only selection.
- All eligibility and cooldown decisions within one run use one reference
  instant captured after the maintenance lock is acquired. Cooldown expiry
  caused only by elapsed wall time cannot alter the captured allowlist.
- The captured candidate tuple is immutable and bound to a deterministic
  drawing/event/result fingerprint. Real local identity or result mutation
  between selection and apply remains fail-closed selection drift.
- The default attempt cap is eight drawings, force is disabled, and persistent
  cooldown/quarantine remains authoritative.
- An empty selection is `DEFERRED/NOOP` with zero network and no backup.
- A valid online SQLite backup with mode `0600`, quick-check, FK check, SHA-256
  and manifest is mandatory before any reconciliation mutation/network apply.
- Retention removes only excess manifest-verified backups and always preserves
  at least the newest known-good copy.
- Morning preparation and nightly reconciliation share one global fcntl lock.
  Stale lock-file metadata alone never permits overlap; the OS lock is
  authoritative.
- `source_incomplete` is `PARTIAL`, not a crash and never evidence for a
  synthetic result/VOID.
- LaunchAgent artifacts are generate-only. Installation requires a separate
  explicit operator decision after review of tests, paths, timezone, and the
  first manual run.
- That operator decision was granted after wave 3. The installed deployment is
  `com.totoai.nightly-reconciliation.v1`, daily 03:20 host-local/Moscow time,
  `RunAtLoad=false`. Installation does not change the generate-only behavior
  of `nightly-reconciliation-plan`.
- Launchd exit code 2 is accepted only when the persisted nightly report is a
  structurally valid `PARTIAL` run. It is not treated as success, but it is
  distinct from `FAILED` and is expected for authoritative 14/15 source data.
- Runtime state, logs, RAW, backups, SQLite, and the installed home plist are
  operational evidence outside Git. Only code, tests and concise audit
  summaries are published.

## Offline canonical-RAW classification decisions (2026-07-30)

- Offline canonical-RAW repair and network reconciliation are separate
  classification domains. Network `source_incomplete` and its
  provider/source-keyed cooldown state are never inferred or updated by an
  offline repair.
- Stable offline states are:
  `offline_repair_recoverable` for a dry-run with provable pending changes,
  `offline_repair_recovered` after those changes are applied, and
  `offline_repair_no_changes` when the canonical RAW adds no analytical
  information.
- Reapplying an already classified local snapshot preserves its classification.
  A reported `logical_changes=0` means a physical and logical no-op, including
  raw-classification metadata, timestamps, attempt counters, archive bytes,
  and SQLite bytes.
- The historical erroneous transition
  `source_incomplete -> offline_repair_recovered` is allowed once only when the
  exact canonical RAW provenance/fingerprint matches its persisted row, its
  content is already incorporated, and an independently hash-verified complete
  result snapshot proves every terminal result omitted by that RAW. Ambiguous
  cases remain unchanged and are reported for manual review.
- A separately persisted and verified VOID result is stronger terminal
  evidence than an older canonical RAW with an empty result. Offline repair
  cannot remove or downgrade that VOID.

## Controlled backfill acceptance decisions (2026-07-30)

- Historical network repair is permitted only through an explicit drawing
  allowlist, an online SQLite backup, a physically read-only dry-run, one
  bounded apply, Data Health comparison, scope proof, integrity checks, and a
  zero-request idempotency pass.
- The successful 4946/4955/4956/4958 batch proves this bounded protocol, not
  unrestricted full-history safety. Waves 2/3 and the idempotency replay
  authorized only the installed latest-30/eight-attempt nightly job; bulk
  unrestricted full-history backfill remains disallowed.
- `source_incomplete` is valid source evidence, not a reason to synthesize a
  result or VOID. Drawing 4946 remains 14/15 and is cooled down.
- Complete reconciliation state prevents repeated network access. A second
  non-force apply must perform zero requests and leave SQLite and RAW
  unchanged.
- Runtime data is local evidence: `data/toto.db`, backups, RAW payloads,
  cooldown state, and rehearsal reports are never committed. Repository
  publication contains code, tests, concise reports, hashes, and
  machine-readable audit summaries only.
- Sports-statistics evidence remains audit-only until a lawful source supplies
  useful coverage and a frozen chronological OOS evaluation proves no
  degradation against the market prior.

## Reconciliation retry-state decisions (2026-07-30)

- Reconciliation eligibility is durable database state keyed by exact
  drawing/provider/source, not an invocation-local JSON log.
- The canonical source fingerprint is the normalized detail payload SHA-256;
  RAW snapshot hashes are not used because capture metadata changes per
  observation.
- Stable source-incomplete data is not a transport failure. It receives a
  6-hour bounded exponential cooldown, capped at 7 days, and an expiring
  30-day quarantine after five unchanged observations.
- Transport failures and HTTP 429/5xx use a separate 5-minute-to-1-hour
  cooldown and never increment source-incomplete stagnation.
- A changed observed fingerprint or improved terminal count resets the
  source-incomplete stagnation sequence. Quarantine expiry permits a bounded
  new observation. `--force` bypasses blocking once without erasing history.
- Source-incomplete payloads are not immediately re-requested inside one CLI
  invocation. Bounded in-process retries remain only for transient failures.
- Dry-run may inspect policy state but must not call the network or write RAW,
  JSON resume state, or reconciliation rows.
- A blocked drawing never consumes a range batch slot; otherwise old
  quarantined rows could starve newer repairable drawings forever.

## Lifecycle evidence decisions (2026-07-30)

- Fifteen event/quote rows do not make a finished drawing fresh. Freshness
  requires 15 terminal outcomes plus a complete result snapshot linked to an
  immutable RAW snapshot.
- RAW archive publication precedes every lifecycle SQL import. The canonical
  overwriteable cache is operational convenience, not historical evidence.
- Full-detail imports are monotonic and non-destructive. Empty/null/zero
  payload fields do not downgrade known values; terminal-result conflicts stop
  the import.
- `0/0/0` remains invalid pool evidence.
- VOID/cancelled is terminal only with explicit source status and evidence.
  Empty result/score fields never imply VOID.
- Network failures are `exhausted/transport_error`, never `source_missing`.
  `source_missing` is used only when absence is proved by local/source
  evidence.
- Historical repair never synthesizes fields. Validated canonical RAW can
  prove `offline_repair_recoverable`; applied recovery is persistently
  `offline_repair_recovered`; absent RAW remains `no_local_evidence`.
- Nightly reconciliation is a non-betting command contract only. Its installed
  LaunchAgent may refresh finished-result evidence but cannot call package,
  upload, evening scheduler activation, or betting paths.

## 2026-07-29: Row counts are not evidence of historical completeness

- A database is never described as current, complete, or validated from
  drawing/event counts alone. Claims must name the audited scope, required
  fields, evidence source, and timestamp.
- The complete local history is untrusted by default. Each analytical use
  declares a versioned data-health contract and admits only drawings that pass
  that contract with machine-readable reasons.
- A finished drawing requires terminal `1/X/2` outcomes or explicit reviewed
  `VOID`; null results are not silently interpreted or synthesized.
- Non-null `0/0/0` pool triples are unusable data, not complete probabilities.
- RAW detail must be archived immutably with identity, capture time, and hash
  before operational-table mutation. Absence of RAW is explicit provenance
  debt and cannot be hidden by a populated SQLite row.
- Backfill preserves source truth. Data recoverable from local RAW is repaired
  separately from data requiring a future TotoBrief request; permanently
  unavailable evidence remains unknown and is excluded from affected studies.
- A package is not evidence of strategy performance until it has immutable
  pre-draw provenance, authoritative final results, settlement, and a
  post-draw report. Rehearsal/simulation packages are excluded.
- `TOTO-DATA-HEALTH-CONTRACT-V1` is the next implementation boundary. New
  optimizer development remains paused until the P0 ingestion, archive, and
  health gates are in place.

## 2026-07-29: Reviewed schedules are source evidence, never synthetic fixtures

- Reviewed schedule fallback is admitted only after complete successful
  API-Sports required-date coverage proves `source_missing_competition`.
  Ambiguity, quota/date/transport failure, or a competing candidate cannot be
  masked by reviewed evidence.
- Production-reviewed evidence requires one official and one independent
  agreeing source with immutable snapshots, exact target binding, scheduled
  status, and bounded freshness.
- A reviewed pin has `source_provider=reviewed-schedule`, no source fixture or
  provider team IDs, a reviewed evidence ID/hash, and schedule-only capability.
- Mixed authoritative pins use an additive canonical pin-set table rather than
  mutating legacy API-Sports identities. Exactly 15 pins publish atomically or
  none do. Existing API-Sports-only loaders remain compatible.
- Final readiness is recomputed from 15 per-pin source revalidations. Reviewed
  pins never reach an odds endpoint and use explicit TotoBrief BK fallback
  only after schedule identity passes.
- Catalog and snapshot mutation through publication is a TOCTOU failure and
  yields `NO BET`.
- The catalog CLI input is explicit opt-in. Passive morning behavior and the
  prohibition on automated bet placement are unchanged.

## 2026-07-29: Generic morning automation is passive by default

- Installing a recurring morning collector/preparer is separate from
  authorizing automatic installation of an evening package scheduler.
- `morning-preanalysis-plan` omits `--activate` by default. The explicit
  `--activate-evening` flag is allowed only after a live activation-disabled
  15/15 drill passes.
- Passive morning automation may synchronize data, persist readiness evidence,
  and generate an exact plan. It cannot load that plan into launchd, create a
  package, or place a bet.

## 2026-07-29: Contextual identities do not authorize cross-competition fixtures

- Reviewed provider team IDs are stable team identity evidence, not fixture
  identity and never a reason to hardcode a fixture ID.
- Reviewed identities may be scoped by country and competition context.
- A domestic target cannot consume a provider fixture classified under a
  global competition; this closes the friendly-match bypass.
- `source_missing_competition` is diagnostic non-match evidence. It is emitted
  only for a derived, confirmed domestic country with an explicit numbered
  competition level, successful same-country provider schedule evidence, and
  no compatible competition. It never creates a pin or makes a drawing ready.

## 2026-07-29: atomic-final clocks and publication reserve are completion gates

- Any decision made after network preparation uses a newly sampled UTC clock.
  Morning plan generation is forbidden at or after T−45 based on that
  post-preparation sample; phase-start time is not valid completion evidence.
- `FinalInputSnapshot.captured_at` is the detail-response acquisition time,
  sampled immediately after `drawing_info()` returns. Request-start time is
  not snapshot freshness provenance.
- `publication_reserve_seconds` defines the actionable calculation cutoff, not
  a second publication deadline. Final calculation, each recomputed subprocess
  timeout, and every retry admission must stop no later than
  `T−10 − publication_reserve_seconds`.
- The interval after the actionable cutoff through hard T−10 is reserved only
  for package writing, archive-manifest writing, durable archive, recovery,
  status, and `.bet-ready` marker work. Those steps use
  `plan.publish_deadline`/`plan.freeze_at`, not the actionable cutoff.
- A recoverable archive without a marker may complete publication during that
  reserve, including exactly at hard T−10. After hard T−10 it becomes terminal
  zero-cost `NO BET`; stale `package.csv` and `package-archive.json` are
  removed so they cannot be mistaken for uploadable coupons. Immutable
  final-input and durable audit evidence may remain.
- Simulation-only legacy long-running execution retains its historical T−10
  fixture semantics; production schema-v5 ticks enforce the reserve boundary.

## 2026-07-28: scheduler failures and morning artifacts are typed evidence

- Retry/permanent classification must use exception type, structured HTTP
  status, or an explicit category. Error-message substring matching is
  forbidden.
- HTTP 503, transport timeouts, and explicitly transient configuration-service
  failures remain retryable. Unknown failures are retryable within the bounded
  attempt budget. Typed integrity/identity/hash failures are terminal.
- Morning plan/wrapper/plist bytes are immutable evidence. A dispatcher writes
  `scheduled/generated` state before activation and retries activation by
  verifying and reusing the exact existing artifact set.
- `bet_ready` and `publish=complete` are durable facts only after the
  exclusive `.bet-ready` marker succeeds. Marker failure is package-free,
  terminal `failed`; a later tick must not retry or report publication.
- Archive recovery must compare the saved atomic-final timing-override hash
  with the current semantic override hash and fail closed on any change.
- Morning state is keyed by drawing ID and deadline, not by the date of a
  dispatcher invocation. One drawing spanning two allowed Moscow dates owns
  one plan.
- Production schema-v5 execution is tick-only. `--run-id` is simulation-only;
  the incompatible legacy long-running production mode is rejected.
- Legacy schema-v3 plans preserve their declared `project_root`.
- Generated `reports/` are ignored as one directory; no report is an
  intentional tracked source artifact.

## 2026-07-28: gender is a hard event-identity boundary

- A TotoBrief women target (`(ж)`, Women/female context) may resolve only to a
  provider candidate with explicit W/Women/female evidence.
- Reserve, academy, youth, and U17-U23 candidates cannot satisfy a senior
  women target even when a women marker is present.
- A non-women target cannot resolve to an explicitly women provider event.
- Missing women coverage remains unresolved; it must never be bridged to a
  male team, reserve, or youth fixture by fuzzy similarity or a manual alias.

## Atomic final input temporal invariant (2026-07-28)

- Pool/BK changes before a final capture are expected and do not invalidate
  earlier diagnostic preparation.
- One production final attempt owns one immutable exact drawing-detail
  snapshot. Its canonical payload, normalized final BK probabilities, capture
  time, target fingerprint, plan, and attempt provenance are independently
  hash-bound.
- A computed or uncomputed `NO BET` is always coupon-free, zero-cost, and has
  an empty derived brief. Empty per-event placeholder strings are not a valid
  zero package.
- The hard manual-publication cutoff is T−10. The configured production phase
  times are T−45, T−30, T−20, T−16, and T−10.
- Scheduler state is persistent evidence, while the process lock is only a
  concurrency primitive. A recovered `running` attempt is marked abandoned
  and a retry receives a new immutable attempt directory.
- Warmup and refresh never authorize a package. Only a verified final snapshot
  may flow through immediate publication, and publication/archive recovery
  validates that snapshot without consulting the mutable live API.

## Dynamic morning identity and deployment gate (2026-07-28)

- A recurring cross-day morning job must never embed a drawing number. The
  morning dispatcher resolves one fresh current drawing per invocation and
  persists the exact identity before generating a per-drawing evening plan.
- Drawing identity belongs to the immutable per-drawing plan, not to the
  recurring dispatcher.
- Multiple morning triggers are idempotent and serialized. Deferred readiness
  may retry; ambiguous/no drawing, identity conflicts, ineligible timing spans,
  and dispatch after T−45 do not create a partial evening schedule.
- Scheduler artifact generation never implies installation. The generic
  dispatcher and schema-v5 evening scheduler require an activation-disabled
  live drill before manual installation.
- The five known obsolete LaunchAgents were explicitly removed. Cleanup must
  remain label-specific; wildcard deletion of unknown `com.totoai.*` jobs is
  forbidden.

## 2026-07-27: sports statistics start as immutable audit evidence

- Sports statistics are a separate provider-neutral evidence boundary.
- The first implementation is football-only and cannot affect probabilities,
  package selection, scheduler decisions, PLAY/NO BET, or betting markers.
- Every fixture is filtered locally with
  `fixture_start < min(snapshot_as_of, target_start)`; target and non-finished
  fixtures are always excluded.
- Missing and provider-plan-denied data remain explicit missingness with
  market-only fallback. They are never converted to numeric zeros.
- Feature hashes exclude run observation timestamps but include source
  provenance, so identical immutable cache evidence reproduces the same feature
  identity.
- Activation requires a predeclared chronological out-of-sample comparison
  against bookmaker probabilities after at least 30 drawings / 450 events and
  sufficient non-fallback feature coverage.
- The tested API-Sports free plan does not provide current-season history or
  standings, so it is not accepted as the sole sports-data source.

## 2026-07-27: Active preparation has a distinct short detail-cache boundary

- The general raw TotoBrief detail cache may remain useful for collection and
  recovery, but its 12-hour lifetime is not valid operational probability
  evidence for an active drawing.
- `sync-prepare` and `prepare-drawing` accept an exact cached detail only when
  it is at most 60 seconds old. Older cache content triggers one coordinated
  exact-detail refresh; refresh failure defers preparation instead of falling
  back to stale probabilities.
- The short cache boundary prevents a known stale-cache mismatch, but it does
  not pin probabilities forever. A genuine probability change after
  preparation remains a fail-closed runner rejection.
- This decision does not weaken drawing identity, probability hash,
  monotonic-timestamp, equal-time conflict, or unrelated readiness-evidence
  checks.

## 2026-07-27: Cancelled events require reviewed evidence and settle as VOID

- TotoBrief empty result/score fields are insufficient to infer cancellation.
  A current snapshot may mark an event VOID only from explicit 1-based event
  numbers plus a syntactically valid HTTP(S) evidence URL.
- A VOID override must agree with the raw payload: both result and score must
  be empty. An existing result or score is a contradiction and fails closed.
- Snapshot schema v3 stores the VOID marker `*`, status, empty score, and
  evidence URL in the immutable hash. Schema v1 and v2 snapshots retain their
  original event shape and hash rules.
- Under BaltBet VOID semantics, every 1/X/2 selection is correct at that
  position. VOID positions are not prediction misses and therefore do not
  appear in fixed-miss or zero-exposure-miss diagnostics.
- Non-VOID settlement hash payloads do not gain an empty VOID field; historical
  settlement identities remain compatible.

## 2026-07-27: Ready pins and probability evidence have separate lifecycles

- A matching drawing fingerprint and successfully revalidated provider
  identity allow the exact existing 15 pins to be reused.
- Reusing pins does not authorize reusing probability evidence. Preparation
  must hash the exact newly loaded normalized 15-by-3 TotoBrief BK input and
  atomically patch only its probability hash, target fetch timestamp, and row
  update time; all unrelated readiness evidence is immutable during refresh.
- Probability evidence is monotonic and compare-and-swap protected. Older
  target fetch times cannot replace newer evidence. Equal time and hash is an
  idempotent no-op; equal time with a different hash is a closed conflict.
- The refresh transaction first verifies ready/playable 15/15 preparation and
  every authoritative pin. Invalid probability input or invalid pin state
  fails closed without partially changing preparation evidence or pins.

## 2026-07-23: Finished result and settlement identity

- Result snapshot identity excludes retrieval time and includes exact drawing
  identity, ordered result/score rows, payments, pool, and jackpot.
- Package identity uses canonical ordered coupons, drawing identity, and stake;
  original source bytes and their SHA-256 are retained.
- Settlement identity binds result snapshot and package archive hashes.
- Category entitlement is derived only from explicit supported official
  category/payout evidence. Without it, return and ROI remain null even when
  observed hits are below a historically familiar threshold; pool and jackpot
  totals are never treated as payouts.
- Post-draw scheduling uses one explicit target and an absolute instant after
  `ended_at`; it never resolves an open drawing or places a bet.

## 2026-07-23: Production PLAY requires explicit package-safety evidence

- Keep Cover Engine generation and guarantee mathematics unchanged.
- Apply the safety gate only at the production-playable publication boundary;
  research selection remains backward compatible.
- Reuse audit exposure definitions. Reject near-fixed concentration, a fixed
  outcome below the configured probability floor, or zero package exposure to
  an outcome at or above the configured material-probability floor.
- A valid unsafe package is `NO BET` with no uploadable coupons. Missing,
  malformed, stale, or mismatched readiness/safety evidence is operational
  `FAILED`, never an implicit `NO BET` or `PLAY`.
- A schema-v4 `PLAY` manifest must serialize coupons, normalized probability
  rows, and canonical safety thresholds. Scheduler ingestion reconstructs
  `PackageSafetyConfig`, recomputes `evaluate_package_safety`, and requires the
  complete declared result to equal that recomputation. It never trusts a
  manifest-declared safety decision. Legacy-incomplete or tampered evidence
  fails closed.
- Safety evidence always retains the original evaluated coupons and package
  SHA-256 separately from `uploadable_coupons`. A rejected package therefore
  remains auditable, while only the publication package is emptied. Every
  non-null safety record is recomputed before scheduler PLAY or NO BET returns.
- A terminal `NO BET` does not imply that package safety failed. Recomputed
  safety evidence may be either `NO BET` or `PLAY`; timing, self-dilution, or
  another audited boundary may be the rejecting gate. Preserve that gate in
  `terminal_reason`, while always publishing zero coupons for `NO BET`.
- Safety thresholds are authorization inputs owned by the scheduler plan, not
  evidence supplied by the runner manifest. Canonically validate and serialize
  them in the plan, forward them to `run-drawing`, require manifest equality,
  and recompute with the plan's `PackageSafetyConfig`.
- Actionable schema-v3 plans require a resolved internal drawing ID.
  Systematic preparation/preflight persists or verifies its exact visible
  number and `ended_at`; pre-bet manifest import verifies the same database
  identity. Durable archival is necessary but not sufficient for publication:
  clock checks immediately after import and immediately before `.bet-ready`
  fail closed after T-10 without deleting the audit archive.
- This decision does not implement finished-result sync, settlement, payout
  accounting, observed ROI, or post-draw scheduling.

## Package audit report verification is fail-closed

- Schema-v1 keeps readable top-level audit fields duplicated alongside the
  canonical `audit_hash_payload`.
- Recomputing from a complete report requires canonical equality for every
  duplicated hash-bound field and requires its stored `audit_sha256` to match.
  Missing or mismatched fields raise `ValueError`; the embedded payload is
  never trusted in isolation when a complete report is supplied.
- Direct recomputation from a standalone canonical payload remains supported.

- Use repository memory instead of relying on chat memory.
- This memory bank is project-local to TotoAI and must never be mixed with
  local skills, personal knowledge bases, team knowledge bases, or unrelated
  external memory stores.
- Project knowledge is stored in repository directories:
  - `memory-bank/` for project state and durable decisions.
  - `knowledge/` for domain notes grounded in implemented repository state.
  - `skills/` for project-local workflow checklists.
  - `prompts/` for reusable project prompt templates.
- After every completed feature, update the project knowledge base first.
- One task, one commit, one verification cycle.
- Every hypothesis must be backtested.
- Never claim guaranteed profit.
- Every eligible drawing will eventually expose three separate package
  strategies under the same dynamic bank: `cover`, `ev`, and `hybrid`.
  Strategy labels are semantic contracts, not presentation aliases.
- `cover` requires an explicit brief, target category, compact package, and
  exact verifier evidence. Its category guarantee remains conditional on the
  actual 15 outcomes being inside the brief.
- `ev` retains exact modeled monetary-EV ranking but receives the same
  concentration and Hamming audit. A union of outcomes observed in an EV
  package is a derived brief and never a Cover guarantee.
- `hybrid` must combine calibrated final probabilities, modeled category-hit
  probability, Cover/Hamming evidence, modeled EV, and frozen
  diversity/concentration constraints. Its objective and constraints require
  chronological development plus untouched/prospective GO/STOP evaluation.
- The operator bank is any positive integer multiple of the configured stake;
  4980 RUB is an operational example only and must not be hard-coded.
- Common package audit schema v1 hashes the exact ordered canonical coupon
  list and separately hashes all audit metadata. Coupons are 15 uppercase
  `1/X/2` outcomes, non-empty, and unique; malformed or duplicate packages
  fail closed.
- Audit report identity includes the full audit SHA-256. Exact existing bundles
  must match regenerated JSON/CSV/Markdown byte-for-byte with no missing or
  extra files, and JSON stores the canonical hash payload for independent
  recomputation.
- Union-brief category coverage is computed by an independent exact streaming
  verifier distance implementation. The derived guaranteed category is
  `15 - worst_minimum_distance`; coverage shares are reported for categories
  15 through 9. For EV/Hybrid this is descriptive conditional coverage of the
  union brief and is not a declared Cover guarantee.
- Fixed/near-fixed and fixed-low-probability findings are auditable warnings.
  The audit never changes coupons. Optional probability-weighted category
  values are explicitly conditional on the union brief.
- Market probabilities remain the probability prior and mandatory fallback.
  Sports-statistical evidence may influence package generation only through a
  provider-neutral, time-valid, leakage-free, calibrated blend that passes
  frozen coverage and no-degradation gates. Morning caching must prevent a
  last-minute sports-provider call from being required for safe completion.
- Every generated morning, fallback, final, recommended, and manually recorded
  package must eventually be archived before results and settled after an
  authoritative 15-outcome refresh. Hit/category/cost settlement is mandatory;
  payout/profit/ROI remain unavailable rather than fabricated when lawful
  actual payout data is absent.
- Prospective package, result, and settlement evidence is append-only and
  content/provenance bound. Corrections append a new snapshot/settlement and do
  not overwrite prior evidence.
- The evening scheduler continues to publish for manual upload only. A
  separate post-draw scheduler may refresh and settle evidence but can never
  submit a bet or create `.bet-ready`.
- Evening production scheduler plans carry an absolute project root. Generated
  wrappers, launchd `WorkingDirectory`, and subprocess `cwd` all enforce that
  root. Preflight deliberately reuses the warmed project raw/provider caches;
  fallback and final package phases deliberately retain isolated run caches.
  Legacy scheduler schema v1 is load-compatible only through strict absolute
  common-root inference and validation of its original plan ID. Filesystem root
  is never a valid project root; root/path symlink ambiguity is rejected, and
  scheduler database, aliases, and output paths must resolve inside that root.
- Separate prediction quality from cover quality.
- The completed BK-only experiments used `13+` hit rate as their fixed primary
  objective. The next optimizer changes the primary objective to modeled
  monetary expected value under a dynamic user bank.
- The bank may be any positive amount exactly divisible by the configurable
  coupon stake. The optimizer does not force full-bank utilization.
- The Expected-Value Package Engine evaluates all `3^15` coupons. Performance
  optimization may not truncate its candidate space or alter exact rankings
  beyond a documented floating-point tolerance.
- EV research and playable recommendations are separate modes. Research always
  shows top coupons; playable mode uses an explicit threshold and returns
  `NO BET` when no coupon qualifies. It never lowers the threshold merely to
  force a package.
- Initial crowd joint probabilities use an explicitly disclosed independence
  model derived from pool marginals. This is an assumption requiring stress
  tests, not an observed property of player tickets.
- Historical modeled ROI is not observed ROI because category payouts and
  winner counts are not present in the current data. Profitability claims
  require prospective validation with lawful payout data.
- Direct Pinnacle access and prohibited scraping are out of scope. External
  odds use a provider-neutral, event-level interface with TotoBrief BK fallback
  so missing external matches do not silently drop a drawing.
- External odds collection starts on API-Sports' free football and hockey plans.
  A paid plan up to 30 USD/month is a last resort after a prospective audit
  proves request quota, rather than provider coverage, is the limiting factor.
- API-Sports event matching is deterministic and fail-closed. Exact matching
  remains first and may use primary TotoBrief names, optional `name_en`
  alternatives, and reviewed versioned aliases. When both English names are
  absent and both target names are Cyrillic, matcher v4 may consume one
  high-confidence transliterated same-or-reversed pair: pair score >= 0.74,
  both team scores >= 0.55, and margin over the runner-up >= 0.15. Existing
  sport and known-time restrictions still apply. Generic fuzzy suggestions
  remain diagnostic-only; low-margin, low-score, and ambiguous matches always
  fall back. Alias files remain deterministic and reject normalized-key or
  canonical-value collisions and cycles.
- External odds must be complete full-time football or regulation-time hockey
  `1/X/2` markets. Two-outcome hockey moneylines must never be mapped to Toto
  three-way outcomes. Exact `Home`/`Draw`/`Away` outcome-label validation is
  applied only after a market name matches the existing semantic allow-list;
  unrelated markets remain ineligible diagnostics and do not abort the event.
- Initial external consensus requires three eligible bookmakers, applies
  multiplicative de-vig per bookmaker, then normalizes component-wise median
  probabilities. The initial maximum odds age is 36 hours and remains visible
  in provenance and coverage reports.
- External probabilities cannot affect `PLAY` during the coverage audit. Every
  one of the 15 events records either an eligible external consensus or an
  explicit TotoBrief BK fallback reason.
- External odds collection snapshots are append-only and immutable. The
  deterministic collection identity includes the canonical drawing target,
  the fresh TotoBrief target `target_fetched_at`, the external observation
  `fetched_at`, provider matching decisions and market payload provenance,
  request/cache counters, observed quota state, and consensus configuration.
  Saving the same canonical collection is idempotent; operationally distinct
  retry passes receive distinct identities, and conflicting content under the
  same identity is rejected.
- External odds consensus age and future-update checks use the explicit
  external observation time, not the earlier TotoBrief target fetch time. The
  observation time must be at least as late as every consumed provider market
  fetch timestamp.
- API-Sports schedule endpoints use one unpaged request per date and must report
  `paging.current = paging.total = 1`; the live fixtures endpoint rejects a
  `page` parameter. Odds pagination remains explicit and fail-closed. Exact
  duplicate provider records may be deduplicated, while conflicting duplicate
  identifiers remain an error.
- Official API-Sports response envelopes do not provide a top-level observation
  timestamp. The client records its UTC receipt time in cache schema v2 and
  reuses that exact time on cache hits without mutating the raw provider payload.
- TotoBrief may return `start_at = null` for every event in an open drawing. A
  missing target time searches the approved progressively expanded schedule;
  a known target time still requires the existing three-hour UTC window. The
  accepted exact or constrained matcher-v4 pair may have the same or reversed
  home/away orientation. Reversed consensus swaps `1` and `2` into TotoBrief
  orientation while raw provider quotes stay in provider orientation.
  Orientation is persisted and reported; multiple or low-confidence candidates
  fail closed.
- `quota_reserve` protects the API-Sports daily request allowance. The minute
  counter blocks only at zero. Cached historical quota headers are provenance,
  not current operational quota, and must not block a fresh client request.
- API-Sports request accounting reports actual HTTP attempts, including retry
  attempts and additional pages. Cache hits and logical fetch calls are tracked
  separately and must not be reported as requests.
- Safe-runner T-5 enforcement is propagated through prospective collection to
  every schedule date/page, event-market request/page, and API-Sports transport
  retry. Closure completes the immutable pass with explicit safety-stop
  fallbacks and permits no later provider call.
- Prospective API-Sports collection is fresh by default. Each CLI invocation
  uses a unique cache-session directory, pins one TotoBrief target before any
  provider pass, and creates a new provider client per pass while reusing that
  invocation's cache. The defaults are three passes and 65 seconds between
  retries. Only quota reserve, provider schedule failure, and provider odds
  failure are retryable. Shared-cache behavior requires explicit
  `--reuse-cache`; stale cache must never masquerade as a new observation.
- Safe-runner preflight computes all possible coverage, EV, and runner paths
  after target pinning and before waiting. Lexical and symlink collisions with
  the database, aliases, cache root, or sibling outputs fail before provider
  construction; report/cache writability is probed and the guard repeats at
  publication.
- Safe-runner publication is the final deadline-aware phase. Actionable child
  and runner artifacts are covered by one transaction until commit; every
  pre-commit `BaseException` restores/removes all artifacts, and an already
  committed publication is command success. Runner `NO BET` never links an EV
  child report or coupon strings.
- The second fresh EV payload is compared with the expected `PinnedDrawing`
  before timing or EV computation. Expected target mutation is a valid
  zero-cost target-mismatch `NO BET` with `ev_run=None`; structurally corrupt
  results remain command failures.
- Rare holiday and off-season drawings may span up to five days. Missing-start
  external collection will use progressive two-to-five-day schedule expansion
  rather than querying five days for every normal drawing. A playable drawing
  must have effective start times for all 15 events and an inclusive
  Europe/Moscow calendar span of at most two days. `multi_day` and `unknown`
  eligibility are fail-closed `NO BET`; provider timing metadata may veto PLAY
  but external probabilities remain audit-only.
- Playable EV output requires an exact stored eligibility match for the same
  fresh target fingerprint and status `playable`. `multi_day`, `unknown`,
  `absent`, and `not_checked` all suppress package and sensitivity output to a
  zero-cost `NO BET`. Exact diagnostic coupons are not published after this
  veto. Research preserves EV computation and ranking while reporting timing
  provenance or a conservative timing warning.
- Provider provenance is stored explicitly, not only committed through an
  opaque event hash. Matched dispositions retain schedule-event fetch time and
  payload hash plus candidate IDs and match reason; quotes retain market fetch
  time and payload hash. Collection identity binds all of these fields.
- Quote records are ordered canonically before collection identity, storage
  comparison, insertion, and load. Provider response order is not data and
  cannot create a different immutable collection.
- The unique quote key remains `(collection_id, event_order, bookmaker_id,
  market_name)`. Multiple assessments with the same exact key remain rejected
  by consensus and are coalesced into one ineligible anomaly row. That row
  stores every source market in canonical provenance and uses a deterministic
  aggregate payload hash, so duplicates neither disappear nor abort the
  15-event transaction.
- Prospective external collection must never silently drop events. Unknown
  sports, missing or ambiguous matches, provider failures, quota exhaustion,
  stale or partial markets, and minimum-bookmaker consensus failures all retain
  the TotoBrief BK triplet with an explicit fallback reason in the event
  disposition.
- Direct package optimization is evaluated before further brief-first
  heuristics. A brief may be derived from a package but does not constrain the
  v1 optimizer.
- Direct Package Optimizer v1 uses only pre-drawing BK probabilities. External
  providers and payout optimization follow only after a fixed baseline test.
- Direct strategy experiments require a manifest frozen before evaluation. The
  manifest records exact drawing IDs, protocol/data hashes, and a clean Git code
  version; evaluation rejects protocol, data, or code-version mismatch.
- A frozen strategy manifest may be reused for bank sensitivity only. Other
  strategy/protocol settings must remain unchanged.
- Historical result data is included in the experiment data hash but is not
  available to package generation.
- The first frozen 500-drawing retrospective experiment found no statistically
  proven strategy winner. Weighted coverage must not be called superior based
  on its higher average best-hit count alone.
- Do not tune against the 150-drawing frozen holdout. Diagnose and select
  changes on development data, then use a newly frozen prospective or otherwise
  untouched evaluation window.
- The Hybrid Direct Package experiment tests only top-core fractions 0.50,
  0.75, and 0.90 at the frozen 5000 RUB / 30 RUB / category 13 protocol.
- Hybrid GO requires at least two additional development 13+ hits over
  top-probability, no worse 13+ results in at least four of five chronological
  folds, no lower average best hits, and zero operational failures. Otherwise
  the optimizer direction stops and the project moves to external data and
  payout/ROI modeling.
- Hybrid evaluation requires a development-only seal derived from the frozen
  manifest, the development prefix of the frozen backtest CSV, and a read-only
  database. Separate SHA-256 hashes bind canonical CSV rows, pre-drawing
  development inputs, development results, and the fixed hybrid protocol.
- Hybrid pre-drawing input seals include drawing number, ordered event IDs and
  event order, and pool/BK values without results. Evaluation verifies CSV,
  protocol, and input seals before loading any result; it accumulates the
  result seal only after each drawing's top package hash passes.
- Hybrid seals require a clean Git code version, reject collisions between
  source/database/output paths, and publish the development CSV and manifest as
  a rollback-safe pair.
- Hybrid evaluation resolves its deterministic report paths before opening the
  database and rejects any collision with the sealed manifest, development CSV,
  or database.
- The hybrid per-drawing deadline covers every package-generation stage.
  Timed-out selectors do not perform exact coverage after expiry, and any stage
  overrun fails the evaluation before reports are written.
- The sealed hybrid development experiment returned STOP: core fractions 0.50,
  0.75, and 0.90 added -2, -1, and 0 observed 13+ hits respectively versus
  top-probability, despite improving average best hits and having zero
  operational failures. The sealed rerun exactly reproduced the initial
  metrics, used zero holdout IDs, and is the final decision for this direction.
- Further tuning of the BK-only direct package optimizer is closed. The next
  research direction is the Expected-Value Package Engine plus a
  provider-neutral external-probability interface. Any later optimizer work
  needs a new hypothesis and a new untouched evaluation window.
- Budget-constrained oracle commands may use actual results only as benchmark
  upper bounds; they must not be treated as playable prediction methods.
- Budget-oracle must not reduce the candidate search space by default. Candidate
  limits only apply when explicitly requested.
- Budget-oracle drawing timeouts keep the best candidate found so far and should
  not fail the whole run.
- Budget-oracle workload profiling is observational only. It must not change
  oracle candidate generation, candidate order, scoring, or default search
  space.
- Budget-oracle pruning must be mathematically safe and match exhaustive
  evaluation in regression tests.
- Budget-oracle incumbent pruning may skip a candidate only when its maximum
  possible hit count is strictly below the incumbent's actual hit count.
- Dominance pruning is disabled until equivalence with exhaustive evaluation is
  proven. Its previous subset rule changed oracle hit metrics.
- A full-cover coupon-cost lower bound must not prune Budget Oracle candidates:
  the oracle objective evaluates useful partial packages under budget.
- Category 13 means maximum Hamming distance 2.
- Category 14 means maximum Hamming distance 1.
- Category 15 means exact match.
- Cover guarantee only applies if actual outcomes are inside the selected brief.
- Cover Engine performance optimizations must preserve selected coupons,
  coverage rate, worst minimum distance, and guarantee results.
- Cover Engine caches may depend on brief structure and category, but must not
  change candidate order or greedy tie-break semantics.
- Strategy package diagnostics use sorted coupon log probabilities and exact
  pairwise Hamming distances for deterministic structural metrics. Package
  overlap uses set intersection/union; mean unique-coupon log probability is
  unavailable when its unique set is empty.
- User bank can be any positive amount exactly divisible by the configured
  stake.
- `--open` means next playable drawing with `ended_at` in the future.
- `--live` means betting is closed and drawing is ongoing.
- `--latest-finished` is for historical analysis.
- Internal drawing ID differs from visible drawing number.
- Normal TotoBrief requests use one cross-process project-local coordinator:
  two-second default spacing, server-authoritative `Retry-After` (persisted even
  after a final exhausted 429), and bounded retry/backoff for 429, temporary
  5xx, timeout, connection, chunked-transfer, and content-decoding failures.
  Local backoff is capped after jitter; a larger valid server directive is not
  shortened. Request diagnostics contain endpoint paths/status/timing only and
  never query strings or secrets.
- Drawing page metadata/status is an independently committed synchronization
  stage. Current-detail failure must not retain stale statuses for other
  drawings from the successfully fetched page.
- Operational drawing detail may come from the network or an exact
  schema/hash/identity-validated raw cache with a mandatory sidecar commit
  marker. Exactly 15 contiguous events and structurally complete pool/BK
  quotes are required before cache or DB persistence. The default 12-hour
  freshness window supports morning preparation for a same-day final run and
  remains configurable. Wrong, partial, torn, sidecar-free, stale, or
  future-dated cache fails closed. Sidecar-free fixtures are non-operational
  and restricted to explicit offline replay. Explicit operational target-cache
  input must also match an already synchronized playable SQLite drawing.
- `sync-prepare --open` is the minimum-call morning path. Subsequent
  `prepare-drawing` is local/cache-first and performs remote TotoBrief detail
  work only on explicit `--refresh-totobrief`; duplicate immediate detail
  fetches are not part of the normal workflow.
- Open selection for `sync-prepare --open` is made only from its freshly
  fetched page one. A stale SQLite open row absent from page one is never used.
  `--sync-only` performs strict synchronization diagnostics without API-Sports
  preparation or pin writes.
- Scheduled preparation additionally pins the expected visible drawing number.
  `--expected-drawing-number` is checked immediately after fresh page-one open
  selection and before detail fetch, API-Sports work, or pin writes. A mismatch
  is a fail-closed scheduling error rather than permission to reuse SQLite.
- TotoBrief `start_at = null` is never replaced with a fabricated timestamp.
  The existing bounded provider-date expansion supplies preparation evidence.
- Multi-day timing acceptance is deterministic and must forbid real network
  calls and sleeps. A lawful live dry run is optional operational evidence, not
  a prerequisite for accepting the collection-to-eligibility-to-veto boundary.
- The production `run-drawing --open` workflow preflights and pins one exact
  target, waits until T-20, revalidates that same target, then runs fresh
  collection, exact stored timing, diagnostic coverage audit, existing EV, and
  rollback-safe linked reports. It never submits a bet. T-5 forbids new work
  and suppresses any package that completes at or after the cutoff.
- The scheduler and runner share one explicit gross-EV threshold contract:
  scheduler-generated package commands pass `--min-gross-ev`, and
  `run-drawing` validates and uses that value through the existing decision
  configuration. The default remains `1.0`.
- Scheduler credentials are referenced only by secure env-file path. Generated
  wrappers set `umask 077`, validate ownership/type/mode both at generation and
  runtime, require non-empty `API_SPORTS_KEY`, and never print its value. A
  LaunchAgent plist contains only the wrapper path. Generated artifacts are
  candidates only; this feature does not install or load launchd.
- Morning preanalysis is operationally separate from evening package
  scheduling. Its generated wrapper performs guarded synchronization and
  preparation only, uses bounded retries and isolated rehearsal logs, and is
  forbidden from creating scheduler/betting markers.
- Historical/current operational replay is an explicit `run-drawing
  --offline-replay` mode, not an environment switch and not scheduler input.
  It requires exact target/schedule cache envelopes and an aware injected
  as-of time, validates payload hashes and drawing/provider/event identity,
  and never falls back to network clients or process credentials.
- Offline replay is permanently research-only even if diagnostic EV is
  computed. It writes only runner JSON/Markdown with additive manifest-v4
  `replay` provenance (`actionable=false`, as-of, provider, cache paths and
  hashes). Scheduler parsing rejects non-null replay provenance, so a replay
  cannot authorize PLAY or publish a production package. Full scheduler
  execution classifies it as non-production `ignored`, writes status only, and
  creates no terminal marker; malformed production manifests still create
  `.failed`.
- Replay mutable state requires an explicit isolation capability:
  `--replay-root`. SQLite, reports, provider cache, and temporary files derive
  below it. Live defaults are resolved only after the replay branch. Output
  overrides must remain strictly contained; repository/live-root overlap and
  symlink traversal are rejected before any directory or database is created.
- Equal external observation timestamps do not define collection chronology.
  SQLite latest-snapshot reads use append order as the deterministic tie-break
  before collection-ID order, preserving a later progressive pass without
  changing immutable collection identities or timing definitions.
- Runner manifest schema v2 makes every terminal artifact carry a structured
  `ev` object and package summary. Schema v1 used `ev: null` when package
  computation did not run and did not provide this contract. In v2, when package
  computation is skipped or suppressed, the summary is canonical zero-cost
  `NO BET`: no coupons, zero selected count/cost/payout, full unused bank, and
  unavailable modeled ROI. This is report evidence only and changes no EV or
  package-selection definition.

- Drawing-4950 boundary is defined by strict fail-closed rules: `7/15` raw matches are validly fail-closed without aliases; reviewed aliases may raise the resolved set but unresolved targets are preserved as missing. Two unresolved provider events are not coerced into synthetic matches.
- Exact timing provenance is now required for production decisions. The runner uses `PlayTimingEligibility` as raw and effective pair; only a reviewed timing overlay with exact catalog hash/provenance parity can change effective timing. Any unverified, invalid, or catalog-changed override drives effective timing to `unknown`.
- Runner manifests and scheduler ingestion are strict:
  - current manifest must be `schema_version = 4` and include exact
    `raw`/`effective` timing payloads plus an authoritative
    `pinned_revalidation` summary; schema v3 remains historical only;
  - manifest and package inputs are path-safe and hash-checked (`package_sha256`, timing catalog hashes, manifest manifest fields);
  - strict JSON parsing rejects duplicate keys, non-finite numbers, non-JSON, and symlink/collision hazards.
- Self-dilution budget is exact and authoritative for package budget math: `requested_cap = min(requested_bank, floor(pool_sum*1% / stake) * stake)`, and `effective_budget` follows that cap before EV sensitivity and selection.
- `drawing 4947`/legacy `drawing 4950` `schema_version = 2` runner outputs are historical; they are not a source of current production truth.

## Systematic Team Identity and Preparation

- A production drawing is actionable only when its exact target fingerprint,
  provider, and event IDs have one `ready` preparation and exactly 15 valid,
  fixture-unique pins. Pins carry provider fixture/team IDs and `starts_at`.
- Preparation publication is atomic. An unresolved attempt writes diagnostics
  and review records but zero authoritative pins. A later complete retry may
  replace unresolved state with one transactional ready version. Ready content
  is immutable; changed provider data requires invalidation/new fingerprint or
  fails closed.
- Reviewed aliases and exact provider-team IDs outrank inferred evidence.
  Normalization and transliteration never authorize a match by themselves.
  Non-registry acceptance requires date, competition/country/league context,
  home-away orientation, pair uniqueness, one exact/high-confidence side, and
  confidence margin. Two weak shared-token names remain unresolved.
- Team aliases are scoped by sport, provider, normalized alias, country, and
  competition context. Context-free Phase-1 aliases remain compatible only
  when lookup is unambiguous; SQLite initialization migrates existing rows
  using their canonical team context.
- The production runner defaults to systematic pins. Legacy name matching is
  an explicit direct-command compatibility option and is never inherited by
  scheduler execution.
- Final collection revalidates pinned provider fixture ID, team IDs, start
  time, provider, and schedule freshness. Display-name differences are ignored
  after pinning; unavailable, absent, stale, or changed identity data is a
  fail-closed outcome, not a reason to rematch names.
- Playable work is gated before timing/audit/EV on exactly 15 successful pin
  revalidations. The same provider, fixture ID, oriented home/away team IDs,
  bounded start-time tolerance, fresh schedule, and complete required-date
  fetches are all mandatory. TotoBrief BK fallback is diagnostic only after
  any pin-revalidation failure.
- Schedule preparation expands null starts progressively by UTC dates derived
  from the Moscow drawing horizon. Each date is isolated, successful dates are
  retained, API client cache/retry/quota behavior is reused, and diagnostics
  preserve each failed date's reason. The accumulated candidates are resolved
  without writes after every successful date. Once all 15 resolve uniquely and
  their effective starts are playable within the normal two-day rule, later
  dates are not requested and are not failures. If readiness is not reached,
  the configured horizon is exhausted; any attempted date failure before
  readiness prevents READY and transactional pin publication.
- Preparation derives conservative sport/country/competition/league context
  directly from TotoBrief championship text. Shared country normalization maps
  Russian, English, ISO alpha-2/alpha-3, and common provider forms to one stable
  country identity; it is not a drawing/team alias mechanism. Unknown values
  compare only by deterministic normalized identity. No network translation or
  team-specific alias may supply country identity. Conflicting country, league
  level, date, sport, or orientation fails closed in the production path.
- Drawing numbers, current team names, and provider fixture IDs are test replay
  data only. Production resolution contains no drawing-4951 or per-team branch.

## Passive preflight escalation

- Missing reviewed aliases and provider-missing schedules are different
  evidence classes. Aliases are versioned reviewed team facts with provider
  team IDs, reviewer, review time, and provenance; they are never learned
  automatically from an unresolved drawing.
- A complete provider date window may be declared source-missing only when no
  candidate carries exact, transliterated, reviewed, or provider-ID team
  identity and the best fuzzy collision has no plausible team side. Strict
  reviewed schedule evidence may then fill schedule identity; it cannot mask
  a genuine identity-bearing ambiguous candidate.
- Every unresolved morning run creates local fingerprint-bound attention and
  immutable attempt evidence. Passive retries are exact-identity commands,
  bounded before T−60, idempotent, and contain no evening activation.
- Attention is resolved only by atomic READY 15/15 for the same fingerprint.
  A changed fingerprint receives separate state and cannot clear the prior
  marker.
- Morning generation defaults to 08:00/10:30/12:00 but does not install
  launchd. Evening package automation remains disabled until separately
  authorized; no code places bets.
- `preflight-status --open` is physically read-only. It reports generated
  activation candidates and records but does not inspect, install, enable, or
  execute GUI/launchd state.
- Reviewed-schedule fallback eligibility is date-scoped per event. API-Sports
  schedule dates are UTC; unrelated failed expansion dates do not block an
  event whose own UTC date was fetched successfully. Unknown or relevant
  failed dates remain fail-closed, and reviewed evidence cannot mask an
  ambiguous identity-bearing provider fixture.

## Sports-statistics audit isolation

- `--historical-as-of` is frozen-input only. It may read only local SQLite,
  hash-verified TotoBrief raw detail/sidecar, and provider cache records whose
  fetch timestamps are at or before `as_of`; it must never fall back to any
  network request.
- Historical team-history replay first looks for its bounded `from/to` cache
  key and may then reuse the normal prospective `last=N` key for the same
  provider/team/season/status/timezone request. Reuse is lawful only when the
  cached provider observation time is not later than `as_of`; the actual cache
  key remains part of source provenance, and fixture rows are filtered again
  locally by target ID, team identity, completed status, target kickoff, and
  as-of. A newer compatible cache is never accepted and historical mode never
  contacts the provider.
- Replaying the same frozen evidence with different transport counters is
  idempotent: storage returns the existing immutable run only when every
  semantic event/source/timing field is identical. Any evidence difference
  remains an append conflict. Reports are emitted from that persisted run so a
  prospective-to-offline replay is byte deterministic.
- An available form window contains at least one eligible completed fixture.
  Provider failure, plan denial, no history, and unrelated-team-only history
  are unknown (`None`) with explicit reasons, never synthetic zero-valued
  W-D-L/goals windows.
- Sports-stat run and event identities/boundaries must agree exactly, including
  drawing ID/number, fingerprint, provider, captured-at, as-of, deadline, and
  request-fingerprint provenance.
- Sports-stat collection and persistence are audit-only. They do not update
  archived packages, package decisions, scheduler markers, or PLAY/NO BET.

## Data-health contract v1 decisions

- Contract version `1.0.0` is the single source of truth for drawing
  eligibility; `0/0/0` is never a valid pool.
- `1`, `X`, `2`, and explicit `*`/VOID/cancelled values are terminal health
  outcomes. Missing or unsupported values are not silently normalized.
- `historical_inventory` is intentionally strict: it requires complete
  structure, names, probability inputs, terminal results, canonical RAW,
  immutable result evidence, and settlement of any canonical actionable
  package.
- `backtest_probability` v1 requires complete structure, names, usable
  pool/BK, and terminal results. Missing canonical RAW/result snapshots remain
  explicit observed deficiencies but are not yet blocking for this use case,
  preserving the currently usable SQL research corpus. Such research is not
  proof of pre-deadline provenance.
- `prospective_generation` requires only the data needed before the draw:
  structure, names, usable pool, and complete BK. Historical RAW, results, and
  settlement are not required.
- `result_settlement` requires terminal results plus immutable result evidence.
  Absence of a settlement blocks only when a `pre_bet_runner` package exists.
  Legacy/rehearsal imports are excluded.
- Strict CLI exit code `3` means controlled data-quality failure; execution
  failures use `4`. Research override is explicit, historical-only, and always
  labeled. Prospective generation has no override.
- Gap numbers remain metadata until verified against the authoritative listing;
  the system must not synthesize drawings 3843/3844.

## Dry-run physical read-only contract

- A CLI flag named `--dry-run` means physical as well as logical read-only:
  no schema setup, migrations, `create_all`, SQL mutations, timestamps,
  WAL/SHM, RAW, snapshots, state files, or adjacent reports.
- Dry-run commands must open an existing SQLite file through the project
  read-only engine. Optional additive tables that do not yet exist are empty
  state during preview and must not be created implicitly.
- Previewing canonical RAW computes the importer delta in memory against
  read-only rows. It does not publish immutable evidence; evidence publication
  remains an apply-mode prerequisite before analytical mutation.
- Explicit apply mode owns idempotent schema initialization before its first
  mutation. This separation is tested at the CLI boundary, not only inside the
  reconciliation operation.

## Reusable schedule evidence, not per-drawing exceptions

- New preparation may consume a provider-neutral, append-only reviewed
  schedule ledger. Its unit of reuse is canonical team identity plus exact
  schedule observation, never drawing number, fingerprint or event order.
- Exact normalized/transliterated aliases, same orientation, compatible
  competition and gender/age class, bounded UTC timing, an official HTTPS
  claim and a hash-checked local review record are required.
- Fuzzy similarity is diagnostic only. Conditional pairings, reversed teams,
  source gaps, stale evidence and conflicts never auto-promote.
- Missing target starts expand collection to the complete bounded drawing
  window; they do not collapse the query to the deadline date. The window is
  defined by `Europe/Moscow` drawing-day boundaries and converted to every
  intersecting API-Sports UTC request date, including the preceding UTC date
  when Moscow midnight crosses that boundary. Reviewed alias reuse remains
  exact after normalization and is gated by sport,
  competition, orientation, class, kickoff, freshness and immutable hashes.
- Reusable evidence pins carry both observation and ledger semantic hashes and
  must revalidate against both before final use. Evidence ingestion is
  append-only: an existing observation ID cannot be changed in place.

## Per-event enrichment is optional; probability completeness is not

A prospective drawing may be READY when every one of its 15 exact TotoBrief
events has a complete, finite, positive BK and pool probability row and each
event is either strictly externally resolved or explicitly recorded as
`totobrief-baseline`. Baseline-only rows carry no synthetic provider identity
and use only hash-bound TotoBrief probabilities. Any external identity conflict,
TotoBrief identity drift, invalid/changed probability input, duplicate/missing
order, or ineligible multi-day timing remains fail-closed.

Exact reviewed schedule evidence may match the target in reversed source
orientation only when both canonical entities match exactly; the stored pin
records that orientation and final revalidation requires it unchanged. Fuzzy or
ambiguous reversed evidence remains unresolved.

## Dynamic TotoBrief pool and immutable BK pins (2026-08-04)

- TotoBrief pool percentages are dynamic crowd observations and may change
  normally between morning preparation and final package generation.
- Canonical preparation safety pins bind event identity, order/orientation,
  schedule/provider evidence, reviewed-catalog hashes, and the normalized BK
  matrix. A later BK matrix is not silently accepted as a refresh.
- A newer valid pool snapshot may advance readiness evidence without replacing
  or invalidating canonical pins. An older snapshot or conflicting evidence at
  the same capture timestamp remains invalid.
- Baseline-only pin provenance retains its creation-time pool for audit only;
  it is not the final package input. Final EV and coupon selection consume the
  pool from the fresh atomic TotoBrief final payload.

## Monotonic schedule-evidence enrichment (2026-08-04)

- The project-owned schedule-evidence ledger is the default morning schedule
  fallback and must resolve beneath `project_root`; an explicit override must
  remain contained and is preserved in passive retry commands.
- The legacy `reviewed-schedule-catalog` is a different per-drawing schema and
  must never be passed as the reusable ledger.
- A canonical ready pin set may change for an unchanged drawing fingerprint
  only through one atomic monotonic transition from `totobrief-baseline` to a
  strict reviewed schedule source for the same target event/order.
- Provider pins, target identity/order, reviewed evidence validation and all
  unrelated canonical pin content remain immutable. Any non-monotonic change,
  invalid ledger schema/hash, ambiguity or conflict fails closed.
