# Roadmap

- [x] Decouple morning public-source collection from LaunchAgent activation;
  verify an identity-bound drawing-4986 rehearsal collects Sofascore 10/15 and
  TheSportsDB 12/15 while remaining non-activating and fail-closed.

- [x] `TOTO-THESPORTSDB-CANONICAL-QUERY-20260825`: prioritize deterministic
  canonical/Latin queries, preserve women's/gender identity, keep independent
  names lookup-only, deduplicate bounded forward/reverse searches, and enforce
  a secret-safe hard 30-request per-run transport budget with cache hits
  excluded. Focused provider/collector verification: 28 passed. Team-ID
  fallback remains a separate next step; release policy is unchanged.
- [x] Reject the proposed free TheSportsDB team-ID/upcoming-events fallback:
  the official free-v1 contract restricts generic team search, so the sampled
  lookup is not a lawful universal production path.
- [ ] Run a provider-neutral schedule bake-off for GOAL API on at least ten
  consecutive mixed Toto drawings (15/15 exact identity/kickoff required),
  with SportsDataAPI as the second candidate only if the first fails. Keep both
  candidate-only until the prospective evidence is complete.
  - [x] Validate the protected free key and complete drawing-4986 canary:
    observed 15/15 exact fixtures, 1,000/day quota, explicit-user-agent
    transport required; API-Sports remains configured but provider-suspended.
  - [x] Implement the reusable candidate-only adapter and run drawing-4987:
    raw and matched coverage 15/15, 37 requests, quota 883/1,000. Record the
    12/15 kickoff-before-`ended_at` rows as blocking `timing_conflict` rather
    than source misses or playable evidence.
  - [x] Resolve the operational boundary from official BaltBet rules: bets
    must precede the earliest event, so 4987 uses no later than 18:45 MSK and
    T-10 at 18:35 MSK; TotoBrief `ended_at=21:45 MSK` is not safe here.
  - [ ] Propagate a scheduler-owned conservative cutoff that can only tighten
    `ended_at`, and keep missing/conflicting earliest-kickoff evidence
    fail-closed.
- [x] `TOTO-THESPORTSDB-PROVIDER-20260824`: add a rate-limited TheSportsDB v1
  schedule provider using the documented public key by default, official-host
  fail-closed transport, immutable snapshots, normalized scheduled/not-started
  evidence, bidirectional query coverage, existing alias/orientation matching,
  secret-safe diagnostics and independent candidate collection. Keep the
  current ledger/release rule unchanged: TheSportsDB cannot promote alone.
- [ ] Evaluate the future two-independent-source promotion lane only as a
  separate architecture/policy change with explicit review; this provider task
  does not authorize it.

## Active execution sequence (2026-08-14)

The authoritative implementation order is tracked in
`plans/TOTOAI-PRODUCT-VALIDATION-20260814/plan.md` and its `progress.md`:

1. close live drawing 4975 through post-draw settlement;
2. compare current EV/crowd, BK probability-only and TotoBrief-style cover;
3. run a strict chronological canary/all-available benchmark and separate
   100/500/1000 legacy diagnostics;
4. correct only measured package-objective defects;
5. complete official+independent schedule automation and free sports coverage;
6. train/walk-forward evaluate a residual model around BK;
7. pass a predeclared prospective paper holdout;
8. only then review a validated real-money release.

Operational evidence collection may run in parallel, but package activation
cannot skip a gate. A separately authorized experimental manual release may
expose one fresh final package while explicitly retaining
`profitability_proven=false`; it is operator-risk testing, not completion of
the validated release stage.

- [x] `TOTO-MORNING-WRAPPER-COMPAT-20260824`: centralize generated
  `morning-dispatch` argv, contract-check the parsed wrapper against the current
  Typer CLI, and generate an uninstalled v4 candidate with the existing hourly
  interval and six fixed triggers.
- [x] Make generic morning discovery deadline-independent with a bounded
  recurring trigger, and add an idempotent scheduler-owned non-actionable
  READY training calculation using configured bank/stake/category. Verify the
  supported CLI path on drawing 4982 without changing live scheduler/release
  state or creating operator-actionable markers.

Current progress: the real drawing-4975 paper lifecycle is closed through
settlement and reviewed postmortem. The shared frozen-input contract,
EV/BK/Cover-13/Cover-14 adapters and `compare-package-strategies` report bundle
reproduced the exact drawing-4975 EV paper package. Five additional strict
drawings 4976-4980 extend the immutable sample to 18 unique drawings. BK-only
and Cover-14 average 8.889 best hits versus 6.889 for current EV/crowd, but the
sample is still below the 30-drawing interpretation floor and no strategy or
profitability verdict is allowed. The resumable legacy-100 diagnostic is
complete: EV/crowd trails BK-only by -1.650 best hits with nominal 95% interval
[-2.210, -1.120], while Cover-14 is +0.260 [0.060, 0.460] but spends only
2,757 RUB on average. This remains non-chronological diagnostic evidence, not
a winner or profitability verdict. A 500-row resume was stopped at 116
checkpoints; 500/1,000 are deprioritized because they cannot establish
chronology or observed ROI. Drawing
4981's two missing UEFA kickoffs
were resolved from frozen official UEFA plus independent Sofascore evidence;
the passive 12:00 retry completed automatically and activated evening paper
plan `5caf88df9bdfe566` with eight triggers. The reusable automatic UEFA
official-adapter/promotion path remains phase-4 work; this reviewed evidence
does not by itself complete schedule automation.

Measured chronology constraint: only 13 drawings currently satisfy the strict
pre-deadline historical-inventory contract, while 1,672 satisfy the weaker
probability-backtest contract. Phase 2 will run a strict 3–5 canary and all 13
only as pipeline evidence, separately from 100/500/1,000 legacy diagnostics;
legacy output is not release evidence. See the active plan's
`phase2-data-eligibility.md`.

- [x] Add strict RAW-before-deadline loader, terminal-result separation, VOID
  scoring, actual exposure, package overlap, CLI and hash-bound reports.
- [x] Run strict canary and all 13 currently eligible drawings at 4,980/30.
- [x] Add physically separate, resumable legacy input/runner/checkpoint/report
  path and verify a real one-drawing calculate/resume canary.
- [x] Add the explicit BK-top single-coupon control and deterministic paired
  bootstrap intervals; rerun all 13 strict drawings with interpretation
  disabled for the small sample.
- [x] Synchronize and analyze finished drawings 4975-4980; preserve 4975 as a
  real settled package and 4976-4980 as retrospective strict strategy rows.
- [x] Complete Legacy-100 diagnostic without using it in release metrics.
  Preserve the 116 resumable checkpoints, but do not spend the current cycle on
  Legacy-500/1,000 unless a new explicit diagnostic question justifies them.
- [ ] Automatically archive and later settle equal-input prospective packages
  from BK-only, current EV/crowd, Cover-13 and Cover-14 for each new eligible
  drawing. Do not tune or choose a winner before the preregistered sample floor.
- [ ] Keep further BK-only optimizer tuning closed after the sealed hybrid
  `STOP`; any new optimizer hypothesis needs a preregistered protocol and a new
  untouched/prospective evaluation window.
- [ ] Capture lawful pre-deadline `Possible winnings` and post-draw payout
  evidence; until then keep modeled EV/ROI separate from observed return.
- [x] Add immutable plan-bound experimental manual authorization, final-only
  promotion, schema-v3 operator provenance, preflight release status and
  structured passive-retry logs without automatic wagering.
