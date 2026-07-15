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

Fresh playable EV path:

```text
TotoBrief API page one
-> Nearest future active/expected drawing
-> Immediate drawing-info snapshot
-> Strict 15-event BK/pool input
-> Reusable exact EV components
-> Prize-factor surfaces and dynamic-bank selection
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
- `toto_ai.collector.sync`: historical drawing collector.
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
- `toto_ai.external_odds.domain` and `toto_ai.external_odds.targets`:
  provider-neutral immutable external-odds records, strict TotoBrief
  drawing-target parsing with explicit nullable event start times, explicit
  sport classification, and preserved
  TotoBrief BK fallback probabilities for the API-Sports coverage audit.
- `toto_ai.external_odds.consensus`: strict football full-time and hockey
  regulation-time three-way market validation, duplicate bookmaker rejection,
  per-book de-vig, median consensus, and explicit minimum-bookmaker fallback.
- `toto_ai.external_odds.collection` and `toto_ai.external_odds.storage`:
  deterministic 15-event prospective external-odds collection, explicit
  event-level TotoBrief BK fallback, provider quota/request/cache provenance,
  and append-only SQLAlchemy persistence for immutable collection snapshots.
  Matcher v3 records whether the unique exact provider pair has the same or
  reversed home/away orientation. Reversed matches swap only the consensus
  `1`/`2` probabilities into TotoBrief orientation; raw provider prices remain
  unchanged. Orientation is part of collection identity, storage, and reports.
  Collection run `fetched_at` is the external observation time and is at least
  as late as every consumed provider market fetch timestamp; the fresh
  TotoBrief drawing-info timestamp is stored separately as `target_fetched_at`.
  Event dispositions persist matched schedule payload hash/fetch time and the
  complete matching decision. Quote rows persist market payload hash/fetch
  time and canonical source provenance. Exact duplicate bookmaker/market keys
  are consensus-ineligible and coalesced into one deterministic anomaly row so
  the mandated database uniqueness constraint does not discard the collection.
  Quote order is canonical before identity, comparison, insertion, and load.
- `toto_ai.external_odds.prospective`: fresh-by-default multi-pass collection.
  It resolves one TotoBrief target, creates one isolated cache session, and
  reuses that session across new provider clients after minute-quota resets.
  Only quota, provider schedule, and provider odds failures trigger another
  pass. Every pass remains an immutable stored 15-disposition snapshot.
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
  CLI output, recursive exception chains, and reports.
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
- `ev-package --open`: resolve and fetch a fresh playable TotoBrief drawing,
  compute exact modeled EV, select a Research or Playable package, and publish
  atomic reports. Unsupported Playable runs return `NO BET`.
- `backtest-ev`: evaluate dynamic banks, prize factors, and gross-EV thresholds
  chronologically while requiring and excluding a frozen strategy holdout.
- `collect-external-odds --open`: collect fresh prospective API-Sports odds for
  one pinned playable drawing, automatically retry approved operational
  fallbacks, and store every 15-disposition pass. `--reuse-cache` explicitly
  enables the old shared-cache diagnostic path.
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
