# TheSportsDB coverage investigation: drawing 4986

**Scope:** investigation only. No ledger mutation, release-policy change,
scheduler activation, package generation, or betting action. The only live
evidence used here is the already completed 12-request probe saved at
`/tmp/toto_tdb_4986_probe.json`.

## Executive summary

- The existing TheSportsDB collector returned **0/15 candidates** after 30
  successful `/searchevents.php` requests (home/away and reverse direction).
- The dominant root cause is **identity/query construction**, not transport,
  quota, date filtering, parser, or matcher: almost every query used Cyrillic
  team names, while TheSportsDB event titles use canonical Latin/English names.
  All existing responses were HTTP 200 with `event: null`; therefore no event
  reached parsing or matching.
- The free `/eventsday.php` strategy also observed **0/15** targets. It returned
  exactly three unrelated events on every queried day, consistent with the
  documented free limit of three rows. It cannot be the primary discovery
  strategy for a 15-event mixed-league coupon.
- The team-ID sample succeeded for **3/3 representative events**: Cardiff City
  vs Norwich City, Stevenage vs Reading, and LASK vs Celtic. Each home-team
  lookup returned one team and each `/eventsnext.php` call returned the exact
  target fixture.
- Sofascore already supplied independent candidates for **10/15** events. The
  five empty target IDs are **180086, 180088, 180090, 180091, 180092**.
- Recommendation: generate canonical Latin query candidates, cache stable
  team IDs, and use bounded home-team `/eventsnext.php` fallback. Keep
  TheSportsDB independent and non-promoting; **do not change the release
  policy**.

## Production CLI verification after the alias implementation (2026-08-25)

The exact production `collect-schedule-sources` command completed in about 48
seconds using the immutable drawing-4986 queue, reviewed alias catalog, and
schedule-evidence ledger. Counting only `status=independent_candidate`:

- Sofascore: **10/15**;
- TheSportsDB: **12/15**;
- source union: **12/15**;
- newly covered beyond Sofascore: event IDs **180086** and **180088**;
- unresolved: event IDs **180090, 180091, 180092**.

TheSportsDB diagnostics were `attempted=30`, `skipped=0`, and
`budget_exhausted=false`. The catalog/ledger conflict for normalized alias
`рапид вена` was retained only as a lookup hint and reported through
`alias_conflicts_skipped`; the ledger remained unchanged. This is improved
independent-source coverage, not reviewed promotion or release evidence.

## Reviewed alias follow-up (2026-08-25)

The versioned source-independent reviewed alias catalog now contains the 18
requested Cyrillic-to-canonical team names for nine drawing-4986 pairs. The
collector entry points load the validated reviewed spelling for query
construction, while the existing matcher receives the normalized form of that
same mapping. No Sofascore lookup hint is inserted into matcher aliases.

Network-free collector regressions prove exact reviewed-alias matching for the
seven previously rejected pairs Cardiff City–Norwich City,
Blackpool–Lincoln City, Cambridge United–Millwall,
Fleetwood Town–Shrewsbury Town, Stoke City–Hull City,
Southampton–West Ham United, and Nottingham Forest–Leeds United. Separate
regressions prove the canonical forward/reverse query names
`Stevenage_vs_Reading` and `LASK_vs_Celtic`; they do not claim a live provider
match or new coverage measurement.

Explicit gender markers are retained in canonical, transliterated, and hint
query candidates. Gender-incompatible TheSportsDB events are removed before
matching, so an unmarked reviewed men's alias is not inherited by a women's
target and the reverse is also fail-closed. A returned unrelated low-score pair
still rejects. Pair/team/margin thresholds, the three-hour matcher window, the
five-day search window, request budget, and promotion policy are unchanged.
Focused verification: `tests/test_thesportsdb_schedule_collection.py` reports
`17 passed in 32.80s`.

## Implemented follow-up (2026-08-25)

The existing independent TheSportsDB path now builds deterministic query-name
candidates from the normalized original name, directly available reviewed or
caller-supplied canonical aliases, Cyrillic-to-Latin transliteration, and Latin
home/away names observed by the earlier independent Sofascore pass. Canonical
or Latin names are prioritized for one home-vs-away query; the bounded reverse
query is deduplicated from the forward query. Independent-source names are
lookup hints only: they are not added to the identity matcher, do not establish
consensus, and cannot promote a candidate.