- [ ] Exercise the authorized path on drawing 4982 only after all 15 kickoff
  times are resolved and its exact evening plan is generated; verify manual
  export before T-10 and retain the full post-draw audit lifecycle.
  - [x] Resolve all 15 kickoff times, publish exact canonical pins, activate
    schema-v6 plan `453829753fa55b5f`, verify the installed LaunchAgent and
    create the exact plan-bound experimental manual authorization.
  - [x] Extend the read-only preflight status with hash-verified per-phase
    attempts, reasons, next checkpoint, overdue detection and terminal state.
  - [ ] Observe each scheduled phase, verify a fresh final `PLAY` or an
    evidence-backed legitimate `NO BET`, and exercise `operator-export` before
    T-10 if and only if the final result is actionable.
  - [ ] Preserve the terminal package/package-free result for settlement and
    mandatory post-draw review.

- [ ] Teach the gap audit to accept hash-bound documented upstream numbering
  gaps. TotoBrief's public listing skips 3,843/3,844 between 3,842 and 3,845;
  these are not missing local drawing records.

## Completed: operator-safe publication and timing escalation (2026-08-13)

- [x] Add one mandatory `operator-export` gateway for current scheduler-owned,
  archived, hash-bound, pre-T-10 `PLAY` packages.
- [x] Suppress misleading operator-path output for `NO BET` and internal audit
  artifacts; expire the canonical upload at T-10.
- [x] Turn baseline-only missing kickoffs into explicit `timing_unknown`
  attention, reviewed-schedule queue entries, and identity-bound retries.
- [x] Make repeated `timing_unknown` attention refresh idempotent and resolve
  drawing-4974 events 8/15 from hash-checked official plus independent
  evidence; rerun the bound preflight to READY 15/15 and activate its evening
  scheduler.
- [x] Freeze the failed unbound drawing-4973 file as non-actionable regression
  evidence without copying its coupon strings.
- [ ] Exercise the gateway on the next fresh final scheduler result. A
  validated release still requires the prospective gate; a plan-bound
  experimental manual result must remain explicitly unproven.
- [ ] Complete the prospective package lifecycle: canonical package -> result
  or VOID -> immutable settlement -> mandatory post-draw review.

- [x] Reproduce and remediate the 4972 HTTP-429/final-timeout incident with an
  immutable LKG checkpoint, phase-local final/retry budgets, pre-T-10 degraded
  fallback, deterministic early NO_BET, and operator-facing artifacts. Current
  verification is in-process; exact launchd overlap remains unclaimed.

## Implemented: shadow sports probability provider

- [x] Convert frozen API-Sports form/goals/standings snapshots into
  experimental per-event `1/X/2` shadow probabilities without changing
  current packages.
- [x] Preserve explicit event-level normalized TotoBrief BK fallback and
  record exact feature, orientation, hash, chronology, and source provenance.
- [x] Emit machine-readable `NOT_ACTIVATED` artifacts with BK, sports-shadow,
  candidate blend, features, fallback reasons, and evidence identity.
- [x] Implement chronological OOS comparison using multiclass log loss,
  Brier, ECE, counts, coverage, fallback, and validation failures.
- [x] Implement a fail-closed activation gate that cannot activate production.
- [x] Harden shadow OOS evaluation: immutable pre-`as_of` authoritative BK,
  independent fingerprint authority, strict orientation, blocking integrity /
  leakage reasons, and non-weakening 30/450/70% activation minima.
- [x] Correct the experimental model to use only home-team home W-D-L and
  away-team away W-D-L. Missing venue history now uses explicit BK fallback;
  aggregate W-D-L remains diagnostic and cannot count as sports coverage.
- [ ] Prospectively collect at least 30 drawings / 450 events with at least
  70% valid non-fallback sports coverage.
- [ ] Run and freeze the chronological OOS report. Require strict candidate
  blend improvement over BK in log loss and Brier, calibration within the
  declared tolerance, and zero leakage/fingerprint/validation failures.
- [ ] Consider production influence only as a separate reviewed architecture
  change after the evidence gate passes.
- [x] Keep quality-v2 `NO BET / TRAINING-PAPER`; no profitability is proven.

Current production baseline: normalized TotoBrief BK supplies all outcome
probabilities and pool supplies crowd/EV input. Sports probabilities exist only
in the shadow artifact/evaluator and remain `NOT_ACTIVATED`. Injuries, lineups,
xG, and Elo are not implemented.

Older scheduler-v5 and wager-ready items below are historical implementation
records, superseded operationally by schema v6 and the paper-only boundary.

## Completed: drawing 4972 country-scoped matcher coverage

- [x] Add reusable country-scoped exact team identity families for the four
  observed provider naming gaps without drawing or fixture hardcodes.
- [x] Add country-scoped translated competition taxonomy for Colombia, Chile,
  and Finland without weakening global league-level comparison.
- [x] Require same orientation, two strong team identities, country agreement,
  date evidence, and unique-fixture margin for taxonomy-assisted acceptance.
- [x] Keep reversed, ambiguous, wrong-country, out-of-window, and truly missing
  cases fail-closed with baseline-only fallback where appropriate.
- [x] Freeze drawing 4972 at fresh 15/15 provider coverage, playable timing,
  and an exact two-day Moscow span.
- [x] Preserve immutable ready pin behavior; provider refresh is not a new
  monotonic-upgrade path.

## Completed: safety-aware EV coupon reselection

- [x] Preserve EV/probability mathematics and the final safety veto.
- [x] Select exact dynamic-bank cardinality from a broad deterministic
  candidate universe.
- [x] Repair material-outcome gaps and concentration violations with stable,
  EV-loss-aware swaps and canonical hashes.
- [x] Fail closed with explicit infeasibility diagnostics.
- [x] Cover zero exposure, concentration, repeatability, dynamic banks,
  infeasibility and unchanged final-veto behavior.
- [x] Freeze pre-cutoff no-leakage regressions for drawings 4967, 4969 and 4970
  and record measured structural/hit evidence without profit claims.

## Completed: scheduler immutable ledger binding

- [x] Bind canonical ledger path, content SHA-256 and semantic hash into
  schema-v6 plan identity and artifacts.
- [x] Revalidate the exact binding before every scheduler stage, preparation
  and final collection pass.
- [x] Make missing/tampered/malformed ledgers and immutable pin conflicts
  terminal integrity failures while preserving transient transport retries.
- [x] Reject unbound schema-v5 plans with an explicit regenerate-v6 diagnostic.
- [x] Cover drawing 4967, path/byte/semantic identity, tamper, missing ledger,
  old plan and retry classification without live runtime mutation.

## Completed: scheduler canonical-ledger forwarding

- [x] Pass the canonical contained schedule-evidence ledger in every future
  scheduler `prepare-drawing` command.
- [x] Expose and forward the ledger through the real `prepare-drawing` CLI.
- [x] Cover scheduler construction and local-cache/local-schedule CLI wiring.
- [x] Preserve scheduler plan schema and all existing pin-set safety rules.

## Completed: drawing 4967 canonical pin upgrade

- [x] Reproduce the persisted `conflicting immutable canonical pin set` path.
- [x] Preserve all 11 strict provider pins while upgrading baseline-only rows
  2, 9, 14 and 15 through validated schedule evidence.
