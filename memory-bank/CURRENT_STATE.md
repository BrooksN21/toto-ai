# Current State

This file is the project-local state note for TotoAI only. Do not mix it with
local skills, personal knowledge bases, team knowledge bases, or unrelated
memory stores.

## Current Important Commits

- `f771bbe` Initial TotoBrief API client and CLI
- `bdcf776` Add historical data collector
- `d368704` Add historical research analytics
- `c962613` Add API inspector
- `4112362` Improve inspect-api with drawing number support
- `8ceda4b` Fix playable drawing selection
- `68cabb9` Add Cover Engine
- `0f92ee5` Add exact Cover Package verifier
- `7e95f24` Add baseline brief generator
- `8b3ed6d` Add persistent project memory bank

Note: the current PR branch was rebased onto an empty remote base for the first
GitHub pull request, so local branch commit hashes may differ from the original
task commits listed above.

## Verification

- Tests currently passed: 204
- Ruff passed

## Active Design: Hybrid Direct Package Experiment

Approved design:
- Preserve an exact top-probability core of 50%, 75%, or 90% of the package.
- Fill remaining capacity by marginal weighted coverage after accounting for
  scenarios already covered by the core.
- Evaluate only the 350 frozen development drawings in five chronological
  folds; never reopen the old holdout for selection.
- Return GO only for at least two additional 13+ hits, non-loss in at least
  four folds, no lower average best hits, and zero operational failures.
- Return STOP and end optimizer tuning when no candidate passes.

Design specification:
- `docs/superpowers/specs/2026-07-13-hybrid-direct-package-experiment-design.md`

Implementation plan:
- `docs/superpowers/plans/2026-07-13-hybrid-direct-package-experiment.md`
- Five TDD tasks: selector, decision model, fail-closed evaluator, atomic
  reports/CLI, and the frozen development GO/STOP run.

## Latest Completed Task: Development Strategy Diagnostics

Added the fail-closed `diagnose-strategies` command and completed the frozen
development-only diagnostic for the Direct Package Optimizer experiment.
The command opens the existing SQLite database in enforced read-only mode and
cannot create tables or run migrations.

Command:
- `python -m toto_ai.cli diagnose-strategies --db data/toto.db --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv`

Run evidence:
- 350 development drawings processed; the 150 holdout drawings were excluded.
- All regenerated package hashes and recomputed frozen result fields matched.
- Bank 5000 RUB, stake 30 RUB, category 13.
- Weighted vs top best hits: 260 wins, 74 ties, 16 losses.
- Weighted minus top best hits: mean +1.394, median +1.
- Paired 13+ transitions: neither 343, both 3, top-only 3,
  weighted-only 1.
- Average best hits: baseline 8.380, top 8.691, weighted 10.086.
- Observed 13+ frequency: baseline 0.286%, top 1.714%, weighted 1.143%.
- Top vs weighted mean pairwise Hamming distance: 3.491 vs 7.496.
- Top vs weighted mean coupon log probability: -13.682 vs -14.729.
- Average top/weighted package intersection: 11.36 coupons; average Jaccard
  overlap 0.0356.

Interpretation:
- Weighted coverage usually improves the nearest coupon, but its much broader
  and lower-probability package does not improve the observed 13+ threshold.
- No strategy was selected. These are development-only diagnostic findings,
  not holdout evidence and not evidence of profitability.
- The next optimizer experiment should test a development-selected hybrid that
  preserves a high-probability core or probability floor while adding measured
  diversity. It must use a new untouched evaluation window.

Reports:
- `reports/strategy_diagnostics_development_last_500_bank_5000.csv`
- `reports/strategy_diagnostics_development_last_500_bank_5000.md`

Important commits:
- `ec97679` Add development strategy diagnostics command

## Previous Completed Task: Package Structure Metrics

Added deterministic package diagnostics for coupon log-probability summaries,
pairwise Hamming diversity, package intersection, Jaccard overlap, and mean
log probability of coupons unique to each package. Empty unique coupon sets
are represented as unavailable (`None`).

## Latest Completed Task: Direct Package Optimizer Experiment

Implemented the approved Direct Package Optimizer and its reproducible
evaluation protocol.

Important commits:
- `e5c4823` Add coupon probability utilities
- `c760515` Add deterministic coupon candidates
- `fd71046` Add weighted direct package optimizer
- `c82b135` Add comparable package strategies
- `4cc8987` Add direct strategy backtest
- `baefa34` Add paired strategy evaluation reports
- `e5b4953` Add frozen direct package experiment
- `5beaeae` Ignore generated strategy experiment reports

