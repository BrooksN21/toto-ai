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
-> Backtest Engine
-> Future Research/ML
-> Package Export
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
- `toto_ai.optimizer.hybrid_evaluation`: fixed five-fold hybrid development
  evaluation rows, aggregate fold metrics, and deterministic GO/STOP selection
  for the approved core fractions; evaluation running, reports, and CLI wiring
  are added separately.
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
- `build-brief --open`: build a baseline brief and package for the next playable
  drawing.
- `backtest-brief`: backtest the baseline brief generator on finished drawings.
- `freeze-strategy-experiment`: freeze exact drawing IDs, protocol/data hashes,
  and code version before a direct-strategy evaluation.
- `backtest-strategies`: compare package strategies on a frozen chronological
  development/holdout experiment.
- `diagnose-strategies`: regenerate and verify frozen packages, then diagnose
  strategy structure and paired 13+ transitions on development drawings only.