- [x] Preserve TotoBrief orientation for reversed schedule-only event 14.
- [x] Enforce exact selected-evidence hash binding and atomic rollback.
- [x] Cover downgrade, provider identity drift, kickoff conflict, hash mismatch
  and ambiguous-ledger rejection with integration regressions.
- [x] Verify focused and full test suites without live activation or network.

## Completed: TotoBrief TLS resilience and early preflight

- [x] Preserve redacted structured transport causes, categories, and attempts.
- [x] Persist and log every scheduler-stage failure detail.
- [x] Add idempotent T−120/T−90/T−60 diagnostics under shared rate limiting.
- [x] Keep TLS verification mandatory and final input fresh-network-only.
- [x] Fail closed with coupon-free `NO BET` when final transport is unavailable.

## Immediate production blockers

- [x] `TOTO-4964-SCHEDULER-LABEL-FIX`: centralize canonical schema-v5
  LaunchAgent label derivation across generation, dispatch, installation,
  records/status and CLI; reject stale or tampered identity before launchd
  mutation.
- [x] `TOTO-NIGHTLY-CAPTURED-SELECTION-DRIFT-V1`: freeze one eligibility
  reference instant and immutable candidate identity per nightly run so
  in-run cooldown expiry cannot create false drift, while real drawing/result
  changes still fail closed.
- [x] `TOTO-SCHEDULER-SCHEMA-V5-TMINUS10`: version the T−10 scheduler as v5,
  bind exact trigger semantics into plan identity/artifact verification, and
  reject stale schema-v4/T−12 plans with an explicit regenerate diagnostic.
- [x] `TOTO-DEADLINE-TZ-AND-TMINUS10-V1`: accept and UTC-normalize aware
  `--expected-deadline` values, reject naive/malformed inputs, preserve exact
  identity mismatch handling, and standardize plan/status/launchd publication
  at T−10 without enabling automatic betting.

## Historical data-health remediation

- [x] Fix offline canonical-RAW classification idempotency, isolate it from
  network `source_incomplete`, and prove drawing-4954 correction-once followed
  by a byte/logical no-op replay
  (`TOTO-OFFLINE-REPAIR-CLASSIFICATION-IDEMPOTENCY-V1`).
- [x] Add durable per-source reconciliation cooldown, separate transient retry,
  expiring quarantine, force override, deterministic clock, and fair range
  batching (`TOTO-RECONCILE-SOURCE-INCOMPLETE-COOLDOWN-V1`).
- [x] Complete the network-free drawing-4946 replay on a copied database and
  record exact state/RAW deltas.
- [x] Run a small backed-up production reconciliation batch only after replay
  acceptance; compare Data Health before/after.
- [x] Audit visible drawings 4940–4959 in the local SQLite database.
- [x] Expand the audit to the complete locally stored `baltbet-main` history:
  2,199 drawings, 32,985 events, visible range 2759–4959.
- [x] Classify local evidence as recoverable from RAW, requiring a future
  TotoBrief request, or permanently unknown unless new authoritative evidence
  is obtained.
- [x] Implement `TOTO-DATA-HEALTH-CONTRACT-V1`: a versioned, read-only
  per-drawing health contract and `data-health` CLI with machine-readable
  reasons.
- [x] Reject `0/0/0` pool triples as unusable rather than merely non-null.
- [x] Fix collector freshness so a transition to `finished` requires terminal
  results or explicit unresolved/void evidence.
- [x] Make final-result ingestion restore complete event identity, names,
  quotes, results, scores, and statuses from one validated detail payload.
- [x] Archive every fetched detail payload RAW-first with identity, timestamp,
  and hash provenance before mutating operational tables.
- [x] Repair the locally recoverable class-A defects from immutable RAW without
  overwriting reviewed `VOID` evidence.
- [x] Add a resumable, rate-limited network backfill for class-B/class-C gaps;
  never synthesize missing history when TotoBrief cannot supply it.
- [ ] Process the historical class-B/class-C backlog through repeated small,
  backed-up allowlist waves; unrestricted bulk mode remains forbidden.
- [ ] Create immutable result snapshots for every completed usable drawing.
- [ ] Gate every backtest/research dataset by its declared requirements:
  exactly 15 events, nonblank identity, usable required pool/BK inputs,
  complete `1/X/2/VOID` terminal outcomes, and valid as-of provenance.
- [x] Implement bounded passive nightly result reconciliation for the latest
  30 finished drawings with an eight-attempt cap, exact captured allowlist,
  shared lock, backup/retention, cooldown/quarantine, Data Health/integrity
  reports, and generate-only 03:20 LaunchAgent artifacts
  (`TOTO-NIGHTLY-RECONCILIATION-V1`).
- [x] Complete controlled waves 2/3 and the wave-2 idempotency replay; restore
  available evidence without synthesizing source-empty results.
- [x] Review and explicitly install
  `com.totoai.nightly-reconciliation.v1` at 03:20 Moscow time after the
  network-free rehearsal and operator smoke; smoke completed `PARTIAL` with
  seven of eight captured drawings restored and one cooled down.
- [ ] Observe and review the first calendar-triggered nightly run; keep the job
  bounded to latest 30, maximum eight, no-force and results-only.
- [ ] Keep rehearsal/simulation package archives out of production
  performance and realized-ROI statistics.
- [ ] Require settlement and a post-draw report for every production package,
  including explicit missing-payout evidence.
- [ ] Repeat mixed-provider 15/15 preparation and final revalidation in the
  main operational database with activation disabled.

Do not add another optimizer before the P0 data-health contract, collector and
importer corrections, RAW-first archive, and post-draw lifecycle are complete.
The authoritative full-history audit and remediation plan are stored under
`plans/TOTO-FULL-HISTORY-DATA-AUDIT/`. The earlier interval audit remains under
`plans/TOTO-DRAWING-COVERAGE-AUDIT-4940-4959/`.

## Scheduler operational remediation

- [x] Complete drawing-bound passive preflight retry scheduling and its
  reusable isolated rehearsal: exact artifact verification, secure environment
  loading, mixed-source READY reuse, terminal cleanup, hard-stop, drift,
  missing-key and bounded-transport scenarios all pass without package/bet
  output or main-database mutation.
- [ ] Keep production preflight retry LaunchAgent activation separate and
  operator-authorized; no drawing-4961 retry job is installed or loaded.

- [x] Add drawing-4959 contextual API-Sports identities for Gimnasia L.P.
  (434) and River Plate (435), reject domestic/global-friendly crossover, and
  retain Iceland 3. Deild as an explicit source-missing non-match.
- [x] One immutable final snapshot and canonical probability binding.
- [x] Independent T−45/T−30/T−20/T−16/T−10 ticks and zero-cost `NO BET`.
- [x] Dynamic drawing-neutral morning dispatcher.
- [x] Make repeated morning-dispatch automation retries idempotent by reusing
  persisted exact-drawing state without notification conflicts.
- [x] Persist generated state before activation and safely reuse exact
  artifacts after bootstrap failure or process interruption.
- [x] Reuse one per-drawing plan across a permitted two-day drawing.
- [x] Typed/status-based retry classification; no message substring matching.
- [x] Reject incompatible production `--run-id`, preserve schema-v3 root, use
  correct T−10 diagnostics, and blanket-ignore generated reports.
- [x] Reacquire time after morning/preflight network preparation and block
  post-preparation plan generation at or after T−45.
- [x] Record final snapshot capture at detail-response completion.
- [x] Remove stale actionable package/archive files on late recovery to
  zero-cost `NO BET`.
