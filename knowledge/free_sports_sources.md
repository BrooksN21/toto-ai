# Free sports-source candidates

Updated: 2026-08-20

## Policy

Free providers are evaluated as frozen, provider-neutral shadow evidence.
Missing data must fall back per event to TotoBrief BK and must never block the
evening package. No source may influence production probabilities before the
30-drawing / 450-event coverage and leakage-safe performance gates pass.

## Current measured providers

- API-Sports external odds: 10 drawings / 150 events, 72.67% unique matching,
  68.00% usable consensus and 48 fallbacks.
- The Odds API: one drawing / 15 events, 4 matches and 11 fallbacks.
- API-Sports sports statistics on drawing 4975: zero complete venue-history
  rows, ten partial rows and five missing rows.
- Sofascore: independent schedule discovery only; it cannot auto-promote an
  event without official corroboration.
- UEFA public v5 match feeds: authoritative schedule/identity evidence for
  UEFA competitions. The first adapter requires exact localized target aliases
  and independently re-fetched Sofascore agreement before append-only ledger
  promotion. A frozen drawing-4981 replay resolved 2/2 queued UEFA events; this
  is schedule evidence, not a sports probability model.

The durable measured report is
`reports/research/free-source-audit-20260814/summary.md`.

Drawing 4981 added a second prospective point: API-Sports sports history had
0/15 complete venue rows (10 partial, 5 missing), while The Odds API matched
3/15 exact events. Both artifacts are frozen pre-deadline and `NOT_ACTIVATED`;
all sports probabilities fell back to BK.

## Candidates from official documentation

### 1. football-data.org — first shadow pilot

- Official free tier documents 12 competitions, fixtures, delayed schedules
  and scores, league tables, and 10 calls/minute.
- It exposes competition matches, team matches, and TOTAL/HOME/AWAY standings.
- Expected benefit: lawful current-season form and standings in supported top
  competitions.
- Expected limitation: Toto drawings frequently contain lower leagues, cups,
  friendlies, hockey, and other competitions outside the free list.
- Requires a separately supplied registered API token. No token is currently
  assumed or stored by this decision.

Sources:

- <https://www.football-data.org/pricing>
- <https://www.football-data.org/coverage>
- <https://docs.football-data.org/general/v4/policies.html>
- <https://docs.football-data.org/general/v4/competition.html>

### 2. TheSportsDB — identity/schedule shadow candidate

- The official v1 documentation provides a public free key and documents 30
  requests/minute across many sports and leagues.
- Useful for event/team identity, scheduled events, results, and a secondary
  cross-check.
- The data is crowd-sourced, and free previous/next team schedule endpoints
  expose too little history for a reliable form model. It is not a substitute
  for a calibrated probability source.

Source: <https://www.thesportsdb.com/docs_api_guide>

### 3. OpenLigaDB — narrow schedule corroboration

- Public unauthenticated JSON API with ODbL community data.
- Useful for German schedule/result corroboration where coverage exists.
- Community editing and narrow competition scope make it unsuitable as the
  only authoritative or predictive source.

Sources:

- <https://openligadb.de/>
- <https://github.com/OpenLigaDB/OpenLigaDB-Samples>

### 4. StatsBomb Open Data — offline research only

- Selected competitions and seasons include match, event, lineup, and some 360
  data for research.
- Useful for feature-engineering and residual-model experiments.
- It is not a broad live/prospective feed and cannot satisfy daily Toto
  coverage by itself.

Source: <https://github.com/statsbomb/open-data>

## Rejected shortcut

An unofficial scraper or parser repository is not accepted merely because it
works today. Before adoption it needs explicit ToS/licensing review,
reproducible timestamps, identity tests, rate-limit behavior, immutable raw
snapshots, and a demonstrated coverage advantage over official candidates.
