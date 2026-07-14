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

- Tests currently passed: 497
- Ruff passed

## Approved Next Design: Expected-Value Package Engine

The sealed BK-only hybrid experiment is final with `STOP`. The next direction
does not continue tuning hit-count heuristics. It ranks the complete
`3^15 = 14,348,907` coupon space by modeled monetary expected value.

Approved requirements:

- dynamic bank: any positive multiple of the configurable stake;
- no candidate truncation for speed;
- official cumulative BaltBet category allocation model;
- explicit prize-fund proxy/override and sensitivity reporting;
- explicit independent crowd-ticket model from pool marginals;
- Research mode that always shows top coupons;
- Playable mode with configurable EV threshold and honest `NO BET`;
- no automatic threshold reduction to force bank utilization;
- provider-neutral external probabilities with event-level TotoBrief BK
  fallback; direct Pinnacle scraping is excluded;
- modeled ROI is not profitability evidence without prospective payout data.

Design specification:
- `docs/superpowers/specs/2026-07-14-expected-value-package-engine-design.md`

Approved implementation plan:
- `docs/superpowers/plans/2026-07-14-expected-value-package-engine.md`
- Seven TDD tasks: domain/prize math, brute-force oracle, exact ternary engine,
  dynamic-bank selection, fresh drawing CLI/reports, chronological modeled-EV
  backtest, and full-space acceptance.

Next action:
- execute the implementation plan task by task with independent review gates.

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
  reports/CLI, and the frozen development GO/STOP run. Tasks 1-5 are complete.

## Latest Review Fix: Hybrid Development Seal

Added `seal-hybrid-development` to derive a development-only CSV and augmented
manifest from the frozen manifest, the bounded development prefix of the full
backtest CSV, and a read-only SQLite database. The deterministic seal stores
separate SHA-256 hashes for canonical development CSV rows, pre-drawing inputs,
development results, and the fixed hybrid protocol. The seal also records the
clean Git code version. Input/output path collisions are rejected before any
source is loaded, and the manifest/CSV pair is published with rollback-safe
same-directory temporary files.

`evaluate-hybrid` now requires these sealed artifacts. It rejects missing or
mismatched CSV, protocol, and pre-drawing input hashes before result access,
rejects any non-development CSV drawing ID, accumulates result hashes only
after each drawing's top package hash passes, and verifies the final result hash
before summary, decision, or report return. Strategy definitions, fractions,
folds, bank, stake, category, and GO/STOP criteria are unchanged.

The shared package-generation deadline is now checked after every major stage,
including top enumeration, candidate generation, both scenario samples, hybrid
selection, and validation coverage. A timed-out selector returns without a
post-deadline exact coverage pass. Deadline overruns therefore fail closed
instead of being reported as successful zero-timeout drawings.

Both sealing and evaluation reject resolved input/output path collisions before
loading inputs or opening the database, so generated seal/report artifacts
cannot replace a manifest, development CSV, or database.

## Latest Completed Task: Sealed Frozen Hybrid Development Experiment

The approved hybrid direct-package experiment completed on all 350 frozen
development drawings without accessing the 150-drawing holdout during
selection. The final run used the development-only data/code seal at Git
revision `530e1021328bb8436671a273e9ab96b4be03ac06`.

Protocol:
- Bank 5000 RUB, stake 30 RUB, category 13.
- Five chronological development folds of 70 drawings each.
- Compared `top_probability` with hybrid top-core fractions 0.50, 0.75, and
  0.90.
- All four strategies produced 166-coupon packages costing 4980 RUB.
- Operational failures and timeouts: 0.

Development results:
- `top_probability`: 13+ 6, 14+ 1, 15 0, average best hits 8.691429.
- `hybrid_0.50`: 13+ 4, 14+ 1, 15 0, average best hits 9.491429.
- `hybrid_0.75`: 13+ 5, 14+ 1, 15 0, average best hits 9.288571.
- `hybrid_0.90`: 13+ 6, 14+ 1, 15 0, average best hits 9.060000.

Per-fold 13+ counts in strategy order `top_probability`, `hybrid_0.50`,
`hybrid_0.75`, `hybrid_0.90`:
- Fold 1: 0, 0, 0, 0.
- Fold 2: 0, 0, 0, 0.
- Fold 3: 1, 0, 0, 1.
- Fold 4: 1, 1, 1, 1.
- Fold 5: 4, 3, 4, 4.