- [x] Enforce the actionable cutoff for final calculation completion,
  recomputed subprocess timeouts, and every retry admission.
- [x] Reserve the remaining interval through hard T−10 exclusively for
  package/archive-manifest writing, durable archive, recovery, status, and
  marker publication; allow recovery through T−10 and fail closed after it.
- [x] Current verification: five exact reserve boundaries, 175 focused
  scheduler/morning tests, 1443 full tests, Ruff, and diff check.
- [x] Add a lawful provider-neutral schedule fallback for events absent from
  API-Sports; drawing 4958 women event 5 and drawing 4959 Iceland 3. Deild
  event 9 are real examples. Reviewed evidence is strict, snapshot-backed,
  source-neutral, and never injected as an API-Sports fixture.
- [x] Run drawing-4959 activation-disabled morning drill: 14 safe candidates,
  one explicit source-missing event, zero partial pins, no evening plan,
  package, marker, activation, or bet.
- [x] Run the historical schema-v4 five-trigger network-free simulation after
  the 2026-07-29 scheduler fixes; schema v4 is now stale and must be regenerated
  as v5 before any future execution.
- [x] Split generic morning automation into passive default and explicit
  post-drill `--activate-evening` mode; full verification is `1444 passed`,
  with Ruff and diff checks green.
- [x] Install and verify the passive generic morning dispatcher at
  08:00/10:30 Moscow time; its installed wrapper contains neither `--activate`
  nor a drawing number. Manual launchd execution completed three bounded,
  consistent 4959 deferrals without an evening plan/package/marker.
- [x] Repeat an activation-disabled 15/15 live drill. Drawing 4959 passed on a
  copied DB with 14 API-Sports pins plus one reviewed schedule pin, source
  revalidation 15/15, no activation, and no betting artifacts.
- [x] `TOTO-PREFLIGHT-ESCALATION-AND-FALLBACK-V1`: add reviewed alias facts,
  identity-bound unresolved escalation, passive bounded retries, strict
  reviewed-schedule queue, attention lifecycle, and read-only
  `preflight-status --open`.
- [x] Run drawing-4960 network-free regression on an isolated DB copy:
  initial 13 event matches with atomic 0/15 pins and ACTION REQUIRED; reviewed
  aliases plus strict rehearsal evidence reach READY 15/15 with 14 API-Sports
  pins and one reviewed-schedule pin; no activation, package, or bet marker.
- [ ] Enable automatic evening activation only after that drill passes.
  This remains explicitly out of scope and is not authorized by the drill.

## Sports statistics milestone

- [x] Provider-neutral immutable football contracts and validators.
- [x] Append-only run/event persistence and as-of lookup.
- [x] Existing-transport API-Sports adapter and strict no-future filtering.
- [x] Recent form/home-away/rest/standings feature builder.
- [x] Audit-only CLI and JSON/CSV/Markdown reports.
- [x] Prospective acceptance run on drawing 4957.
- [x] Independent-review hardening: strict network-free historical replay,
  nullable unknown windows, actual standings capability parsing, full
  run/event identity validation, unrelated-team rejection, deterministic
  reports, legacy-DB initialization, package/PLAY isolation tests, and safe
  reuse of a frozen prospective `last=10` history cache by historical
  `from/to` replay with strict as-of and local fixture cutoffs.
- [ ] Select a lawful source with current-season history/standings coverage.
- [ ] Accumulate at least 30 frozen drawings / 450 events with material
  non-fallback sports coverage.
- [ ] Run chronological out-of-sample sports-only and capped-blend evaluation
  against bookmaker log loss, Brier, calibration, and coverage.
- [ ] Consider a capped bookmaker/sports blend only after a frozen
  no-degradation gate passes.

The API-Sports free-plan result is a provider limitation, not a reason to
weaken the as-of contract or substitute old-season/currently fetched data.
Until a suitable source is selected, `p_final = p_market`.

## Hybrid Package Program — Milestone 1 complete

The ordered program is defined in
`plans/hybrid-package-program/plan.md`. Its goal is to compare and eventually
operate three explicitly different strategies for every eligible drawing under
the same dynamic bank: true conditional **Cover**, exact modeled **EV**, and a
calibrated/concentration-controlled **Hybrid**. No strategy claims profit.

Ordered vertical milestones:

1. **COMPLETE:** Package strategy metadata and deterministic
   concentration/Hamming/coverage audit with schema-v1 JSON/CSV/Markdown,
   `package-audit`, independent exact streaming distance, dynamic banks,
   canonical hashes, probability-aware warnings, and the independently
   verified drawing-4952 acceptance reproduction. Acceptance: focused
   `88 passed`, full `1269 passed`, Ruff passed, `git diff --check` passed,
   real drawing-4952 audit verified, and all P1/P2 findings closed.
2. True probability-aware Cover strategy with exact verification and a common
   EV/Cover comparison.
3. **IN PROGRESS:** Append-only prospective package archive, forced post-draw
   result refresh, settlement, and expected-vs-actual ledger. Explicit
   finished-result sync, immutable package/result/settlement evidence, bounded
   retries, reviewed VOID-event settlement, and the short fail-closed
   active-detail freshness boundary are implemented. Mandatory production
   scheduler integration and complete official payout evidence remain.
4. Provider-neutral lawful sports-statistics collection, morning cache,
   historical backfill, and canonical football/hockey feature snapshots.
5. Chronologically evaluated and calibrated market/sports probability blend;
   market remains prior/fallback and sports influence remains audit-only until
   frozen gates pass.
6. Hybrid optimizer combining category-hit probability, Cover/Hamming
   coverage, modeled EV, and explicit diversity/concentration constraints.
7. Morning and evening three-strategy scheduler integration with dynamic
   stake-multiple banks and manual package upload only.
8. Separate bounded post-draw scheduler that refreshes results/payout evidence,
   settles every archived package, and surfaces missing data.

The first slice reproduces the known drawing-4952 package audit
(`EV`, 166 coupons, fixed events 1/5/8/14/15, event-12 frequency 163/2/1,
union brief 5184, no 13/14/15 guarantee, worst distance 6) before Cover or
Hybrid selection is changed.

Future/not implemented milestones include actual Hybrid package
selection/optimization; an official/reputable sports-statistics probability
model with calibrated integration; mandatory post-draw result refresh,
settlement, and payout/profit/ROI ledger; and morning/evening/post-draw
scheduler integration for the unified Cover/EV/Hybrid lifecycle. True
probability-aware Cover generation and common EV/Cover comparison are also
future work. Completion of the audit foundation is not evidence of
profitability or a proven winning strategy.

## Phase 1: Infrastructure - completed

- API client
- Historical collector
- SQLite storage
- Audit
- API inspector
- Validation suite
- Persistent project knowledge base

## Phase 2: MVP - completed

- Cover Engine
- Exact cover verifier
- Baseline brief generator
- Current/open drawing selection
- CSV exports

## Phase 3: Baseline evaluation - in progress

- Backtest baseline brief generator on 100/500/1000 completed drawings.
  - Backtest CLI and report export are implemented.
- Measure brief containment.
- Measure package best hits.
- Measure 13/14/15 hit rates.
- Measure average cost.
- Compare category 13 vs 14.
- Compare different budgets.
- Compare against simple baselines.
- Use `budget-oracle` to estimate the gap between baseline generation and an
  oracle package under the same budget.
- Use budget-oracle progress, timeout, and timing diagnostics for longer
  baseline/oracle comparison runs.
