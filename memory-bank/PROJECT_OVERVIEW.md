# Project Overview

TotoAI is a BaltBet toto analysis and package-generation system.

The project goal is to collect TotoBrief data, analyze historical BaltBet
drawings, build probability-aware briefs, generate coupon packages under a
budget, and verify/backtest those packages.

Core principles:
- Budget is user-defined, not fixed.
- BaltBet coupon stake defaults to 30 RUB but must remain configurable.
- Profitability is not proven and must never be presented as guaranteed.
- The optimization target is probability and expected value under budget.
- TotoBrief is the primary source for pool distribution, bookmaker estimates,
  draw history, results, and payouts.
- External sports data is integrated for identity, schedule, eligibility,
  immutable audit snapshots, and a shadow probability/evaluation path. It is
  not a production prediction input.
- The current outcome matrix is exclusively normalized TotoBrief BK. TotoBrief
  pool probabilities model crowd behavior for EV calculations.
- API-Sports form, goals, and standings snapshots can produce an experimental
  `NOT_ACTIVATED` sports-shadow artifact and candidate blend. The experimental
  estimate is venue-only (home-team home W-D-L and away-team away W-D-L);
  missing venue evidence falls back to BK without aggregate substitution.
  Production EV and package generation remain exclusively on normalized
  TotoBrief BK.
- The shadow provider/evaluator and CLI are implemented with per-event BK
  fallback and strict provenance validation. Injuries, lineups, xG, and Elo
  are not implemented.
- The next prediction milestone is prospective collection and chronological
  OOS evidence on at least 30 drawings / 450 events. Production activation is
  prohibited unless the declared improvement and safety gates pass.

Project memory isolation:
- This memory bank belongs only to the TotoAI repository.
- Do not mix it with local skills, personal knowledge bases, team knowledge
  bases, or chat-only memory.
