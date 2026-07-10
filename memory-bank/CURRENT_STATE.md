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

- Tests currently passed: 82
- Ruff passed

## Exact Cover Example

- 144 full brief variants
- 8 coupons
- Category 13
- 100% exact verified coverage
- Worst minimum Hamming distance 2

## Latest Completed Task

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

## Previous Completed Task

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

Run baseline evaluation on real collected data for 100/500/1000 completed
drawings and compare budgets/categories.

Required backtest metrics:
- Actual result fully inside brief
- Number of uncovered actual outcomes
- Best coupon hits
- Hit rates for 13, 14, 15
- Package size
- Package cost
- Brief full variant count
- Category guarantee verification
- Results by budget and category
