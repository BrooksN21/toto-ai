# Free schedule fallback assessment — 2026-08-24

Task: `TOTO-FREE-SCHEDULE-FALLBACK-20260824`

## Executive recommendation

1. **Primary free source: TheSportsDB v1**, using the documented event-search API, immutable raw snapshots, provider event/team IDs, and a persistent team-alias registry.
2. **Backup free source: football-data.org v4**, after registering a free project key. It is narrower, but has a documented API contract, predictable throttling, and strong top-league data.
3. **Do not put Sofascore or ESPN web JSON into production automation without explicit permission.** Both had useful observed coverage, but their published terms restrict automated extraction. A publicly reachable JSON response is not the same as an authorized public API.
4. **BetsAPI is not a free fallback.** It is a paid independent aggregator, and no BetsAPI/B365API credential was detectable under the common `.env` names checked.
5. **The current mandatory `official + independent` promotion rule must change** if TotoAI is expected to fill heterogeneous domestic schedules automatically. Recommended replacement:
   - one immutable **official organizer** claim may promote by itself;
   - two agreeing, documented and legally usable **independent APIs** may promote;
   - one independent claim requires explicit operator review;
   - undocumented or contract-restricted web endpoints may never auto-promote.

There is no free, documented, legally usable single source that demonstrated 15/15 coverage for drawing 4985. The recommended pair gives a lawful base, but perpetual gaps can only be avoided with provider-neutral collection, a two-independent-source ledger lane, and an explicit review path for the remaining niche fixtures.

## Scope and method

I read `AGENTS.md`, all files in `memory-bank/` and `knowledge/`, the existing schedule adapters, the relevant scheduler/preparation paths, and current local artifacts for drawing 4985. I made only read-only public API probes. No source files, tests, dependencies, commits, or remotes were changed.

The assessment separates three questions that should not be conflated:

- **coverage** — does the source contain the fixture at all;
- **identity quality** — home/away orientation, provider IDs, canonical names, competition and UTC kickoff;
- **ledger eligibility** — whether TotoAI may legally and operationally use the source for automatic promotion.

Observed coverage is a dated canary, not a promise of future coverage.

## Current project state

### Credential presence

Only presence booleans were checked; no value was printed or persisted.

| Environment name | Present with a non-empty value |
|---|---:|
| `API_SPORTS_KEY` | yes |
| `THE_ODDS_API_KEY` | yes |
| `BETSAPI_KEY`, `BETS_API_KEY`, `BETSAPI_TOKEN`, `BETS_API_TOKEN` | no |
| `B365API_KEY`, `B365API_TOKEN`, `B365_API_KEY`, `B365_API_TOKEN` | no |
| `FOOTBALL_DATA_API_KEY`, `FOOTBALL_DATA_KEY` | no |
| `THESPORTSDB_API_KEY`, `SPORTSDB_API_KEY` | no |
| `ESPN_API_KEY` | no |

TheSportsDB publishes a shared free v1 key in its documentation, so no private project credential is required. Despite the prior expectation that a BetsAPI key had been added, it is not detectable under the common BetsAPI/B365API names above in the current `.env`.

### Existing adapter architecture

- `src/toto_ai/external_odds/schedule_source_collector.py` already collects immutable **Sofascore candidate** snapshots. It does not mutate the ledger.
- `src/toto_ai/external_odds/schedule_consensus.py` can promote exact UEFA-v5 + independently refetched Sofascore agreement.
- `src/toto_ai/external_odds/schedule_sources.py` defines reusable schedule-claim structures and reviewed-catalog revalidation, but there are no TheSportsDB, football-data.org, BetsAPI, or ESPN adapters.
- Scheduler, preparation, cache/pin, CLI, and environment validation paths still contain substantial `api-sports` assumptions. Adding a transport adapter alone would not create a working fallback; the preparation and pin/revalidation path must become provider-neutral.

