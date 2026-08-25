# Free schedule-provider audit — 2026-08-25

## Answer

No single free provider can honestly guarantee that every arbitrary BaltBet
event will always be present and that access will never be suspended. Published
provider terms explicitly reserve missing coverage, quota enforcement and
account suspension for abuse. TotoAI must therefore use documented APIs behind
a provider-neutral resolver and fail closed when evidence is still incomplete.

## Best candidate for a controlled test

**GOAL API** is the strongest new football candidate found:

- free plan: 1,000 requests/day, no card;
- 1,019 listed competitions and 184 countries;
- exact public coverage catalogue, including Russia Second League B and the
  Saudi League;
- documented fixture endpoint, bearer-key authentication, quota headers and
  429 behavior;
- terms state that data is licensed from third-party providers and permit API
  use within plan limits.

It is not yet approved for production. The service and its current terms are
new (July 2026), coverage is explicitly not guaranteed, and a registered
account can still be suspended for rate-limit abuse. It must first pass a
prospective coverage and stability bake-off.

Official references:

- <https://goal-api.com/coverage>
- <https://goal-api.com/documentation>
- <https://goal-api.com/what-is-goal-api>
- <https://goal-api.com/terms>

## Other candidates

### SportsDataAPI

Its pricing page advertises a permanent free plan with 100 requests/day,
10/minute, all sports/endpoints/competitions and no card. Its football product
page separately describes free coverage as major European and international
competitions. This contradiction prevents approval without an exact live
coverage test. It is the second bake-off candidate, not a trusted fallback.

- <https://sportsdataapi.com/pricing>
- <https://sportsdataapi.com/sports-api/football>
- <https://sportsdataapi.com/sports-api/football/documentation>

### TheSportsDB

Keep only as a keyless secondary source. It reached 12/15 on drawing 4986, but
the official free v1 documentation restricts `searchteams.php` to an Arsenal
example and free bulk endpoints are truncated. Therefore the previously
considered generic team-ID plus upcoming-events fallback is not viable on the
documented free tier. The provider is also crowdsourced and incomplete.

- <https://www.thesportsdb.com/docs_api_guide>

### Sofascore

Do not make it a required production dependency. Sofascore states that it does
not provide its sports data through a public API because of provider
agreements. The currently reachable web endpoint is therefore unsupported and
may change or be blocked.

- <https://sofascore.helpscoutdocs.com/article/129-sports-data-api-availability>

### The Odds API

Its free current-events endpoint is documented and quota-free, but the
published league catalogue omits many lower and regional competitions that
appear in BaltBet coupons. It remains useful for odds/shadow evidence, not as a
universal schedule resolver.

- <https://the-odds-api.com/sports-odds-data/sports-apis.html>
- <https://the-odds-api.com/liveapi/guides/v4/>

### Rejected approaches

- 1xBet parsers and consumer-site reverse engineering: unofficial scraping,
  unstable schemas and material blocking/account risk.
- football-data.org free tier: documented and stable but too few competitions.
- Sportmonks free tier: only selected leagues.
- BetsAPI: paid, not a free source.
- KickoffAPI: broad marketing coverage, but its public documentation exposes
  API-Sports media/IDs and says some data is proxied from API-Sports. It does
  not provide the independent resilience required here.

## Acceptance bake-off before integration

Do not connect a candidate to the scheduler merely because registration works.
For GOAL API first, and SportsDataAPI only if needed:

1. freeze the exact targets for at least 10 consecutive mixed BaltBet drawings;
2. collect only through documented API endpoints and within reported quotas;
3. measure exact home/away identity, kickoff, status and competition coverage;
4. require 15/15 on every tested drawing for primary-source qualification;
5. repeat collection at morning, control and final checkpoints;
6. record 401/403/429/5xx behavior and quota headers without exposing the key;
7. keep the provider candidate-only and non-promoting during the bake-off;
8. retain TheSportsDB and official competition sources as independent
   fallbacks; unresolved events remain fail-closed.

Passing this bake-off demonstrates observed coverage, not a perpetual
guarantee. Provider health, quota and per-competition coverage must continue to
be monitored on every drawing.

## Recommendation

Register one free **GOAL API** project key and test it on recent/current Toto
drawings before writing a production adapter. Do not create replacement
accounts to bypass the suspended API-Sports account, and do not integrate an
unofficial bookmaker parser. If GOAL API fails the exact bake-off, test
SportsDataAPI next. The final operational design remains multi-source; no
single free account is a safe universal dependency.