- Use `budget-oracle --profile-workload` to inspect generated/unique candidate
  counts, Cover Engine calls, cache hits/misses, brief variant sizes, and
  slowest candidate briefs before changing search strategy.
- Budget Oracle retains pruning diagnostics, but unsafe dominance and
  full-cover cost pruning are disabled.
- Implement the approved Direct Package Optimizer experiment and compare
  `baseline_brief`, `top_probability`, and `weighted_coverage` on a chronological
  development/holdout split. Completed for a frozen retrospective 500-drawing
  experiment with 350 development and 150 holdout drawings.
- Use 5000 RUB as the primary bank and 3000/10000 RUB as sensitivity checks.
- Diagnose the weighted-coverage objective on development data: it improved
  average best hits but did not improve development 13+ frequency over
  top-probability. Completed on all 350 frozen development drawings.
- Implement deterministic package structure and overlap metrics for development
  strategy diagnostics. Completed.
- Add a fail-closed development diagnostics CLI that regenerates packages,
  verifies frozen package hashes/results, and exports deterministic reports.
  Completed.
- Hybrid Direct Package experiment Tasks 1-5 are completed: selector, GO/STOP
  model, fail-closed evaluator, atomic reports/CLI, and sealed development run.
  The final decision is STOP: no hybrid added the required two 13+ hits over
  top-probability. Total 13+ counts for top/0.50/0.75/0.90 were 6/4/5/6;
  per-fold counts were 0/0/0/0, 0/0/0/0, 1/0/0/1, 1/1/1/1, and 4/3/4/4.
  Average best hits were 8.691429/9.491429/9.288571/9.060000, with zero
  operational failures. The sealed rerun exactly reproduced these metrics with
  zero holdout-ID overlap and zero timeouts. BK-only optimizer tuning is closed.
- Harden the hybrid development boundary with a reproducible development-only
  seal and separate canonical CSV, pre-drawing input, result, and protocol
  hashes, plus clean-code binding and rollback-safe artifact publication.
  Completed without changing strategies, folds, budgets, categories, or
  GO/STOP criteria.
- Extend the hybrid deadline across all package-generation stages and skip
  post-timeout exact coverage work. Completed.
- Reserve a new untouched or prospective evaluation window before claiming an
  improvement from further optimizer tuning.

## Phase 4: Research

- Bookmaker calibration
- Brief oracle research
- Budget-constrained brief oracle
- Pool calibration
- Crowd calibration
- Pool vs BK bias
- Draw underestimation
- Favorite overestimation
- Position streak hypotheses
- League effects
- Entropy and uncertainty
- Cancelled/missing-result handling

## Phase 5: Probability Model

- Direct Pinnacle access is unavailable for this project; prohibited scraping
  is excluded.
- Evaluate lawful third-party feeds, starting with API-Sports football/hockey,
  for coverage, terms, freshness, historical availability, and event matching.
- API-Sports coverage-audit Tasks 1-6 are complete: provider-neutral records,
  API-Sports transport/cache/quota, strict deterministic fail-closed event
  matching with reviewed alias diagnostics, and strict three-way
  market-semantics consensus with explicit fallback, plus append-only
  prospective storage and deterministic 15-event collection with explicit
  TotoBrief BK fallback. Task 5 storage is review-hardened with identity-bound
  schedule/market fetch provenance, canonical quote ordering, and deterministic
  duplicate-key anomaly coalescing under the unchanged uniqueness constraint.
  Task 6 adds read-only stored-snapshot coverage auditing, deterministic atomic
  CSV/Markdown reports, `collect-external-odds`, and
  `audit-external-coverage`. Task 6 review hardening completes the aggregate and
  per-scope report schema, exact fallback classification, bookmaker-threshold
  diagnostics, and dedicated report atomicity/determinism coverage. Task 7
  adds end-to-end fail-closed acceptance for success/mixed/failure/quota/
  interruption paths, report evidence, EV non-interference, and API-key absence
  across persistence, cache, CLI, exception chains, and reports.
- Final whole-branch review fixes are complete for the coverage-audit branch:
  consensus now uses an external observation clock distinct from TotoBrief
  target provenance; official item-level API-Sports odds updates are parsed as
  bookmaker defaults; schedules and odds fetch all pages fail-closed; market
  outcomes reject duplicate or unknown labels before provider-neutral records;
  and actual HTTP attempts are reported separately from cache hits.
- Live-contract hardening is complete for the first authorized API-Sports run:
  unpaged schedule requests, official odds items without teams/top-level
  timestamps, numeric non-three-way labels, cache observation timestamps,
  daily/minute quota semantics, stale-cache quota isolation, and TotoBrief
  `start_at=null` matching are covered by regression tests.
- Matcher v3 reversed-pair mapping is complete and live-verified on drawing
  4945: 13/15 unique exact matches and usable consensuses, two explicit
  fallbacks, two recorded reversed orientations, and zero ambiguous matches.
  Consensus `1`/`2` is swapped only for reversed pairs; raw prices are retained.
- Fresh prospective orchestration is complete: one target is pinned, isolated
  run caches prevent stale observations, and approved operational fallbacks are
  retried across the API-Sports minute reset. The final live drawing-4945 T-15
  run finished in two passes and 69.04 seconds with 13/15 consensuses, leaving
  13 minutes 50 seconds before the betting deadline.
- Remaining coverage-audit work: collect the prospective sample. The operator
  gate remains `PENDING` below 30 drawings and 450 events; external consensus
  still has no `PLAY` impact.
- Run the free-tier prospective gate on at least 30 future drawings and 450
  events before external probabilities can influence package generation.
- Test a second free provider when the gate fails for missing coverage; consider
  a paid plan up to 30 USD/month only when quota is the measured blocker.
- Add a provider-neutral, event-level probability interface with explicit
  TotoBrief BK fallback and prospective odds storage.
- Feature builder
- Train/validation/test split by time
- Calibration
- Log loss, Brier score, ROC-AUC where appropriate
- Avoid data leakage

## Phase 6: Package Optimizer

- Cover Engine performance optimization for greedy cover is implemented.
- Direct Package Optimizer design is approved; v1 targets holdout `13+` rate
  directly with BK probabilities and a 5000 RUB bank. V1 and its frozen
  retrospective comparison are implemented; no statistically proven winner was
  found.
- Safe Budget Oracle optimization remains open. Any future pruning must match
  exhaustive evaluation in regression tests.
- Compare greedy cover, MILP, simulated annealing, genetic algorithms.
- Optimize expected value and probability of 13+/14+/15.
- Monte Carlo simulation.
- Implement the approved Expected-Value Package Engine in the sequence defined
  by `docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md`:
  pure payout/reference math, exact ternary full-space engine, dynamic-bank
  research/playable selection, reports/CLI, then chronological evaluation.
- Chronological modeled-EV evaluation is implemented with frozen-holdout
  exclusion before event queries, pre-result package hashing, reusable complete
  factor rankings, dynamic banks/thresholds, resumable exact-config checkpoints,
  realized 9..15 indicators, deterministic reports, and `backtest-ev`.
- Task 6 integrity hardening is complete: latest-N result-complete backfilling,
  diagnostic-only skip re-evaluation, exact checkpoint Cartesian grids and row
  invariants, SQL projection leakage tests, live-compatible 1% self-dilution
  suppression, and configuration-hash-scoped final/checkpoint artifacts.
