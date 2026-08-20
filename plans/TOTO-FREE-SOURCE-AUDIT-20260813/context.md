# TOTO-FREE-SOURCE-AUDIT-20260813

Date: 2026-08-13  
Scope: project context collection and public source research only. No source was
connected to production, no code was changed, and no secret was read or sent.

## Executive conclusion

TotoAI currently does **not** use external sports statistics or external odds
to calculate production probabilities or choose the operator package. The
production probability matrix is still normalized TotoBrief `bk_*` data;
TotoBrief pool percentages are used as the crowd model. API-Sports and the
existing sports/odds modules currently provide identity, schedule, audit, and
shadow evidence only.

The best free first experiment is a prospective **shadow audit of The Odds
API**. Its official Starter plan currently offers 500 credits per month and its
official bookmaker list includes 1xBet and Pinnacle. It must not affect package
generation until exact BaltBet-event coverage, freshness, semantics, and
out-of-sample probability quality are measured. No publicly documented,
official 1xBet odds API was found. The examined GitHub 1xBet parser is incomplete,
stale, unofficial, and unsuitable for production.

## 1. Current project state

### 1.1 What actually affects production today

| Input/component | Current role | Affects production probabilities/package? | Evidence |
|---|---|---:|---|
| TotoBrief `bk_win_1`, `bk_draw`, `bk_win_2` | Normalized 15x3 probability matrix | **Yes** | `src/toto_ai/ev/drawing.py` builds `true_rows` from source `bk` and records `probability_sources=("totobrief_bk",) * 15`. |
| TotoBrief pool percentages | Crowd-selection model used by EV/payout logic | **Yes** | Current EV drawing input and project memory. It is not treated as true sports probability. |
| TotoBrief `pin_*` fields | Stored/available reference fields | **No** | No production probability path selects them. |
| Current sports statistics snapshot | Diagnostics, research and shadow evaluation | **No** | `src/toto_ai/sports_stats/reports.py` explicitly says the evidence is diagnostic and is not used by probabilities, briefs, packages, scheduler, PLAY, or decision markers. |
| Sports shadow model | Separate experimental output with `NOT_ACTIVATED` status | **No** | `src/toto_ai/sports_stats/shadow_operation.py`; there is no connection to the production `EVInput`. |
| External odds consensus | Provider-neutral audit/shadow artifact | **No** | `src/toto_ai/external_odds/`; the current concrete adapter is API-Sports and does not replace production BK probabilities. |
| API-Sports fixture/schedule data | Event identity, kickoff/status, eligibility and audit support | Indirect operational use only | Current `sports_stats` provider and scheduler architecture. |

The final input fingerprint also includes the target events' TotoBrief BK
probabilities (`src/toto_ai/runner/final_input.py`). Therefore an external
source cannot silently change a package in the current architecture.

### 1.2 Sports-statistics implementation

Implemented:

- provider protocol and source-neutral snapshots;
- API-Sports concrete provider;
- fixture identity and kickoff/status reconciliation;
- up to ten prior completed fixtures when the provider returns them;
- basic recent form, home/away W-D-L, goals and rest indicators;
- optional standings;
- append-only audit/shadow reports and an activation gate.

Not implemented as production features:

- injuries and confirmed lineups;
- xG/event models;
- Elo/team-strength model;
- reliable cross-provider historical feature store;
- trained and validated multi-league sports model;
- sports-data contribution to package probabilities.

The recorded free-plan API-Sports trial was incomplete: for drawing 4957 it
did not provide usable current-season history/standings, leaving all 15 events
partial and none complete. The project policy requires at least 30 drawings / 450
events, at least 70% sports-data coverage, temporal leakage checks, and
out-of-sample log-loss/Brier/calibration evidence before activation. A passing
report would still require an explicit review; it does not activate itself.

### 1.3 External-odds implementation

The architecture is provider-neutral but currently has only an API-Sports
adapter. It can collect and compare bookmaker consensus in research artifacts,
but the production probability source remains TotoBrief BK. There is no direct
Pinnacle integration, no direct 1xBet integration, and no approved scraping
path.

## 2. Factual source findings

Prices and quotas below are the public values observed on 2026-08-13 and may
change. They must be rechecked before subscribing.

### 2.1 Free and free open data

#### football-data.co.uk — recommended for historical calibration

- Provides free downloadable CSV football results, match statistics, and
  bookmaker odds archives.
- Strong fit for historical calibration and feature experiments in covered
  leagues.
- Not a live API, football only, and its current worldwide set does not cover
  the long tail of minor, youth, women, and mixed-sport Toto events.