GO predicates by hybrid core fraction:
- 0.50: additional 13+ -2, non-losing folds 3, average best-hit delta
  +0.800000, operational failures 0; fail.
- 0.75: additional 13+ -1, non-losing folds 4, average best-hit delta
  +0.597143, operational failures 0; fail.
- 0.90: additional 13+ 0, non-losing folds 5, average best-hit delta
  +0.368571, operational failures 0; fail.

Final decision: `STOP`.

No hybrid fraction met every pre-registered GO predicate. All hybrids improved
average best hits, but none produced the required two additional 13+ hits over
`top_probability`. Direct optimizer tuning is closed under the current
BK-only protocol. The old holdout remains excluded and unopened for hybrid
selection. This development-only result is not profitability evidence.

The final sealed rerun completed in approximately 25 minutes and exactly
reproduced the original strategy hit counts, fold counts, average best-hit
metrics, and STOP decision. It processed 1400 evaluation rows with zero
timeouts, exactly 350 development IDs, and zero holdout-ID overlap. This
result remains evidence for the sealed evaluator revision above; subsequent
documentation-only commits do not alter or rerun the experiment.

Reports:
- `reports/hybrid_evaluation_development_last_500_bank_5000.csv`
- `reports/hybrid_evaluation_development_last_500_bank_5000.md`
- `reports/hybrid_development_manifest_last_500.json`
- `reports/hybrid_development_rows_last_500.csv`

The CSV was independently checked: 1400 rows, 350 rows per strategy, and 280
rows per fold.

## Completed Task: Hybrid Evaluation Reports and CLI

Added `write_hybrid_evaluation_reports()` and the fixed `evaluate-hybrid`
command for the approved hybrid experiment. CSV rows use manifest drawing order
and the stable strategy order `top_probability`, `hybrid_0.50`,
`hybrid_0.75`, and `hybrid_0.90`. CSV and Markdown are fully rendered in
same-directory temporary files and closed before either final report is
replaced. Existing final reports are copied to same-directory backups before
publication. If either final replacement fails, both previous reports are
restored byte-for-byte, or both newly published reports are removed when no
previous pair existed; all temporary and backup files are then removed.

The Markdown report records the frozen configuration, five development folds,
total and structural metrics, operational failures, every GO predicate, and
the exact GO/STOP decision. It explicitly labels the result development-only
and as no profitability evidence. Generated reports are ignored by Git.

`evaluate-hybrid` accepts only the database, manifest, frozen backtest CSV, and
report directory paths. It uses `open_readonly_db()` and Rich progress, does
not initialize or migrate the database, and converts controlled failures to
`typer.BadParameter`, including `SQLAlchemyError` database failures.

No evaluation run has been interpreted as profitability evidence. The frozen
holdout remains excluded from hybrid selection.

The worktree CLI help shows only the four path options. Current test and Ruff
verification is recorded once above.

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

## Completed Task: Hybrid Package Selector

Added `select_hybrid_package()` for the approved direct-package experiment.
It keeps an exact, unique top-probability core sized with `ceil`, fills only
core-uncovered sampled scenarios through the existing weighted selector, and
uses a deterministic unique probability fallback when time remains. Timeout
paths return only work completed so far. Existing top-probability and weighted
coverage behavior remains unchanged.

Verification at completion: pytest and Ruff passed.

Review follow-up: the hybrid probability fallback now checks the deadline before
each coupon log-probability ranking computation, after sorting, and while
appending. On expiry it returns the unique partial package with `timed_out=True`.
Verification at completion: pytest and Ruff passed.

## Completed Task: Hybrid Fold Metrics and GO/STOP Decision Model

Added the pure `hybrid_evaluation` model for the approved hybrid experiment.
It defines immutable evaluation rows/results, assigns exactly five contiguous
chronological folds, aggregates stable top and hybrid fold metrics, and applies
the fixed GO predicate and deterministic fraction ranking. A STOP selects no
core fraction. This task does not load the database, generate reports, or add
CLI behavior.

