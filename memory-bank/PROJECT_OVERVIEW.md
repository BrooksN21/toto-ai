# Project Overview

TotoAI is a BaltBet toto analysis and package-generation system.

The project goal is to collect TotoBrief data, analyze historical BaltBet
drawings, build probability-aware briefs, generate coupon packages under a
budget, and verify/backtest those packages.

Core principles:
- Budget is user-defined, not fixed.
- BaltBet coupon stake defaults to 30 RUB but must remain configurable.
- The main goal is not guaranteed profit.
- The optimization target is probability and expected value under budget.
- TotoBrief is the primary source for pool distribution, bookmaker estimates,
  draw history, results, and payouts.
- External odds and statistics sources may be added later.

Project memory isolation:
- This memory bank belongs only to the TotoAI repository.
- Do not mix it with local skills, personal knowledge bases, team knowledge
  bases, or chat-only memory.