Frozen retrospective experiment:
- Code version: `5beaeae4d7801748e82a4ae9a0003be4e0796d81`
- Manifest: `reports/strategy_experiment_manifest_last_500_exclude_10.json`
- 500 eligible drawings, 350 development and 150 holdout
- Latest 10 previously exposed drawings excluded
- Bank 5000 RUB, stake 30 RUB, category 13, seed 42
- 500/500 drawings evaluated; no skips, generation errors, invalid packages,
  or timeouts

Holdout results:
- `baseline_brief`: hit13 2, hit14 1, hit15 0, average best hits 8.59,
  average cost 663 RUB
- `top_probability`: hit13 6, hit14 1, hit15 0, average best hits 8.86,
  average cost 4980 RUB
- `weighted_coverage`: hit13 5, hit14 0, hit15 0, average best hits 10.23,
  average cost 4980 RUB
- Paired weighted-vs-baseline hit13 difference: +2.00 percentage points
- 95% paired bootstrap interval: [-0.6667, 5.3333]
- Status: preliminary; the interval includes zero

Interpretation:
- Direct strategies outperform the low-cost baseline on raw holdout hit13
  counts, but superiority is not statistically established.
- `top_probability` currently has the highest holdout hit13 count.
- `weighted_coverage` has substantially higher average best hits, but that
  improvement has not yet converted into more 13+ hits.
- This is a retrospective benchmark, not independent prospective evidence and
  not evidence of profitability.

## Exact Cover Example

- 144 full brief variants
- 8 coupons
- Category 13
- 100% exact verified coverage
- Worst minimum Hamming distance 2

## Previous Completed Task

Fixed unsafe Budget Oracle pruning.

- Disabled dominance pruning because it changed oracle best-hit metrics.
- Disabled pruning based on full-cover coupon-cost bounds because Budget Oracle
  evaluates useful partial packages under budget.
- Restricted incumbent pruning to candidates whose maximum possible hit count
  is strictly below the incumbent's actual hit count.
- Added regression coverage comparing optimized and exhaustive selection.
- Removed the unused unsafe pruning helpers.

Local smoke result on `data/toto.db`:
- `budget-oracle --last 3 --bank 10000 --stake 30 --category 13 --no-progress --profile-workload`
  found 15 hits for all three processed drawings.
- All pruning counters were zero; two drawings reached the configured timeout,
  so these rows are partial oracle evidence rather than exhaustive optima.

## Previous Completed Task

Profiled Budget Oracle candidate workload.

The `budget-oracle` command now supports:
- `--profile-workload` to print aggregate candidate workload diagnostics.
- Per-drawing generated candidate count.
- Per-drawing unique candidate count.
- Cover Engine call count.
- Cache hit/miss counts, where duplicate candidate briefs avoided by
  deduplication are counted as hits and actual Cover Engine evaluations are
  counted as misses.
- Average and maximum brief variant counts.
- Average Cover Engine call duration.
- Slowest 10 candidate briefs across the run.

This does not change oracle search logic, candidate scoring, or default search
space.

## Previous Completed Task

Optimized Cover Engine performance without changing mathematical results.

The Cover Engine now:
- Caches expanded brief variants.
- Caches coverage bitsets by `(brief, category)`.
- Builds coverage via bounded outcome mutation instead of rebuilding all
  coupon/variant Hamming comparisons.
- Uses integer bitsets for greedy uncovered coverage tracking.
- Keeps the same selected coupons, coverage rate, worst minimum distance, and
  guarantee result on the representative regression case.

Benchmark evidence:
- Pre-optimization representative cover runtime: about 1.70s for 1024 variants.
- Post-optimization representative cover runtime: about 0.04-0.05s.
- Speedup: about 35x on the representative benchmark.
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13 --no-progress`
  completed in about 0.5 seconds without `--max-candidates`.

New command:
- `python -m toto_ai.cli benchmark-cover`

## Previous Completed Task

Improved Budget-Constrained Brief Oracle observability and diagnostics.

The `budget-oracle` command now supports:
- Rich progress updates with drawing number, drawing index, candidate index,
  elapsed time, average drawing time, ETA, current best hits/cost, and
  processed/skipped/timed-out counts.
- `--timeout-per-drawing` to keep the best candidate found so far and mark the
  row as timed out.
- `--max-candidates` as an explicit optional candidate limit. Omitted means full
  search.
- `--progress/--no-progress`.
- Partial CSV writes every 10 drawings.
- Per-drawing profiling timings for candidate generation, cover generation,
  verification, and total time.
- Final timing summary.

Local smoke result on `data/toto.db`:
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13 --max-candidates 3 --no-progress`
  completed in about 5 seconds.