Review follow-up: `summarize_hybrid_evaluation()` now fail-closes before
aggregation on invalid folds, duplicate or unpaired rows, unequal or empty
folds, non-chronological fold assignments, and mismatched strategy fractions.
Verification at completion: pytest and Ruff passed.

## Completed Task: Fail-Closed Hybrid Development Evaluator

Added `run_hybrid_evaluation()` for the approved fixed-protocol hybrid
experiment. It validates the 5000 RUB / 30 RUB / category 13 configuration and
five equal development folds before database access, then evaluates only the
manifest development IDs. Per drawing it regenerates and validates the exact
top package plus all three hybrids, reuses candidate and scenario inputs across
fractions, verifies the frozen top hash before loading a result, recomputes the
frozen top fields, and produces four scored rows for the GO/STOP model.

The evaluator fails closed on duplicate/non-divisible development manifests,
protocol mismatches, malformed/incomplete/over-budget/timed-out packages,
frozen hash/result mismatches, and invalid package strategy identities. It does
not add reports or CLI wiring, and never loads the frozen holdout during
selection.

Review follow-up: integrity-boundary coverage now tags every development drawing,
captures real result-bearing Event SQL, and proves a later top-hash mismatch
stops before that drawing's result load or any holdout access.

Verification at completion: focused and full pytest suites plus Ruff passed.

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

## Latest Completed Task: Expected-Value Domain Math

