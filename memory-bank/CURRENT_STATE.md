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

Note: the current PR branch was rebased onto an empty remote base for the first
GitHub pull request, so local branch commit hashes may differ from the original
task commits listed above.

## Verification

- Tests currently passed: 68
- Ruff passed

## Exact Cover Example

- 144 full brief variants
- 8 coupons
- Category 13
- 100% exact verified coverage
- Worst minimum Hamming distance 2

## Next Task

Implement a backtest specifically for the Baseline Brief Generator, not the old
placeholder MVP.

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
