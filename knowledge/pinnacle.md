# Pinnacle and External Odds

Pinnacle is not integrated in the current repository. Direct API access is not
assumed, and scraping or bypassing access restrictions is out of scope.

Current relevant code:
- `study-bk` compares TotoBrief `bk_*` probabilities with `norm_*` odds-derived
  probabilities.
- `calibration` evaluates how stored bookmaker probabilities match results.

The current external-source candidate is a lawful third-party market feed,
starting with an API-Sports feasibility experiment for football and hockey.
The Odds API is another candidate but its documented competition coverage maps
poorly to the historical BaltBet mix.

External data must be integrated through a provider-neutral event-level
interface. A high-confidence external match may replace or blend with TotoBrief
BK probabilities; a missing or low-confidence match falls back to TotoBrief BK
for that event. It must never silently remove the whole drawing.

Odds must be stored prospectively because third-party historical windows may be
short. Every report records source, timestamp, match confidence, and fallback
reason.

Systematic matcher v3 keeps reusable identity knowledge conservative. Its
small code-owned team and domestic-competition alias families are exact after
deterministic normalization and scoped by stable country identity; they never
contain drawing positions or fixture IDs. A translated league label can help
authorize a match only when the candidate is uniquely same-oriented, both team
identities are strong, country agrees, and the normal date window passes.
Ambiguous, reversed, wrong-country, out-of-window, and truly missing fixtures
continue to use explicit fallback rather than a synthetic match.

Related:
- [closing_line.md](closing_line.md)
- [bookmaker_calibration.md](bookmaker_calibration.md)
- [expected_value.md](expected_value.md)
- [../memory-bank/ROADMAP.md](../memory-bank/ROADMAP.md)