Task 1 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev` package exposes immutable `EVConfig`, `EVInput`, `EVComponents`,
`EVSurface`, `RankedCoupon`, and `EVPackage` models, plus bank validation,
official cumulative category-fund allocation, triplet normalization, and
Jeffreys-smoothed crowd marginals. `EVConfig` validates positive integer banks
and stakes, including divisibility, during construction; its
`max_coupons` result is always an integer without forcing full bank
utilization. `EVComponents` and `EVSurface` defensively copy and freeze their
NumPy arrays. The exported `CROWD_JOINT_MODEL` contract is
`independent_event_marginals`: later joint coupon probabilities are modeled as
products of the smoothed event marginals.

## Latest Task 1 Fix Wave: Hardened EV Immutability

The second Task 1 fix wave enforces the same positive-integer stake contract in
`smooth_crowd_matrix()` as `validate_bank()`, including rejection of booleans,
floats, zero, and negative values. `EVInput` now deep-normalizes probability
matrices and probability sources to tuples and rejects probability rows that do
not contain three outcomes. `EVPackage` deep-normalizes coupons and derived
brief values to tuples. EV arrays are defensive copies exposed through owned
immutable byte buffers, so their shapes and dtypes are preserved and callers
cannot re-enable writes with `setflags(write=True)`.

Verification for this fix wave: focused EV tests `48 passed`, full pytest
`336 passed`, focused Ruff passed, and full Ruff passed. NumPy remains
intentionally undeclared in `pyproject.toml` until Task 3.

## Latest Completed Task: Independent Brute-Force EV Oracle

Task 2 of the Expected-Value Package Engine is complete. The reference oracle
enumerates actual results and coupons with `itertools.product(range(3),
repeat=event_count)`, preserving deterministic C-order base-three indexing.
It exposes independent joint distributions, Hamming hit counts, crowd
qualifying stakes, coupon payouts, and exhaustive gross EV for event counts up
to eight. Zero-valued outcome probabilities are accepted when the modeled
category denominators remain finite and positive; invalid category denominators
fail closed before payout division.

Verification: focused reference tests `11 passed`; full pytest `347 passed`;
focused Ruff passed; full Ruff passed.

## Latest Task 2 Review Fix: Hardened Reference Validation

The brute-force EV reference now requires every probability row to contain
exactly three finite non-negative values whose sum is one within
`rtol=1e-12` and `atol=1e-12`, while preserving valid zero probabilities.
`coupon_payout()` validates category ranges against the event hit count,
non-negative finite category funds, positive finite qualifying stakes for
every funded category, and strict positive integer stakes. Brute-force EV
rejects out-of-range categories before enumeration, and all public integer
contracts reject booleans.

Verification: focused reference tests `36 passed`; full pytest `372 passed`;
focused Ruff passed; full Ruff passed.

## Latest Completed Task: Exact Ternary Full-Space EV Engine

Task 3 of the Expected-Value Package Engine is complete. Flat arrays and coupon
strings preserve C-order base-three indexing with outcome order `1`, `X`, `2`.
The exact engine builds product probability arrays with repeated Kronecker
products. It computes each crowd qualifying probability over every actual-result
state with a chunked independent-marginal Poisson-binomial DP, then processes
the coupon-side Hamming-ball category sequentially through ternary FFT
convolution. Category denominators must remain finite and positive, and an
interruption propagates without returning a partial EV surface.

`compute_ev_components(EVInput, progress_callback=None)` uses only the official
9..15 regular-prize and jackpot coefficients and returns separate immutable
unit arrays so prize sensitivity can reuse the heavy calculation.
`materialize_ev_surface()` performs the light regular-prize/jackpot scaling.
For small-space oracle work, the explicit convenience signature is
`compute_ev_surface(true_probabilities, crowd_probabilities, pool_sum,
category_funds_by_hits, stake, minimum_category, progress_callback=None)`;
this preserves arbitrary category-fund mappings rather than weakening oracle
equivalence.

The deterministic `benchmark-ev` command records elapsed time, peak resident
memory when available, probability masses, minimum denominator, exact error,
fixed sample diagnostics, and normalized SHA-256 array hashes. Event counts up
to eight compare the complete surface to the independent brute-force oracle;
larger spaces independently verify sampled crowd tails with scalar
Poisson-binomial arithmetic and fixed coupon EVs with direct vectorized hit
comparisons over every actual-result state. Official benchmark expectations are
literal and do not share the production category-fund map. Array hashes are
diagnostic fingerprints only and do not affect PASS/FAIL.

Verification: focused Task 3 tests `35 passed`; full pytest `407 passed`; focused
and full Ruff passed. The five-event CLI benchmark verified all 243 coupons
against the oracle with maximum absolute error `1.897e-19` and status `PASS`.
The mandatory 15-event acceptance benchmark remains deferred to Task 7 and was
not run for Task 3.

## Latest Task 3 Mathematical Review Fix

Removed the absolute FFT cutoff that could erase legitimate positive values.
`ternary_convolve()` now copies the real inverse result away from its complex
buffer, preserves every positive value, clips only negative values within a
scale-aware roundoff tolerance, and raises on material negative output.

Crowd category denominators no longer use FFT recovery. For each category, a
bounded-memory Poisson-binomial DP evaluates `P(matches >= k | actual result)`
for all `3^n` actual-result states without state truncation. Regressions cover
all-positive five-event full spaces and a selected 15-event state with
`(0.999998, 0.000001, 0.000001)` marginals; the latter remains positive at
approximately `1e-90` without allocating the full 15-event state space.

The larger-space benchmark verifier no longer reuses production denominators,
Hamming kernels, or coupon convolution. It compares sampled production tails
to a scalar independent recurrence and recomputes sampled coupon components by
direct vectorized hit comparisons over every actual-result state in chunks.

Verification for this fix: focused Task 3 tests `45 passed`; full pytest
`417 passed`; focused and full Ruff passed. `benchmark-ev --events 5 --samples
10` verified all 243 coupons against the brute-force oracle in `0.116300 s`,
with `62.84 MiB` peak resident memory, minimum denominator `1828.14404892`,
maximum EV error `1.626e-19`, zero sampled crowd-tail error, and status `PASS`.
The full 15-event benchmark was not run, as instructed; its runtime and peak
memory remain Task 7 acceptance concerns.

## Final Task 3 Formula Fix: Exact Crowd Mass Handling

The production accumulation now materializes both C-order Kronecker product
arrays `Q` and `R`. It validates finite unit mass from `R.sum()` within `1e-12`,
records that value as `crowd_mass`, and releases `R` before category work. The
Poisson-binomial denominator DP remains the only denominator path and does not
consume or truncate `R` states.

For tolerance-accepted rows that are not bit-exact unit mass, production and
both independent benchmark recurrences now compute non-match probability from
the supplied row (`row_sum - selected match`) rather than `1 - selected
match`. This preserves the accepted row mass and agrees with the independent
brute-force joint reference. Regressions cover production tails, scalar tails,
direct coupon sums, full EV surfaces, C-order `R` auditing/release, and existing
tiny-positive behavior.

Verification: focused Task 3 tests `48 passed`; full pytest `420 passed`.
The five-event benchmark (`243` coupons) passed in `0.121526 s` with `62.00
MiB` peak resident memory, maximum EV error `1.626e-19`, and zero sampled
crowd-tail error. The 15-event benchmark was not run.

## Latest Completed Task: Dynamic-Bank EV Package Selection

Task 4 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.package` module ranks every validated `3**event_count` EV value
with a complete deterministic NumPy order: descending gross EV, then ascending
base-three coupon index for values tied under `rtol=1e-12` and `atol=1e-15`.
It does not truncate candidates or create a Python object per coupon; only the
selected package rows become `RankedCoupon` values.