Sources: [data archive](https://www.football-data.co.uk/data.php),
[current/new data](https://www.football-data.co.uk/all_new_data.php).

#### StatsBomb Open Data — recommended for football feature research only

- Official repository provides selected matches, events, lineups, and rich
  event data for research/education.
- Useful for validating feature ideas such as xG/event-derived team strength.
- Selected competitions only, not a comprehensive live feed, no hockey, and
  not suitable as the operational source for all 15 Toto events.

Source: [StatsBomb Open Data repository](https://github.com/statsbomb/open-data).

#### TheSportsDB free API — supplemental identity/results probe

- Official v1 test key is public (`123`), with a documented free rate of 30
  requests per minute.
- Broad multi-sport taxonomy can help with aliases, teams, leagues, schedules,
  and results.
- Free endpoint result limits and community-contributed data make it unsuitable
  as the sole model source. Exact event coverage and correction latency need
  measurement.

Sources: [API page](https://www.thesportsdb.com/api.php),
[documentation](https://www.thesportsdb.com/documentation),
[pricing](https://www.thesportsdb.com/pricing).

### 2.2 Freemium sources

#### The Odds API — highest-priority prospective odds audit

- The official Starter plan lists 500 credits/month, all sports, most
  bookmakers and markets, but no historical odds; the first paid plan is
  currently listed as USD 30/month for 20,000 credits and historical access.
- Official bookmaker pages/listing include 1xBet and Pinnacle in the European
  region.
- The v4 API documents event IDs, commence times, bookmaker updates, `h2h`
  markets and request-credit accounting.
- It is the best current candidate for obtaining documented 1xBet/Pinnacle
  snapshots without scraping. Actual minor-league, women/youth, and hockey
  coverage must be measured against real BaltBet drawings; a bookmaker being
  listed does not mean it quotes every event.

Sources: [official site and pricing](https://the-odds-api.com/),
[v4 guide](https://the-odds-api.com/liveapi/guides/v4/),
[bookmakers](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html).

#### Odds-API.io — secondary cross-check candidate

- Official free plan lists 100 requests/hour, 500/day, 34 sports, and two
  recreational bookmakers, with live and prematch access.
- Sharp bookmakers, exchanges, and broader production use are paid features;
  the free plan does not establish reliable free 1xBet/Pinnacle access.
- Suitable as an independent coverage/identity/odds cross-check, not the first
  sharp-market source.

Sources: [free plan](https://odds-api.io/pricing/free),
[documentation](https://docs.odds-api.io/).

#### API-Sports / API-Football — keep current operational/audit role

- Official free plan currently advertises 100 requests/day.
- The source is already integrated and useful for schedule, identity, status,
  and some current data.
- The project's own prospective evidence shows that advertised endpoints do
  not imply usable free current-season history/standings for every competition.
  It is not currently a sufficient sports-model source.

Source: [API-Football official plans/features](https://www.api-football.com/).

#### football-data.org — optional top-competition enrichment

- Official free plan lists twelve competitions and ten calls/minute, with
  delayed scores/schedules, fixtures, and tables.
- Stable and documented, but football-only and too narrow for mixed and
  long-tail BaltBet Toto. Odds/statistics are paid add-ons or require paid
  access.

Sources: [pricing](https://www.football-data.org/pricing),
[quickstart](https://www.football-data.org/documentation/quickstart).

#### TheSportsDB paid upgrade — only after a free coverage audit

- Current Developer plan is listed at USD 9/month and raises limits/data
  availability.
- It should be considered only if the free probe demonstrates good exact event
  and result coverage for actual Toto drawings.

Source: [pricing](https://www.thesportsdb.com/pricing).

### 2.3 Paid sources

#### BetsAPI / ru.betsapi.com

- BetsAPI is a commercial aggregator, not a free public API. Its official docs
  describe token query authentication, `api.b365api.com` / `api.betsapi.com`
  endpoints, and a default limit of 3,600 requests/hour.
- Event-odds documentation accepts sources including `1xbet` and
  `pinnaclesports`; the published coverage table currently marks 1xBet prematch
  and in-play coverage for soccer and basketball, while other sports in that
  table are not shown as covered. The docs warn that coverage evolves and may
  be inaccurate.
- Public pricing pages observed for this audit list direct 1xBet access around
  USD 100/month, soccer event APIs around USD 30/month, ice hockey around USD
  10/month, and short paid trials. Exact plan contents must be confirmed before
  purchase.
- This may be useful as a short benchmark if free providers fail, but it is not
  a free solution and its contractual data-use/redistribution rights require
  review.

Sources: [official docs](https://betsapi.com/docs/),
[event odds and source coverage](https://betsapi.com/docs/events/odds.html),
[pricing](https://betsapi.com/docs/pricing.html).

### 2.4 Unofficial endpoints and scraping — reject for production

#### Is there an official public 1xBet API?

No publicly documented official developer/odds API or developer portal was
found on the [official 1xBet consumer site](https://1xbet.com/) or in its public
documentation/search results. This statement does **not** prove that no private
B2B, affiliate, or licensed feed exists; it means there is no public supported
contract on which TotoAI can safely depend today.

Browser/internal endpoints are not equivalent to a public API. Without written
authorization and a stable contract they carry terms-of-service, geo/IP,
anti-bot, schema-change, provenance, timestamp, and account/blocking risks.
TotoAI should not use them.

#### `emresports/1xbet_parser_api`

The [repository](https://github.com/emresports/1xbet_parser_api) is unsuitable:

- its own README says it is for acquaintance and that the full working version
  requires contacting the author through Telegram;
- required configuration/database pieces are absent, so the published version
  is not operational as-is;
- the repository has only eight commits and its latest code activity was in
  May 2024;
- no repository-level license file/recognized GitHub license is present,
  despite an `ISC` string in `package.json`;
- it depends on an undisclosed 1xBet host/internal interface, old Node tooling,
  MySQL and PM2, with no official API contract, SLA, as-of guarantees, or data
  rights.

Using it would add a fragile scraper and a supply-chain/provenance dependency,
not a reliable odds provider. Recommendation: **do not integrate or use for the
audit**.

## 3. Source comparison matrix

| Source | Class | Odds | Sports stats/results | Football | Hockey | Historical free | Main limitation | Proposed role |
|---|---|---:|---:|---:|---:|---:|---|---|
| TotoBrief | Existing | BK/pool/Pin fields | Draw/results | Yes | Yes | Yes | Derived source semantics/provenance | Production baseline, unchanged |
| API-Sports | Freemium, already used | Some audit odds | Yes | Yes | Product-dependent | Limited by plan/competition | Free current-season gaps observed | Identity, timing, status, shadow audit |
| The Odds API | Freemium | **Yes** | Limited | Yes | Yes | No | 500 credits and unverified long-tail coverage | First prospective odds audit |
| Odds-API.io | Freemium | Yes, limited books free | Results/API claims | Yes | Yes | Plan-dependent | Only two recreational books free | Secondary odds cross-check |
| football-data.org | Freemium | Paid/add-on | Fixtures/tables | Yes | No | Narrow free set | 12 competitions | Optional matched enrichment |
| TheSportsDB | Free/freemium | No primary odds | Identity/schedules/results | Yes | Yes | Partial | Community data and free return limits | Supplemental identity/result probe |
| football-data.co.uk | Free | Historical odds | Results/stats CSV | Yes | No | **Yes** | No live API; limited leagues | Historical calibration/training |
| StatsBomb Open Data | Free/open subset | No | Rich event/lineup data | Yes | No | **Yes**, selected | Selected competitions, not live | Feature research only |
| BetsAPI | Paid | **Yes**, including advertised 1xBet | Events/results | Yes | Plan-dependent | Paid | Cost, coverage and data-rights review | Paid fallback/trial only |
| Direct 1xBet parser/endpoints | Unofficial/scraping | Possible | Unclear | Unclear | Unclear | No supported contract | Legal, blocking, breakage, provenance | Reject |

## 4. Prospective audit design

### 4.1 Unit and sample

- Audit at least **30 consecutive completed BaltBet drawings / 450 events**;
  50 drawings is preferred before a production decision.
- Capture each open drawing twice: morning/pre-analysis and final T-10 snapshot.
- Persist raw source response, provider timestamp, local fetch time, source
  event ID, normalized event identity, and an immutable payload hash.
- New providers remain shadow-only. Missing external data must not block the
  scheduler or alter the current TotoBrief-BK fallback.

### 4.2 Per-event audit fields

1. Exact sport, competition, country, gender, youth/reserve and team identity.
2. Home/away order and source event ID; no silent reversal.
3. Kickoff UTC, event status, cancellation/postponement semantics.
4. Full-time three-way market semantics:
   - football: regulation/full time;
   - hockey: regulation 1-X-2, not moneyline including overtime unless BaltBet
     event rules say otherwise.
5. Bookmaker name, 1/X/2 prices, bookmaker update time and fetch time.
6. Historical fixtures/standings/statistics with strict as-of cutoff and no
   future leakage.
7. Match state: exact, ambiguous, reversed, missing, unsupported, or stale.
8. Quota use, latency, 429/5xx/timeouts and retry outcome.
9. License/terms, caching/storage and redistribution constraints.

### 4.3 Metrics and acceptance gates

| Dimension | Metric/gate |
|---|---|
| Identity safety | 100% precision among auto-accepted matches; ambiguous matches are missing, never guessed. |
| Coverage | Report exact coverage by source, sport, competition, gender/youth and capture time. Composite odds target: at least 90% over the audit; sports-model evidence keeps the existing 70%/450-event minimum. |
| Freshness | T-10 bookmaker update preferably no older than 15 minutes; if the provider exposes no timestamp, mark freshness unverified. |
| Reliability | At least 95% successful scheduled capture attempts and no provider failure may block package production. |
| Semantics | All accepted events must expose comparable three-way 1/X/2 markets; reject moneyline/two-way substitutions. |
| Probability quality | After results: log loss, Brier score and calibration versus TotoBrief BK, per source and consensus; use time-ordered/out-of-sample evaluation. |
| Package impact | Replay packages shadow-only under the same bank/category; compare 13+/14+/15 hit rates, cost, gross/net EV assumptions, and failure/no-bet rate. |
| Activation | No activation on coverage alone. Require non-degradation in OOS probability metrics, scheduler safety, unchanged fallback, and explicit project decision. |

### 4.4 Minimum experiment matrix

| Experiment | Morning | T-10 | Result capture | Production effect |
|---|---:|---:|---:|---:|
| Existing TotoBrief BK/pool baseline | Yes | Yes | Yes | Current baseline |
| API-Sports current adapter | Yes | Yes | Yes | None/shadow |
| The Odds API free | Yes | Yes | Yes | None/shadow |
| Odds-API.io free | Optional | Yes | Yes | None/shadow |
| TheSportsDB free | Yes | Optional | Yes | None/shadow |
| football-data.org matched comps | Yes | Optional | Yes | None/shadow |
| football-data.co.uk/StatsBomb historical | Offline | No | Historical | Research only |
| BetsAPI short trial | Only if free audit fails | Yes | Yes | None/shadow |

## 5. Ranked recommendation

1. **The Odds API Starter, shadow-only.** Audit 30 consecutive drawings at
   morning and T-10. It is the most direct documented free route to compare
   1xBet/Pinnacle with TotoBrief without scraping.
2. **Keep API-Sports in its current identity/timing/status role.** Record its
   actual statistics coverage; do not infer that an endpoint is available just
   because it exists in paid documentation.
3. **Build the free historical research lane** from football-data.co.uk and
   StatsBomb Open Data; use football-data.org only where competition matching is
   exact.
4. **Probe TheSportsDB free** for aliases, schedules, statuses and results. Do
   not feed it into probabilities unless its accuracy and coverage pass the
   same prospective audit.
5. **Use Odds-API.io free as a secondary independent cross-check**, not as the
   primary sharp-market feed.
6. **Consider a BetsAPI one-day trial only if free sources leave material
   coverage holes.** Do not subscribe to direct 1xBet access until the trial
   demonstrates incremental exact coverage and measurable value within the
   project's optional USD 30 ceiling; its currently advertised direct 1xBet
   plan is above that ceiling.
7. **Reject direct 1xBet scraping and the examined GitHub parser.** They do not
   provide a legally and technically stable production dependency.

## 6. What is required to start the audit later

- A free The Odds API account/key. The key must be stored only in `.env` with
  restrictive permissions and never pasted into chat, logs, reports, or Git.
- Optionally a free Odds-API.io key for the secondary cross-check.
- No key is needed for the public TheSportsDB v1 test key, football-data.co.uk
  CSV files, or StatsBomb Open Data, but their terms/attribution still apply.
- A separate implementation task should add provider adapters and append-only
  shadow capture. It must not modify production probabilities or package
  selection during the audit.

## 7. Risk register

| Risk | Applies to | Mitigation |
|---|---|---|
| Undocumented endpoint/ToS breach | Direct 1xBet, scrapers | Do not use; require documented provider contract. |
| Account/IP blocking and schema breakage | Scrapers/internal endpoints | Reject from architecture. |
| Wrong event or home/away match | Every aggregator | Exact identity gate; ambiguous means missing. |
| Wrong market semantics | Hockey and cup/playoff events | Validate regulation 1-X-2 explicitly. |
| Stale odds or no source timestamp | Odds providers | Record update/fetch times; mark unverified/stale. |
| Free quota exhaustion | The Odds API/API-Sports/Odds-API.io | Batch requests, count quota, preserve TotoBrief fallback. |
| Long-tail coverage gaps | All free providers | Measure on real consecutive Toto drawings; use provider ensemble only after audit. |
| Data leakage | Historical statistics/model training | Enforce event-time cutoffs and time-ordered splits. |
| Licensing/storage/redistribution limits | All external sources | Review official terms before persistent storage or sharing. |
| False expectation of profit | Entire project | Treat source quality as an empirical hypothesis; no profitability claim without OOS package backtests and prospective evidence. |

## Final decision for this task

Do not integrate `ru.betsapi.com`, direct 1xBet endpoints, or the GitHub parser
now. The next evidence-producing step should be a **free, prospective,
shadow-only source audit**, led by The Odds API and backed by the existing
API-Sports adapter plus selected free historical/supplemental sources. Until
that audit passes, production continues to use normalized TotoBrief BK
probabilities and the current scheduler/package path unchanged.