- Task 6 checkpoint package integrity is complete: SQL parameter scoping covers
  every Event/Quote query, and checkpoint-only canonical coupon manifests make
  package hashes exactly verifiable while rejecting missing, duplicate, orphan,
  conflicting, or tampered package records.
- Task 6 row binding is complete: SQL scope checks derive drawing IDs from
  explicit Event/Quote predicates, and canonical per-manifest row references
  reject swapped equal-count hashes plus duplicate, missing, extra, or unsorted
  checkpoint contexts.
- End-to-end EV acceptance is complete: tests cover honest `NO BET`, dynamic
  bank caps, deterministic reports, interruption safety, and the small oracle
  guard. The mandatory benchmark evaluated all `3^15 = 14,348,907` coupons
  without truncation and independently verified 20 samples with `PASS`.
- Playable gross-EV thresholds 0.90, 0.95, 1.00, and 1.05 are covered by package
  and chronological backtest tests, including bank utilization and `NO BET`.

## Phase 7: Production
- Atomic-final scheduler remediation is complete: canonical zero-cost
  `NO BET`, immutable one-fetch final detail, snapshot-fed preparation/EV,
  plan-v5 five-trigger ticks, persistent restart/concurrency state, bounded
  retry, T−10 cutoff, runner manifest v5, and archive manifest v2 provenance
  are implemented and fixture-tested. Terminal `bet_ready` is committed only
  after marker success; marker failures stay package-free/failed, archive
  recovery rechecks current timing overrides, and activation retry verifies
  exact plan/wrapper/plist bytes. Generated LaunchAgent candidates remain
  uninstalled; a bounded operator-controlled drill is still required before
  any manual installation.
- Dynamic morning dispatcher implementation is complete: the recurring
  candidate contains no drawing number, pins one fresh exact drawing, retries
  deferred preparation idempotently, and creates one per-drawing schema-v5
  evening plan only before T−45. The five known obsolete LaunchAgents were
  removed and follow-up inspection found none installed or loaded.
- Next operational gate: run an activation-disabled morning plus atomic-final
  drill on drawing 4958, inspect exact identity/readiness, all due ticks,
  immutable final-input provenance, terminal decision, and absence of automatic
  betting. Do not install any scheduler until this drill succeeds.
- Emergency pre-bet safety slice is complete: production-playable packages
  fail closed on configured concentration/fixed-low-probability/material-
  outcome exposure checks, 4952 is rejected before upload, and morning
  preparation requires fresh playable 15/15 evidence. The earlier actionable
  schema-v3/T-10 contract remains historical compatibility; production
  schema-v5 now requires durable package archival plus post-archive/pre-marker
  T−10 checks before `.bet-ready`.
  Result synchronization, settlement, payout/ROI persistence, and a post-draw
  retry scheduler remain pending.
- Drawing-4952 launchd incident remediation is implemented: scheduler plan v2
  binds an absolute project root, wrapper/plist/subprocess working directories
  agree, preflight reuses absolute warmed preparation caches, and package
  phases retain isolated caches. A real cache-only preflight regression starts
  from `cwd=/` with HTTP prohibited. Existing installed launchd jobs are not
  modified automatically and require explicit artifact regeneration/install.
- Scheduler operational contracts are implemented but not installed:
  - scheduler-generated `run-drawing` argv carries the configured finite
    `--min-gross-ev` threshold;
  - generated wrappers may securely source a user-owned `0600` env file while
    plists remain secret-free and wrapper-only;
  - `sync-prepare --expected-drawing-number` prevents a stale still-open draw
    from being prepared for the next scheduled target;
  - a separate morning preanalysis wrapper/plist generator supports multiple
    times and retries beneath `reports/rehearsal` without betting markers.
- Systematic team-resolution Phase 2 is implemented:
  - context-aware reviewed team registry and backward-compatible migration;
  - conservative oriented candidate resolution with review-queue fallback;
  - atomic 15/15 drawing preparation and exact immutable pins;
  - progressive per-date schedule preparation with isolated failures;
  - scheduler preparation preflight and default pin-based final execution;
  - recent provider fixture/team/start revalidation without display-name
    rematching;
  - production-derived sport/country/competition/league context, including
    fail-closed competition-level conflicts and shared Russian/English/ISO
    country-identity normalization;
  - progressive preparation resolves after each successful date and stops at
    playable unique 15/15; unresolved attempts exhaust the configured horizon,
    while any attempted pre-readiness date failure publishes zero pins;
  - runner/manifest schema v4 authoritative 15/15 revalidation summaries and
    scheduler `.no-bet` enforcement before EV/actionable publication;
  - offline 4951 replay, prior-drawing regressions, unseen-team coverage, and
    scheduler-to-bet-ready/fail-closed acceptance.
  - official deterministic `run-drawing --offline-replay` path through real
    preparation, pins, cached 15/15 revalidation, runner, and manifest v4;
    strict cache hashes/identity, injected replay clock, research-only output,
    and scheduler-marker prohibition are covered by CLI acceptance tests.
  - replay safety hardening requires one isolated `--replay-root`, derives all
    mutable state beneath it, rejects live-root/symlink/output escape before
    writes, and makes scheduler replay ingestion marker-free `ignored` while
    retaining `.failed` for malformed live production manifests.
- The legacy name matcher remains compatibility-only through explicit direct
  opt-in. It is not a scheduler/final fallback and its global thresholds were
  not weakened.
- Drawing-4950 production-boundary update (no live bet):
  - 7/15 raw matching, reviewed-alias correction to 13/15, and strict reviewed-timing overrides are now documented for operational use.
  - Scheduler and runner output boundary remains strict fail-closed: only `bet-ready` at T-10 publishes an actionable package, while missing timing or catalog mismatches remain `no-bet`; terminal marker also includes `failed`.
  - Runner/reporting boundary now records `schema_version = 4`: v3
    raw/effective timing and budget provenance plus mandatory pinned schedule
    freshness/identity revalidation evidence.
  - Old `schema_version = 2` `drawing_4947` and `drawing_4950` reports remain historical and are excluded from current status.
  - Live platform install and first prospective live production run are pending.


- Automatic incremental TotoBrief morning synchronization is implemented:
  page-one status updates commit independently, exact detail synchronization
  is cache-aware/resumable, all normal request paths share cross-process
  pacing/retry state, and `sync-prepare --open` reaches systematic preparation
  without a duplicate detail request. The path now has strict page-one-only
  selection, server-authoritative Retry-After state, mandatory sidecar/torn
  cache rejection, exact 15-event validation, safe local roots, and a
  `--sync-only` diagnostic mode. Full historical `collect` remains the
  recovery/backfill path. Explicit finished-result refresh, package archive,
  immutable settlement, and bounded non-betting retry are implemented.
- Drawing 4950 early-run hardening is complete: immutable collection identity
  now includes request/cache/quota provenance, preventing retry passes with the
  same provider content from conflicting in storage. The early 7/15 coverage
  is explained by the API-Sports free-plan date window rejecting 2026-07-21;
  repeat the final collection after that date enters the provider window.
- The first scheduled run on drawing 4947 exposed an acceptance gap: the
  exact-only matcher could not bridge new Cyrillic names when both `start_at`
  and `name_en` were null, despite all 15 pairs existing in the provider
  schedule. Matcher v4 remediation and raw replay regressions for drawings
  4947 and 4945 are complete. Future matching releases require an unseen-team
  raw replay plus a prior-drawing false-positive regression; synthetic
  fail-closed tests alone are insufficient.