Research mode fills the dynamic bank capacity even where gross EV is below one
and labels the result `RESEARCH ONLY`. Playable mode selects only coupons at or
above its configured threshold, can leave bank unused, and returns `NO BET`
with zero cost when none qualify. Packages report cost, unused bank, expected
payout, modeled ROI, and an outcome-union brief in `1`, `X`, `2` order.
Modeled ROI remains a model output, not evidence of profitability.

Verification: focused package tests `19 passed`; full pytest `439 passed`;
focused and repository-wide Ruff passed. Playable threshold tests cover
0.90/0.95/1.00/1.05 with monotonic selected-count assertions.

## Task 4 Review Hardening: Full-Surface Ranking

The full-surface ranker now handles every accepted real numeric dtype without
negating unsigned arrays. It creates one complete ascending index order with
NumPy quicksort, reverses that order in bounded chunks, and then scans adjacent
EV values in fixed-size chunks. Only actual tolerance-tie candidate blocks are
processed; common no-tie surfaces do not enter Python once per coupon. Each
candidate block is split by the specified run-first `rtol=1e-12`,
`atol=1e-15` rule and its tie runs are sorted in place by base-three index.

Regressions cover unsigned zero ordering, non-transitive adjacent-close chains,
candidate blocks crossing scan chunks, no singleton candidate processing, and
complete-order `RankedCoupon.rank` values when threshold filtering skips an
earlier tolerance-tied coupon.

Verification: focused package tests `24 passed`; full pytest `444 passed`;
repository-wide Ruff passed. Synthetic no-tie `uint32` and all-tie `uint8`
surfaces both ranked all `3**15 = 14,348,907` indices exactly. The combined
process completed in `1.00 s`; `/usr/bin/time -l` reported a `229,786,488`-byte
peak memory footprint and `433,176,576`-byte maximum resident set size while
running both surfaces sequentially.

## Latest Completed Task: Fresh Drawing EV Package Command