## Earlier Completed Task: Budget-Constrained Brief Oracle

Implemented Budget-Constrained Brief Oracle.

The `budget-oracle` command uses actual results only as an oracle benchmark. It
searches BK-ranked candidate briefs that include the actual outcome, runs the
Cover Engine under the same budget/stake/category constraints, and compares the
best oracle package hits against the baseline brief generator.

Command:
- `python -m toto_ai.cli budget-oracle --db data/toto.db --last 500 --bank 10000 --stake 30 --category 13`

Exports:
- `reports/budget_oracle_last_<N>.csv`
- `reports/budget_oracle_last_<N>.md`

Metrics:
- Oracle average best hits
- Oracle hit13/hit14/hit15
- Average singles, doubles, triples
- Average oracle package size and cost
- Baseline generator average best hits
- Oracle vs baseline gap

Local smoke result on `data/toto.db`:
- `budget-oracle --last 1 --bank 10000 --stake 30 --category 13` completed in
  about 9 seconds.

## Earlier Completed Task: Project Knowledge Base

Created the persistent project knowledge base.

New repository-local project knowledge areas:
- `memory-bank/`: current state, roadmap, architecture, philosophy, decisions.
- `knowledge/`: concise domain notes for TotoBrief, bookmaker calibration,
  crowd bias, closing line, and Pinnacle integration status.
- `skills/`: project-local workflow checklists for algorithm review, research,
  and backtesting.
- `prompts/`: reusable project prompt templates for feature, research, and
  backtest tasks.

The project rule is now explicit: after every completed feature, update the
project knowledge base first.

## Earlier Completed Task: Brief Oracle Research

Implemented Brief Oracle Research.

The `brief-oracle` command finds the smallest oracle brief that contains the
actual 15-outcome result for completed drawings using BK probabilities only.

Exports:
- `reports/brief_oracle.csv`
- `reports/brief_oracle.md`
- `reports/brief_oracle_by_event.csv`

Per drawing it records:
- singles, doubles, triples
- full brief variant count
- log brief probability
- actual result string
- oracle brief string
- BK rank counts for actual outcomes
- average BK rank and actual-result BK probability
- pool/BK top disagreement diagnostics

Aggregate metrics include:
- average singles, doubles, triples
- p25/p50/p75/p90 full variant counts
- doubles and triples distributions
- BK rank frequency for actual outcomes
- entropy by required cover size

## Earlier Completed Task

Implemented bookmaker calibration research.

The `calibration` command measures:
- Bookmaker reliability by 5 percentage-point bins for outcomes 1/X/2
- Pool reliability by the same bins
- Overall Brier score
- Log loss
- Expected Calibration Error
- Pool vs bookmaker bias
- Draw calibration
- Favorite calibration for BK >= 60%
- Underdog calibration for BK <= 25%

Exports:
- `reports/calibration.md`
- `reports/calibration.csv`
- `reports/reliability.csv`

## Earlier Completed Task: Backtest Optimization

Optimized the Baseline Brief Generator backtest.

The `backtest-brief` command now includes:
- Rich progress for drawing number, candidate index, elapsed time, and best
  score.
- Cover Engine cache keyed by brief tuple, category, and max coupon count.
- Candidate brief deduplication.
- Cheap candidate scoring before exact cover.
- Exact cover/verifier only for top candidates.
- Per-drawing timeout fallback.
- Per-drawing timing metrics.
- `--top-candidates`, `--max-candidate-briefs`, and
  `--timeout-per-drawing` options.

Exports:
- `reports/backtest_brief_last_<N>.csv`
- `reports/backtest_brief_last_<N>.md`

Local smoke results on `data/toto.db`:
- `backtest-brief --last 1 --bank 10000 --stake 30 --category 13` completed
  in about 4.7 seconds.
- `backtest-brief --last 10 --bank 10000 --stake 30 --category 13` showed
  progress and completed in about 41 seconds, testing 9 drawings with one
  skipped due to missing pre-match BK/pool probabilities.

## Next Task

Implement the approved Hybrid Direct Package experiment from
`docs/superpowers/specs/2026-07-13-hybrid-direct-package-experiment-design.md`.
Evaluate only the 350 frozen development drawings. Do not inspect the old
holdout while selecting a core fraction.