- Safe Drawing Runner implementation and corrective verification are complete:
  immediate protected preflight, exact target binding, T-20 final start, strict
  in-pass T-5 provider cutoff, audit/eligibility/EV orchestration, and
  transactional run artifacts without automatic bet placement. Independent
  whole-feature review is approved with no remaining findings.
- Safe Drawing Runner Task 3 orchestration is complete. The injected state
  machine rechecks the inclusive T-5 cutoff after each bound-phase progress
  notification, validates a terminal result before emitting `complete`, and
  keeps coverage `GO`/`PENDING`/`STOP` diagnostic-only.
- Safe Drawing Runner Task 4 deterministic reports are complete and
  review-hardened. Terminal results retain the actually observed final target
  fingerprint, including mismatch and unresolved-final states, and report-pair
  transactions precompute and exclusively create every temp/backup path before
  writes so interruptions cannot leak artifacts.
- Safe Drawing Runner Task 5 production Typer wiring is complete. `run-drawing`
  validates the approved configuration before API-Sports access, uses fresh
  pinned collection, exact timing, latest-30 diagnostic audit, existing EV and
  report writers, and publishes linked runner artifacts without automatic
  betting. Review hardening rejects page-one/drawing-info ID mismatches,
  detaches sanitized provider failures from secret-bearing exception graphs,
  and closes the owned CLI acceptance gaps.
- Safe Drawing Runner whole-feature review corrections are implemented,
  verified, and independently approved. Fake-clock and real
  CLI acceptance cover in-pass schedule/market/page/retry cutoff, second-fetch
  target mutation, post-complete/publication cutoff, computed-`NO BET` coupon
  suppression, all-artifact rollback, path aliases, unwritable roots, and
  publication TOCTOU. The 30-drawing/450-event coverage gate remains `PENDING`
  and external probabilities remain audit-only. Runner manifest schema v2 is
  still the first structured computed/suppressed `ev` contract; schema v1
  retains its historical `ev: null` representation when EV did not run.

- Task 1 complete: provider-neutral drawing eligibility classifier and
  deterministic target fingerprint, including immutable effective starts,
  Moscow calendar-span classification, and fail-closed invariants.
- Task 2 complete: deterministic per-date schedule collection/provenance,
  date-local failure isolation, quota-stop suppression of market requests,
  effective starts, and immutable eligibility-bound collection identity.
- Task 3 is complete: additive legacy-safe persistence, exact
  drawing/fingerprint eligibility lookup, and deterministic audit/report
  evidence with separate ordinary, expanded, multi-day, and unknown scopes.
  The existing overall coverage gate remains unchanged.
- Task 4 is complete: fresh collection now uses bounded base retries at a
  two-day horizon and an independent, cache-reusing expansion phase through
  day five only for stable null-start exact-pair misses.
- Task 5 is complete: playable EV output requires exact fresh-target timing
  eligibility with status `playable`; all other statuses produce a zero-cost
  `NO BET`. Research math and ranking remain unchanged.
- Task 6 is complete: deterministic acceptance covers ordinary two-day,
  day-five expansion, partial-date failure, confirmed multi-day, and unresolved
  drawings across collection, persistence, audit/report, and playable/research
  output. The multi-day eligibility feature is complete.
- Automatic T−10 publication scheduling of the fresh prospective command
- Open drawing analysis
- Package generation
- Report export
- Reproducible backtests

## Full-history remediation

- [x] Handle an early open drawing whose TotoBrief pool is still `0/0/0`
  without importing invalid detail: retain exact identity, retry on a bounded
  schedule, and activate the ordinary evening scheduler only after normal
  preparation becomes ready.

- [x] `TOTO-REVIEWED-EVIDENCE-DATE-SCOPED-POLICY-V1`: evaluate provider
  completeness per event UTC date, ignore unrelated expansion-date failures,
  preserve strict fail-closed controls, and verify drawing 4961 on an isolated
  database copy.

- [x] `TOTO-DATA-HEALTH-CONTRACT-V1`: versioned read-only contract, strict
  CLI, per-use-case eligibility, machine reason codes, selectors, exports, and
  minimal generation/backtest gates.
- [x] P0.2: lifecycle-aware collector freshness. A transition to `finished`,
  incomplete terminal results, or invalid `0/0/0` input must trigger explicit
  reconciliation rather than be treated as current.
- [x] P0.3/P0.4: RAW-first immutable archive plus full-detail finished
  importer.
- [x] Offline repair command and copy-database verification for fields provably recoverable from existing canonical
  RAW.
- [x] Bounded, rate-limited resumable reconciliation engine and dry-run CLI.
- [x] Controlled network canary on a database copy for 4946/4955/4956/4958.
- [x] Persistent source-incomplete cooldown/quarantine required by the canary.
- [x] `TOTO-RECONCILE-DRY-RUN-READONLY-FIX-V1`: physical read-only SQLite
  dry-runs, missing-state-table compatibility, and write-free canonical RAW
  preview.
- [x] Small backed-up production reconciliation batch for
  4946/4955/4956/4958 with exactly four first-pass requests and zero-request
  idempotency pass.
- [ ] Continue the controlled
  historical backlog.
- [ ] Install/schedule nightly listing/detail/result reconciliation and health report only after canary acceptance.
- [x] Complete package/package-free settlement scheduling and mandatory
  post-draw review-request lifecycle. Actionable package settlement continues
  to use the same archive and result evidence boundary.

Do not build another optimizer before the measurable lifecycle
`drawing -> package -> archive -> results/VOID -> settlement -> review` is
closed.

- [x] Expose every final computed package, including `NO BET`, through a
  validated `PAPER / DO NOT WAGER` report and read-only display command.
- [x] Schedule post-draw result checks for 12:00 Moscow next day with
  three-hour retries; create a durable user review request after 15/15 terminal
  outcomes and settlement.
- [x] Generate immutable package postmortems covering event exposure, actual
  outcomes/VOID, BK/pool/Pin/sports probabilities, category hits and payout
  status.
- [ ] Audit free sports-data source coverage on Toto competitions and freeze
  source provenance before expanding sports features.
- [ ] Implement leakage-safe Elo, venue, form, goals, rest, table and
  congestion features with explicit per-event BK fallback.
- [ ] Train and walk-forward evaluate a regularized sports residual adjustment
  around BK; compare BK, Pin, calibrated BK, venue shadow and ensemble.
- [ ] Run every candidate through unchanged dynamic-bank package selection and
  finished settlement before any activation review.

- [x] Add provider-neutral reusable schedule evidence ledger and strict
  identity/time resolver; integrate it into morning preparation.
- [x] Wire the canonical schedule-evidence ledger through real
  `morning-dispatch`, preserve it in passive retries, and allow only atomic
  baseline-only-to-reviewed schedule enrichment for an unchanged drawing.
- [x] Install generated identity-bound passive retry plans automatically when
  `morning-dispatch --activate` defers, and keep hard-stop-day hourly retries
  running after the fixed 12:00 morning pass.
- [x] Add automatic independent public-source discovery with immutable raw
  snapshots and candidate/conflict/missing reports; never mutate the ledger.
- [ ] Add authoritative competition/team source adapters and reviewed
  promotion so official-plus-independent observations can be completed without
  manual discovery while preserving the existing evidence gate.
  - [x] UEFA v5 plus independent Sofascore exact-consensus adapter, immutable
    snapshots/review evidence, idempotent ledger promotion and automatic
    deferred-morning integration.
  - [ ] Add equivalent authoritative adapters for non-UEFA competitions only
    where a stable official source and exact identity contract are available.