Task 5 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.drawing` path resolves only page one of the live TotoBrief API,
chooses the nearest future `active`/`expected` drawing by `(ended_at, id)`, and
immediately fetches `drawing-info`. It never falls back to SQLite. The fresh
receipt timestamp is recorded in UTC.

Drawing parsing requires exactly event orders 0 through 14, normalizes every BK
triplet, applies the approved Jeffreys smoothing to every pool triplet, and
fails closed on missing or invalid pool, jackpot, quote, and possible-winnings
inputs. Possible winnings are either an explicit override with the default
factor or the disclosed `pool_sum * prize_fund_factor` proxy. Event results are
not consumed.

`build_open_ev_package()` computes the complete reusable category components
once, materializes and selects the 0.70/0.80/0.90/1.00 sensitivity surfaces,
and reuses the configured factor's package where applicable. No probability or
coupon candidate space is truncated. Package cost divided by `pool_sum` is the
self-dilution ratio: exactly 1% remains supported; above 1% is unsupported.
Unsupported Playable output suppresses `PLAY` to `NO BET`, while Research output
retains diagnostics and an explicit warning.

The new rollback-safe report publisher fully renders deterministic exact-package
CSV and Markdown artifacts before publication and restores both prior files if
the second final replacement fails. Reports disclose fresh timestamps, sources,
the independent-event crowd model, prize factor, bank and self-dilution ratios,
decision, package metrics, derived brief, top-20 diagnostics, sensitivity, and
that modeled ROI is not observed ROI.

`ev-package` requires `--open`, accepts the exact planned mode, bank, stake,
threshold, prize-factor, possible-winnings, and jackpot options, and uses Rich
phase/category progress. API, validation, numerical, interruption, and report
failures become controlled `BadParameter` errors. An interrupted calculation
prints no `PLAY` decision.

Verification before documentation: focused Task 5/API-inspector tests `34
passed`; full pytest `468 passed`; CLI help listed all eight planned options;
repository-wide Ruff passed.

## Task 5 Review Hardening

Unsupported Playable runs are now fully non-actionable. When the proposed
package exceeds the 1% self-dilution limit, the returned package is `NO BET`
with no coupons, zero cost and expected payout, the full bank unused, no
modeled ROI, and an empty derived brief. Sensitivity rows apply the same
suppression, and the exact package CSV contains only its header. Research mode
still retains diagnostic coupons and the unsupported warning. The exact 1%
boundary remains supported.

Atomic report publication now rolls back after any `BaseException`, including
`KeyboardInterrupt` and `SystemExit`, once publication has started. The
original exception is re-raised after both prior artifacts are restored and
temporary/backup files are cleaned.

Fresh `drawing-info` payload IDs must exactly match the requested drawing ID
before EV components are computed. Oversized numeric conversion failures are
normalized to `ValueError`, CLI overflow failures become controlled
`BadParameter` output, and parser receipt timestamps must include an explicit
timezone. Reports now disclose whether jackpot came from the TotoBrief payload
or an explicit override.

Sensitivity factors are materialized and selected sequentially. The workflow
retains only scalar sensitivity summaries and the requested main
surface/package; instrumentation observes at most the main surface plus one
transient sensitivity surface. Main package selection and bounded top-20
diagnostics share one complete deterministic ranking. Every `3**15` EV value
is still ranked for selection; no probability or coupon candidate truncation
was introduced.

Review-fix verification before documentation: focused EV/API-inspector tests
`66 passed`; full pytest `476 passed`; CLI help listed all planned options;
repository-wide Ruff passed.

## Latest Completed Task: Chronological Modeled-EV Backtest

Task 6 of the Expected-Value Package Engine is complete. The new
`toto_ai.ev.backtest` module exposes immutable config, row, summary, and result
types. It validates dynamic stake-multiple banks, finite unique thresholds and
prize factors, and validated frozen holdout IDs from the existing strategy
manifest loader.

Finished drawing candidates are selected from `Drawing` rows with holdout IDs
excluded in SQL before any event or quote query. Historical EV inputs query
only ordered event identifiers and BK/pool quote columns; actual result columns
are loaded only after all factor/bank/threshold packages and deterministic
SHA-256 hashes for that drawing are complete. Inputs require exactly orders
0..14, valid normalized BK rows, Jeffreys-smoothed pool rows, positive pool
sum, and non-negative jackpot.

Each drawing builds one reusable exact component set. Every prize-fund factor
materializes and ranks one complete surface, then reuses that ranking across
all banks and thresholds without candidate limits or timeouts. Selection is
monotonic by threshold, respects exact bank caps, leaves unused bank, and emits
honest zero-cost `NO BET` rows. Realized output records best hits and cumulative
9..15 indicators.

Completed drawings are atomically checkpointed to a diagnostic partial CSV
bound to the exact normalized run configuration, requested window, community,
and forbidden IDs. Resume accepts only complete drawing groups and does not
turn interrupted work into report rows. Final reports include modeled expected
payout/ROI, bank utilization, hit rates, skip rate, and the over-80% model
review alert. They state that expected crowd denominators are modeled and that
modeled payout/ROI are not observed bookmaker payout/ROI.

`backtest-ev` requires `--frozen-manifest`, resolves forbidden IDs before
opening the read-only database, parses comma-separated banks and thresholds
deterministically, and shows drawing/category progress with ETA.

Verification: focused backtest/report tests `27 passed`; full pytest `497
passed`; worktree-local CLI help listed all six options and marked the manifest
required; repository-wide Ruff passed. No historical EV run was interpreted as
profitability evidence, and the old frozen holdout was not used for development
or evaluation.

## Next Task

Run Task 7 end-to-end mathematical and operational acceptance, including the
mandatory full 15-event benchmark. External probability collection and event
matching remain a separate later design.