Women's/gender markers are preserved during query construction. A women's
target cannot consume a men's canonical alias, and transliteration retains an
explicit women's marker when needed. The provider client also has a hard
per-run transport budget of 30 requests. Cache hits are checked before the
budget and consume no transport; secret-safe diagnostics expose attempted,
skipped, and budget-exhausted counts without the key.

This narrow follow-up deliberately did **not** add `/searchteams.php` or
`/eventsnext.php` team-ID fallback. Stable team-ID resolution remains the next
possible coverage step and requires a separate endpoint/identity design. The
release boundary is unchanged: TheSportsDB and Sofascore remain independent,
non-promoting evidence with `ledger_eligible=false` and
`ledger_mutated=false`. Focused verification passed all 28 tests in
`tests/test_thesportsdb_provider.py` and
`tests/test_thesportsdb_schedule_collection.py`.

## Existing collector input and bounded classification

The target timing window used by the current collector was
`2026-08-25T17:00:00Z` through `2026-08-30T17:00:00Z`. All events are football.
The date is taken from existing independent evidence where available; `unknown`
means only that the stored artifacts did not establish an exact date.

`A_vs_B / reverse` below is the exact normalized search form sent to
`/searchevents.php` in both orientations.

| # | Target ID | Event | Date from evidence | Existing TheSportsDB search | Existing result | Bounded classification | Sofascore |
|---:|---:|---|---|---|---:|---|---|
| 1 | 180078 | Кардифф Сити — Норвич | 2026-08-25 | `Кардифф Сити_vs_Норвич / reverse` | 0 | **Alias/query mismatch confirmed.** Team-ID found exact `Cardiff City vs Norwich City`; provider has the event. | candidate |
| 2 | 180079 | Блэкпул — Линкольн Сити | 2026-08-25 | `Блэкпул_vs_Линкольн Сити / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 3 | 180080 | Блэкберн Роверс — Шеффилд Юнайтед | 2026-08-25 | `Блэкберн Роверс_vs_Шеффилд Юнайтед / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 4 | 180081 | Кембридж Юнайтед — Миллуолл | 2026-08-25 | `Кембридж Юнайтед_vs_Миллуолл / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 5 | 180082 | Флитвуд — Шрусбери Таун | 2026-08-25 | `Флитвуд_vs_Шрусбери Таун / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 6 | 180083 | Сток Сити — Халл Сити | 2026-08-25 | `Сток Сити_vs_Халл Сити / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 7 | 180084 | Уолсолл — Лейтон Ориент | 2026-08-25 | `Уолсолл_vs_Лейтон Ориент / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 8 | 180085 | Саутгемптон — Вест Хэм | 2026-08-25 | `Саутгемптон_vs_Вест Хэм / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 9 | 180086 | Стивенидж — Рединг | 2026-08-25 | `Стивенидж_vs_Рединг / reverse` | 0 | **Alias/query mismatch confirmed.** Team-ID found exact `Stevenage vs Reading`; provider has the event. | empty |
| 10 | 180087 | Ноттингем Форест — Лидс | 2026-08-25 | `Ноттингем Форест_vs_Лидс / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 11 | 180088 | ЛАСК Линц — Селтик | 2026-08-25 | `ЛАСК Линц_vs_Селтик / reverse` | 0 | **Alias/query mismatch confirmed.** Team-ID found exact `LASK vs Celtic`; provider has the event. | empty |
| 12 | 180089 | Валенсия — Бетис | 2026-08-25 | `Валенсия_vs_Бетис / reverse` | 0 | Cyrillic alias plus exact-title endpoint limitation. Independent evidence confirms the event; individual TheSportsDB presence was not probed. | candidate |
| 13 | 180090 | Рязань — Спартак Тамбов | unknown inside window | `Рязань_vs_Спартак Тамбов / reverse` | 0 | Query/alias mismatch is primary; provider coverage, league coverage, and exact date remain unverified. Provider absence is **not proven**. | empty |
| 14 | 180091 | Торпедо Владимир — Красное Знамя | unknown inside window | `Торпедо Владимир_vs_Красное Знамя / reverse` | 0 | Query/alias mismatch is primary; provider coverage, league coverage, and exact date remain unverified. Provider absence is **not proven**. | empty |
| 15 | 180092 | Абха — Аль Халидж Сайхат | unknown inside window | `Abha Club_vs_Аль Халидж Сайхат / reverse` | 0 | Mixed Latin/Cyrillic exact title is unsuitable; provider coverage, league coverage, and exact date remain unverified. Provider absence is **not proven**. | empty |

