# Architecture

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
-> Scheduler T-10 publication only when the final package remains valid
```

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
  `toto_ai.runner.scheduler`, `toto_ai.runner.models`:
  schema v4 runner manifests, raw/effective timing boundary, mandatory exact
  15/15 pinned schedule freshness/identity summary, strict parsing, immutable
  run-scoped artifacts, and deadline-driven scheduler phases
  (`T-45`, `T-30`, `T-15`, `T-10`) with terminal markers
  (`.bet-ready`, `.no-bet`, `.failed`).
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
  LaunchAgent files for the fixed phase boundaries (`T-45`, `T-30`, `T-15`,
  `T-10`). The plan's gross-EV threshold is passed through the exact
  `run-drawing --min-gross-ev` CLI contract. Optional `--env-file` produces a
  wrapper that validates and sources a user-owned regular non-symlink file
  whose mode is no broader than `0600`; the plist contains only the wrapper
  path and no credentials.
- `morning-preanalysis-plan`: generate, but never install, a separate launchd
  candidate beneath `reports/rehearsal`. Its wrapper uses the same secure env
  contract and runs only guarded `sync-prepare --open
  --expected-drawing-number N` at configured morning times with bounded
  retries. It writes isolated logs and never invokes the betting scheduler or
  creates betting markers.
- `scheduler-execute`: execute preflight/fallback/final/freeze phases from a
  signed schedule, strictly parse runner manifests, and only publish an
  actionable package when freeze publishes `.bet-ready`.