- [x] Make repeated preparation preserve already validated schedule-evidence
  pins when API-Sports cannot serve their kickoff UTC date; verify the live
  4973 READY/PLAYABLE re-run and install its schema-v6 evening scheduler.
- [x] Propagate revalidated reviewed/schedule-evidence kickoff times through
  final collection, persistence and eligibility; exercise the real 4973
  atomic-final path to 166 coupons / 4,980 / `STRUCTURAL_PASS`.
- [x] Give the T-20 primary final the complete runtime through T-10 minus the
  publication reserve instead of truncating it at T-16; preserve the T-30 LKG
  fallback without reducing package-search quality.
- [x] Fix the drawing-4973 T-45 deterministic timeout: the warmup child now
  starts at T-45 instead of waiting for the T-30 fallback boundary while its
  parent deadline expires.
- [x] Fix the drawing-4974 T-45 command/parser contract: command generation and
  strict manifest validation now share the canonical phase-to-lead mapping;
  automatic recovery refresh/final/T-10 runs completed with terminal `NO BET`.
- [x] Fix drawing-4973 `safety_reselection_infeasible`: scheduler fallback
  phases now provide the immutable snapshot, ledger and scheduler-plan
  artifacts required by quality-v2 provenance instead of hash-only metadata.
- [x] Resolve the drawing-4973 runner-manifest schema mismatch: artifact-bound
  warmup/refresh now emit schema v5, and scheduler fallback ingestion accepts
  that current schema. Keep legacy schema v4 rejected.
- [x] Profile and repair the 506-second package runtime without reducing search
  quality, samples, candidates, or bank. Exact swap-delta vectorization reduced
  the identical 4973 cProfile run from 444.8 to 260.0 seconds and preserved the
  selected-package hash.
- [x] Verify DNS resilience after restoring warmup/refresh LKG: bounded
  final/retry failures retain the validated 166-coupon package before T-10 with
  degraded provenance and no automatic wager marker.
- [x] Remove the manual emergency-plan hash omission path; recovery now clones
  the exact original scheduler-plan inputs and reviewed evidence binding.
- [x] Raise the measured final-runtime admission floor to 300 seconds and
  recheck it after final-input capture. Scheduler-bound manual runs cannot
  start heavy work after the safe latest-start boundary.
- [x] Prove publication/output suppression at and after every actionable and
  hard T-10 boundary, including a completed package arriving too late.
- [x] Apply current non-conflicting authoritative evidence for 4965 events 5,
  10 and 12 through the reusable ledger; retain event-13 material as an audit
  record only because its official home/away identity is not established.
- [ ] Resolve 4965 events 7 and 13 only from non-conflicting authoritative
  evidence; until then keep the drawing fail-closed at 13/15.

- [x] `TOTO-4965-PARTIAL-ENRICHMENT`: permit explicit per-event baseline-only
  preparation when all 15 TotoBrief BK/pool rows are valid, while retaining
  fail-closed identity/probability conflicts and full mixed-source provenance.
  Production 4965 reached READY 15/15 (13 external; baseline-only 7/13) but was
  correctly deadline-deferred with no package or bet.

- [x] `TOTOAI-FIX-4971-PACKAGE-QUALITY-20260810`: continuous probability-aware
  exposure floors, concentration headroom, deterministic Hamming diversity,
  explicit package P(9+/13+/14+/15) objective, provenance-bound diagnostics,
  frozen 4967/4969/4970 plus prospective 4971 comparison, and paper-only
  release gate.
- [x] Close quality-v2 independent-review blockers: top-level `NO BET` plus
  `STRUCTURAL_PASS`, true P13+/P14+/P15/P9+/diversity/robust-EV lexicographic
  comparison, domain-separated MC streams, artifact-backed schema-v6
  provenance, complete configuration binding, dynamic 4,980/9,960/alternate
  bank tests, and a full bank-4,980 four-sensitivity runtime budget.
- [x] Refresh only the quality-v2 golden hash/payout/hit/probability fields for
  4967/4969/4970 from separate actual frozen-node outputs. Old and safety-v1
  historical assertions remain unchanged; 4971 is covered by the separate
  frozen-package postmortem and its quality-v2 coupon strings are unavailable.
- [x] Split quality-v2 verification into a practical default/release suite and
  retained opt-in/nightly `heavy` research suite. Fast golden-contract tests
  verify refreshed artifacts without recomputing `3**15` surfaces.
- [ ] Predeclare prospective holdout size, calibration/category/diversity/
  exposure thresholds, and stopping rules before collecting release evidence.
- [ ] Keep quality-v2 paper-only until that prospective gate is independently
  met; three retrospective drawings and one unfinished prospective drawing are
  insufficient for any profitability or real-money claim.
- [x] Harden the model/direct-report boundary against manually injected
  `PLAY`, and bind the complete canonical selection context through selector
  provenance, schema-v6 SchedulerPlan, diagnostics, and runner manifests.
- [x] Close the lower-level EV report bypass by sharing the paper-only EV-run
  sanitizer with direct CSV/Markdown export and retaining only clearly labelled
  training/paper coupon diagnostics.
# 2026-08-13 immediate implementation: The Odds API shadow audit

- [x] Approve provider role, quota boundary, matching semantics, and activation
  prohibition in the sports analytics specification.
- [x] Record the implementation sequence in
  `docs/superpowers/plans/2026-08-13-the-odds-api-shadow-audit.md`.
- [x] Implement fail-closed provider parsing and secret-safe transport.
- [x] Persist provider-neutral provenance and quota evidence.
- [x] Add the current-drawing `NOT_ACTIVATED` shadow command and reports.
- [x] Run one current-drawing live probe with the protected key: drawing 4975,
  4/15 matched, 3 credits spent, 497 remaining, zero secret leakage.
- [x] Add the uninstalled, idempotent morning/control/T-10 checkpoint command
  and provider-scoped audit; no production scheduler hook was added.
- [ ] Collect 30 consecutive completed drawings / 450 events prospectively.
- [ ] Add post-settlement log-loss/Brier/calibration and unchanged-package
  replay once settled checkpoint evidence exists.

# 2026-08-25 operational deadline correction

- [x] Add a hash-bound conservative cutoff that can only tighten TotoBrief
  `ended_at` to an independently collected earlier kickoff.
- [x] Separate scheduler identity time from operational time in schema v7 and
  anchor T-120 through T-10 plus passive retry hard stops to the latter.
- [x] Make morning source collection persist and immediately apply a tighter
  retry cutoff before LaunchAgent installation; reuse it on later runs.
- [x] Verify drawing 4987 without activation or package generation:
  `ended_at=18:45Z`, operational cutoff `15:45Z`, T-10 `15:35Z`.
- [ ] Decide, through reviewed provider policy, whether two-source exact
  timing consensus may become canonical event timing. Until then the cutoff is
  scheduling safety only and does not promote candidate rows.
- [x] Run the first live 4987 morning control collection, persist the tighter
  cutoff, promote two exact UEFA/Sofascore consensus observations, and install
  the identity-bound passive retry job for the remaining 13 events.
- [x] Give valid `deferred` dispatches a dedicated terminal wrapper path so one
  scheduled invocation cannot repeat full source collection and waste quota.
- [x] Make schedule-evidence lookup tolerate individual unsupported-script
  source aliases without weakening exact matching or crashing the ledger.