No stored TheSportsDB row had normalized events or statuses. Consequently none
of the 15 existing zeroes can be attributed to parser/matcher rejection. For
the three sampled exact fixtures, the returned sport, date, orientation, and
window were valid, which also excludes sport/date/window mismatch for those
three.

## Twelve-request probe

All 12 requests completed once, without retries, with HTTP 200.

| Req. | Endpoint and bounded input | Rows | Relevant target coverage |
|---:|---|---:|---:|
| 1 | `/eventsday.php`, Soccer, 2026-08-25 | 3 | 0 |
| 2 | `/eventsday.php`, Soccer, 2026-08-26 | 3 | 0 |
| 3 | `/eventsday.php`, Soccer, 2026-08-27 | 3 | 0 |
| 4 | `/eventsday.php`, Soccer, 2026-08-28 | 3 | 0 |
| 5 | `/eventsday.php`, Soccer, 2026-08-29 | 3 | 0 |
| 6 | `/eventsday.php`, Soccer, 2026-08-30 | 3 | 0 |
| 7 | `/searchteams.php`, `Cardiff City` | 1 team | identity found |
| 8 | `/eventsnext.php`, Cardiff City team ID | 1 event | exact event #1 |
| 9 | `/searchteams.php`, `Stevenage` | 1 team | identity found |
| 10 | `/eventsnext.php`, Stevenage team ID | 1 event | exact event #9 |
| 11 | `/searchteams.php`, `LASK` | 1 team | identity found |
| 12 | `/eventsnext.php`, LASK team ID | 1 event | exact event #11 |

The six day responses contained only unrelated fixtures. This is an endpoint
visibility limitation, not evidence that the target events are absent from the
provider: three target fixtures were subsequently recovered by team ID.

## Coverage comparison

| Strategy | Requests observed | Target coverage | Interpretation |
|---|---:|---:|---|
| Current two-direction Cyrillic `/searchevents` | 30 | **0/15** | Exhausted the minute budget on unusable exact-title strings. |
| Free `/eventsday`, six UTC dates | 6 | **0/15 visible** | Exactly 3 unrelated rows/day; truncated free response is unsuitable for broad discovery. |
| Canonical home team ID + `/eventsnext` sample | 6 | **3/3 sampled** | Recovered all three representative targets, including two missed by Sofascore. Not yet evidence of 15/15 coverage. |
| Existing Sofascore collector | existing artifact | **10/15** | Independent candidates only; empty IDs: 180086, 180088, 180090, 180091, 180092. |

The team-ID result is a promising sample, not a coverage guarantee. The free
team-next endpoint returns only one upcoming home event, so it can miss a
target when the requested team is away, the provider orders fixtures
differently, or the target league/team is absent.

## Root cause and limitations

1. **Primary defect: wrong identity language.** The collector preferred
   Cyrillic target names and performed exact event-title searches. Reversing
   home/away did not solve transliteration or canonical-name differences.
2. **Request budget was spent inefficiently.** Two guaranteed-null searches
   per event consumed all 30 free requests/minute.
3. **Day bulk is truncated.** The observed free response exposed only three
   events per date and missed even events known to exist in TheSportsDB.
4. **Provider coverage remains incomplete.** Events 13–15 were not recovered
   by another source or a team-ID probe, so TheSportsDB league/team absence
   cannot be separated from alias failure for those rows.
5. **Sample size is small.** Team-ID success is 3/3 representative cases, not
   a prospective reliability measurement.
6. **Independent evidence is not release evidence.** Neither TheSportsDB nor
   Sofascore alone satisfies the existing official-plus-independent reviewed
   evidence contract.

## Remaining next implementation

Canonical query construction is now implemented. A separate future change may
add the remaining bounded **team-ID resolver** inside the existing independent
TheSportsDB candidate path:

1. On a canonical-query miss, resolve the canonical **home team** through
   `/searchteams.php`,
   validate the returned identity, and cache its stable provider team ID across
   drawings.
2. Query `/eventsnext.php` using the cached home-team ID and require exact
   canonical home/away orientation plus the existing bounded time window.
3. Cache team IDs long-term and schedule payloads briefly while retaining the
   implemented hard 30-request per-run transport budget.
4. Retain immutable request evidence, explicit unresolved/conflict reasons,
   and the existing fail-closed parser/matcher rules.

This change should be evaluated on several completed drawings before relying
on it operationally. TheSportsDB must remain `ledger_eligible=false` and
`ledger_mutated=false`; **no release-policy or promotion rule changes are
recommended**.