The existing immutable snapshot and exact-orientation model is a good foundation. The main missing pieces are legal source selection, provider-neutral orchestration, and durable team identity aliases.

## Drawing 4985 coverage canary

Drawing 4985 (internal 12062) had 15 fixtures and no source kickoffs in the TotoBrief payload. The deadline was `2026-08-24T19:30:00Z`. API-Sports returned an account-suspended semantic response for the immediate window and free-plan date-window errors later, leaving all 15 events with unknown timing.

Read-only probes used dates 2026-08-24 and 2026-08-25. `yes` means the exact home/away pair was observed. The football-data.org column is eligibility from its published free-competition list because no project token is present.

| # | Fixture | TheSportsDB search | ESPN public feed | Existing Sofascore collector | football-data.org free |
|---:|---|:---:|:---:|:---:|:---:|
| 1 | Fulham — Chelsea | yes | yes | no | yes |
| 2 | Málaga — Deportivo La Coruña | no | yes | yes | conditional: Toto says La Liga |
| 3 | Celta B — Andorra FC | no | yes | no | no |
| 4 | Granada — Mallorca | yes | yes | yes | no: Toto says La Liga 2 |
| 5 | Bologna — Lazio | yes | yes | no | yes |
| 6 | Baltika — Rubin | yes | yes | no | no |
| 7 | Veles — Arsenal Tula | yes | no | no | no |
| 8 | Lanús — Argentinos Juniors | yes | yes | yes | no |
| 9 | Talleres Córdoba — Rosario Central | yes | yes | no | no |
| 10 | Güemes — Atlético de Rafaela | yes | yes | no | no |
| 11 | Botafogo RJ — Athletico Paranaense | yes | yes | yes | yes |
| 12 | Athletic Club — Grêmio Novorizontino | no | yes | yes | no |
| 13 | Oțelul — FC Argeș | yes | no | no | no |
| 14 | Kocaelispor — Amedspor | no | yes | no | no |
| 15 | Malmö — Djurgården | yes | yes | no | no |
|  | **Observed/eligible total** | **11/15** | **13/15** | **5/15** | **3 definite, 1 conditional** |

Important qualifications:

- TheSportsDB's free all-events-for-day endpoint returned only three records per date, as documented. It happened to expose only 2/15 targets. Drawing-driven event searches plus canonical accent/name variants found 11/15.
- TheSportsDB searches needed names such as `Lanús`, `Talleres de Córdoba`, `Baltika Kaliningrad`, and `Güemes`. This proves that a provider-ID/alias registry is required; repeated fuzzy guessing at deadline is not robust.
- The current Sofascore result is coverage of TotoAI's search-and-match path, not necessarily of Sofascore's underlying database.
- Toto competition labels are sometimes inconsistent with the actual teams. Pair orientation and stable team IDs must outrank the free-text competition label during matching, while a competition conflict remains reviewable evidence.
- On fixtures seen by more than one probed source, observed UTC kickoffs agreed to the minute. This is encouraging but does not override access terms.

## Source-by-source assessment

### 1. TheSportsDB — recommended primary

**Access and limits.** The [official API guide](https://www.thesportsdb.com/docs_api_guide) documents a free v1 key, 30 requests/minute, event/team/league IDs, event search, lookup, and schedule endpoints. Free `eventsday` returns at most three events; free event search returns one result. V2 is paid and is the only version receiving forward development.

**Fields.** Suitable fields include `idEvent`, `idHomeTeam`, `idAwayTeam`, home/away names, league ID/name, `strTimestamp`, local date/time fields, postponement, and status. This is enough for immutable schedule claims and provider-specific identity binding.

**Legal/public use.** The [terms](https://www.thesportsdb.com/docs_terms_of_use.php) explicitly allow API content to be copied/modified when official endpoints are used and disallow website scraping. Free use is intended for development projects; an app-store publication requires a paid subscription. TotoAI's current private pet-project use fits much better than scraping a consumer score site.

**Provenance.** Independent, community-maintained database; not an official competition organizer. It must never be labeled official.

**Stability.** Medium. The contract is documented and v1 is more than ten years old, but it is legacy, result caps are tight, and community data can be incomplete or corrected after the fact.

**Implementation effort.** Medium, roughly 2–4 engineering days including adapter, snapshots, throttling, alias registry, provider-neutral pinning, and focused verification. A naive date-list adapter is insufficient. The collector should issue one exact drawing-driven search per target, use pre-learned provider aliases, cache results, and spend at most one controlled retry per event within the 30/minute budget.

### 2. football-data.org — recommended backup

**Access and limits.** The [free plan](https://www.football-data.org/pricing) is €0, provides fixtures/schedules for 12 competitions, and permits 10 requests/minute. The [API policy](https://docs.football-data.org/general/v4/policies.html) documents throttling and UTC behavior. Registration and an API key are required for match data; no project key is currently present.

**Coverage.** The [free coverage list](https://www.football-data.org/coverage) includes the English Premier League, Spanish La Liga, Italian Serie A, and Brazilian Série A, but not the lower Spanish, Russian, Argentine, Brazilian Série B, Romanian, Turkish, or Swedish competitions in 4985. This gives 3 unambiguous matches and possibly Málaga–Deportivo if the Toto La Liga label is correct.

**Fields.** Stable match/team/competition IDs, `utcDate`, status, and explicit home/away teams are sufficient for schedule claims. The free plan says schedules are delayed, so late fixture changes need a second source or review.

**Legal/public use.** The [published terms](https://www.football-data.org/about) authorize registered API use subject to fair use, credential secrecy, and visible attribution. Free use is non-commercial. This is a clear API contract, unlike consumer-site JSON endpoints.

**Provenance.** Independent aggregator, not official.

**Stability and effort.** Medium-high interface stability but no availability SLA, and narrow free coverage. Adapter effort is low-to-medium, roughly 1–2 engineering days after registration, plus the shared provider-neutral scheduler work.

### 3. BetsAPI — broad but paid and not currently configured

The [BetsAPI introduction](https://betsapi.com/docs/) explicitly describes a paid service. Current [pricing](https://betsapi.com/mm/pricing_table) lists the Soccer Events API at $30/month and 3,600 requests/hour; low-cost trials are paid and time-limited. Its [upcoming-events endpoint](https://betsapi.com/docs/events/upcoming.html) provides UTC epoch kickoff and league/team filters, and its [event search](https://betsapi.com/docs/events/search.html) accepts home, away, and date.

Coverage is likely broad because the Events API is aggregated from Bet365 and other sources, but 4985 coverage was not tested: no detectable token is present and a paid trial is not a sustainable free fallback. It is an independent commercial aggregator, not an official source. Technically it would be a medium-effort adapter and a sensible paid escape hatch if the owner later chooses that budget, but it should not be the answer to this task.

### 4. Sofascore — useful evidence, ineligible for unattended production

The existing adapter produced 5/15 exact candidates. Events expose useful IDs, team orientation, tournament metadata, timestamps, and status, and the current code already snapshots them.

However, Sofascore does not publish the consumed endpoints as a supported developer API with rate limits or SLA. Its [terms](https://www.sofascore.com/en-us/terms-and-conditions) say the data comes from independent, internal, and official sources, is not guaranteed accurate, and restrict automated requests, extraction, aggregation, and scraping without consent. Therefore Sofascore is independent and **not ledger-eligible for automated production under the published terms**. Existing use should remain research-only or be disabled unless explicit permission is obtained.

### 5. ESPN public league feeds — excellent canary coverage, ineligible without permission

The public scoreboard JSON exposed 13/15 fixtures with stable event/team IDs, explicit `homeAway`, competition metadata, and UTC dates. It missed only Veles–Arsenal Tula and Oțelul–FC Argeș in the league paths tested.

There is no current public, self-service ESPN schedule API contract or published rate limit for these site endpoints. ESPN's support page points to the general Disney terms, whose [license restrictions](https://disneytermsofuse.com/english/) prohibit robot/script extraction, data mining, scraping, and database compilation without written permission. ESPN is also an independent media source, not a league organizer. High coverage does not make it a lawful production fallback.

### 6. Other free sources

- [OpenLigaDB](https://www.openligadb.de/) is unauthenticated, ODbL-licensed, and explicitly community-maintained. It is strongest for German competitions and has no dependable breadth for this 15-match set. It can be a niche independent adapter, not a universal fallback.
- The existing UEFA v5 feed is authoritative for UEFA competitions but 4985 contained no UEFA fixture. Official league/federation feeds remain valuable authority lanes, but maintaining one adapter per domestic organizer is a large, fragmented effort rather than a single fallback source.
- Static/open historical datasets do not solve near-term kickoff or postponement updates and should not enter the live schedule ledger.

## Required policy change

The source classifications should **not** change: TheSportsDB and football-data.org remain independent. What must change is the promotion rule.

The current `official + independent` requirement is impossible to satisfy consistently across Russia's second tier, Argentina's Primera Nacional, Brazil Série B, Romania, Turkey, Sweden, and changing UEFA/CONMEBOL mixes with one generic official adapter. Keeping it as the only automatic lane guarantees recurring `timing_unknown` gaps.

Recommended ledger lanes:

1. **Official lane:** one organizer/federation claim, immutable snapshot, exact orientation, kickoff present, stable source ID. Independent corroboration is desirable but not mandatory.
2. **Independent consensus lane:** two legally authorized, independently operated APIs agree on home team, away team, and kickoff (exact or a deliberately documented small tolerance). Neither source may derive from the other where that can be established.
3. **Reviewed lane:** one authorized independent source plus explicit operator review bound to source hash, IDs, orientation, kickoff, and review timestamp.
4. **Candidate-only lane:** unsupported consumer endpoints, unresolved aliases, competition conflicts, or one-source facts without review. These never self-promote.

This is a controlled policy broadening, not permission for a single aggregator to silently become truth. If adopted, it changes an architectural decision and should be recorded in `memory-bank/DECISIONS.md` before implementation.

## Avoiding perpetual gaps

Implementation should be organized around unresolved events, not around a preferred provider:

- make scheduler/preparation/pin validation provider-neutral;
- persist provider event/team IDs and reviewed aliases, including accents and reserve-team markers;
- query the drawing's exact pairs across the whole plausible date window and cache every raw response immutably;
- maintain per-competition coverage profiles so known-ineligible providers are skipped;
- use rate-aware queues and circuit breakers; a suspended provider must fail over immediately rather than consume every retry;
- promote only through the three eligible ledger lanes above;
- create a deterministic unresolved reason and operator-review queue by an early deadline, rather than retrying forever;
- run a small coverage canary on every drawing and alert when either the primary or backup loses a historically covered league;
- preserve the existing T-10 expiry boundary: schedule discovery never revives an expired operator artifact.

## Bottom line

**Choose TheSportsDB v1 as the primary free collector and football-data.org v4 as the backup.** This is the strongest combination with explicit API documentation and usable terms. Expect 11/15 observed coverage from TheSportsDB and only 3–4/15 free-tier eligibility from football-data.org on 4985; the overlap is useful for independent consensus, but the pair is not a magic 15/15 feed.

Do not substitute unsupported ESPN or Sofascore JSON merely because their observed union with TheSportsDB would cover 4985. The correct way to close the remaining gaps is a provider-neutral ledger with official-only, two-independent, and reviewed-one-independent lanes. BetsAPI can later be evaluated as a paid broad-coverage escape hatch if a valid token and budget are deliberately restored, but it is neither free nor official.
