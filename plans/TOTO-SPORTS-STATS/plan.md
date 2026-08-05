# TOTO-SPORTS-STATS: первый audit-only vertical slice

## Статус 2026-07-27

Первый вертикальный срез реализован и прошёл prospective acceptance на тираже
4957. Контракты, persistence, adapter, feature builder, CLI и отчёты работают
fail-safe, но текущий бесплатный план API-Sports не даёт историю и standings
сезона 2026. Все 15 событий корректно получили
`provider_plan_unavailable` и `MARKET ONLY`; спортивные признаки не влияют на
прогноз или пакет. Следующий этап — проверка другого законного источника
current-season статистики.

## Цель

Собрать и заморозить до дедлайна проверяемые футбольные признаки для каждого
матча тиража, не меняя вероятности, купоны, `PLAY`/`NO BET` или scheduler.

Первый срез должен дать пригодный для будущего честного сравнения датасет:

- последние 5–10 завершённых матчей обеих команд;
- общие и home/away W-D-L;
- голы за/против;
- число дней отдыха;
- позиция в таблице, если она доступна;
- явные причины отсутствующих данных;
- полная as-of/provenance информация.

Это сбор evidence, а не спортивная модель и не доказательство прибыльности.

## Границы первого среза

### Входит

- только футбол;
- provider-neutral контракты;
- адаптер API-Football v3 поверх существующего `APISportsClient`;
- только заранее подготовленный тираж с валидными 15/15 pins;
- append-only SQLite snapshots;
- утренний ручной CLI и повторный запуск из immutable cache;
- JSON/CSV/Markdown audit report;
- строгая защита от future leakage;
- явный market-only fallback status для каждого неполного события.

### Не входит

- хоккейные признаки и модель;
- травмы и составы;
- `/teams/statistics`: его данные пока дублируются вычислениями из fixtures и
  потребуют дополнительной квоты;
- xG, удары и расширенная event statistics;
- обучение модели, blend с рынком и изменение package optimizer;
- historical backfill текущими standings/team statistics задним числом;
- scheduler wiring и любое автоматическое размещение ставок.

Injuries/lineups и `/teams/statistics` добавляются отдельными срезами только
после измерения покрытия, квоты и стабильности базового сбора.

## As-of и no-leakage контракт

1. Snapshot создаётся только до `drawing.deadline`.
2. У run отдельно хранятся `started_at`, `as_of` (момент завершения заморозки)
   и `deadline`; `started_at <= fetched_at <= as_of < deadline`.
3. Исторический fixture допустим, только если:
   - status — завершённый;
   - его timestamp строго меньше `min(as_of, target_starts_at)`;
   - fixture ID не равен target fixture ID.
4. API-порядок не считается доказательством времени: fixtures повторно
   сортируются и фильтруются локально.
5. Prospective standings допустимы только из ответа, полученного до `as_of`.
   Если для исторического as-of нет сохранённого pre-deadline ответа,
   standings помечаются `historical_asof_unavailable`, а не восстанавливаются
   из текущего состояния.
6. Явный past `--as-of` разрешает только cache entries с
   `fetched_at <= as_of`; сетевой запрос в прошлое запрещён.
7. Collector не импортирует и не читает `Event.result`,
   `drawing_result_snapshots` или settlement tables.
8. Любое нарушение времени делает источник непригодным; значения не
   подменяются нулями.

## Provider-neutral контракты

Добавить пакет `toto_ai.sports_stats`:

- `domain.py`
  - `StatsTargetEvent`;
  - `ProviderFixtureContext`;
  - `CompletedFixture`;
  - `StandingRow`;
  - `SourceEvidence`;
  - `FootballTeamWindow`;
  - `FootballEventFeatureSnapshot`;
  - `SportsStatsRunSnapshot`;
  - enum/status и reason codes для missing/partial/unsupported.
- `provider.py`
  - `SportsStatsProvider` protocol:
    - получить context target fixture;
    - получить завершённые fixtures команды до cutoff;
    - получить standings для league/season.

Все records immutable, UTC-only и валидируют идентификаторы, числа,
chronology, hashes и точные schema versions.

Минимальные missing reasons:

- `unsupported_sport`;
- `preparation_not_ready`;
- `target_fixture_missing`;
- `league_or_season_missing`;
- `provider_error`;
- `quota_exhausted`;
- `no_completed_fixtures`;
- `standings_unavailable`;
- `historical_asof_unavailable`;
- `future_data_rejected`;
- `stale_or_conflicting_cache`.

## API-Sports adapter

Расширить существующий transport/cache, не создавать второй HTTP-клиент:

1. `/fixtures?id=<target_fixture_id>`:
   получить и проверить target fixture, league ID, season и orientation.
2. `/fixtures?team=<team_id>&season=<season>&last=10&status=FT&timezone=UTC`
   для обычного prospective запуска.
3. Для explicit historical as-of использовать bounded `from/to` и всё равно
   применять локальный cutoff. Если exact `from/to` cache отсутствует,
   разрешён только совместимый frozen prospective `last=N` cache для тех же
   team/season/status/timezone при `fetched_at <= as_of`; его фактический
   request fingerprint сохраняется. Cache miss/newer cache никогда не вызывает
   сеть в historical-режиме.
4. `/standings?league=<league_id>&season=<season>`:
   один cacheable запрос на уникальную пару league/season; отсутствие таблицы
   для кубка — нормальная missingness.

Запросы дедуплицируются по target fixture, team/season и league/season.
Каждый parsed record содержит endpoint/params hash, payload hash и fetched_at.
Ошибки одного события не стирают остальные 14 результатов.

## Canonical features

Для каждой команды по последним максимум 10 допустимым fixtures:

- eligible fixture count и ordered fixture IDs;
- W/D/L overall;
- W/D/L дома и в гостях;
- goals for/against overall;
- goals for/against дома и в гостях;
- points per game;
- last-5 form points;
- last completed fixture timestamp;
- rest days до target fixture.

Для события:

- home/away provider и canonical team IDs;
- provider target fixture ID, league ID и season;
- target start;
- обе team windows;
- home/away standings position и points, если доступны;
- coverage/status/missing reasons;
- source evidence и canonical feature hash.

Неполный window остаётся неполным (`fixture_count < requested_count`), а не
масштабируется до десяти матчей.

## SQLite schema и storage

Добавить только новые таблицы:

### `sports_stats_runs`

- content-addressed `run_id`;
- drawing ID/number/fingerprint;
- provider, schema/config version;
- `started_at`, `as_of`, deadline;
- status: `complete | partial | failed`;
- event/complete/partial/missing/unsupported counts;
- request/cache/quota counters;
- payload/config hashes.

### `sports_event_feature_snapshots`

- `run_id`, event order и target event ID;
- sport/status/missing reasons;
- target/provider fixture and team IDs;
- league ID/season/target start;
- canonical feature JSON;
- source-evidence JSON;
- feature SHA-256.

Constraints:

- ровно одна event row на order в одном run;
- orders уникальны и лежат в `0..14`;
- повторная запись идентичного content — idempotent;
- тот же identity с другим content — conflict;
- старые таблицы не изменяются.

Storage API:

- `save_sports_stats_snapshot()`;
- `load_sports_stats_snapshot(run_id)`;
- `load_latest_eligible_snapshot(drawing_id, fingerprint, as_of)`.

Последняя функция никогда не возвращает snapshot после as-of/deadline.

## Collector, CLI и reports

Новая команда:

```bash
python -m toto_ai.cli collect-sports-stats \
  --open \
  --db data/toto.db \
  --provider api-sports \
  --history-size 10 \
  --report-dir reports/sports-stats
```

Альтернатива `--drawing-id`; ровно один selector обязателен.

Поведение:

1. загрузить exact drawing identity и ready 15/15 pins;
2. зафиксировать pre-deadline collection boundary;
3. собрать/dedupe provider data через существующий cache/quota transport;
4. построить все 15 audit rows, включая unsupported/missing;
5. атомарно сохранить immutable run;
6. атомарно записать:
   - `sports_stats_<drawing>_<run>.json`;
   - `sports_stats_<drawing>_<run>.csv`;
   - `sports_stats_<drawing>_<run>.md`.

Report показывает as-of/deadline, coverage, missing reasons, quota/cache,
по каждому событию — target, status, window counts, W-D-L/goals/rest/standing
и source timestamps/hashes. Он явно содержит:

```text
mode: AUDIT ONLY
package influence: NONE
fallback: MARKET ONLY
```

Команда не вызывает package generation и не создаёт betting markers.

## Порядок реализации

1. **Contracts и validators**
   - immutable domain/protocol;
   - canonical JSON/hash;
   - chronology и missingness tests.
2. **Append-only persistence**
   - SQLAlchemy tables/storage;
   - idempotency/conflict/as-of selection tests;
   - legacy DB initialization regression.
3. **API-Football adapter**
   - parsers target fixture/history/standings;
   - cache/quota/dedup/sanitized error tests;
   - no network in unit tests.
4. **Feature builder**
   - orientation-aware W-D-L/goals;
   - home/away splits, last-5, rest;
   - strict cutoff/target exclusion and partial-window tests.
5. **Collector + CLI + reports**
   - 15-row partial-safe orchestration;
   - atomic DB/report writes;
   - offline-cache replay equivalence;
   - no result-table access and no package/scheduler side effects.
6. **Prospective acceptance**
   - manual morning run on one prepared open drawing;
   - inspect quota, coverage and missing reasons;
   - rerun network-free from cache and compare hashes;
   - keep all output audit-only.

После каждого шага: focused tests, full `pytest`, repository-wide Ruff,
`git diff --check`, memory-bank update и отдельный commit.

## Acceptance criteria первого среза

- один prospective open drawing даёт immutable run и ровно 15 ordered event
  rows, даже при partial/missing data;
- ни один fixture/source после as-of или target start не входит в features;
- target fixture никогда не входит в history;
- historical past-as-of не использует текущий network response;
- prospective `last=N` collection → network-off historical replay из того же
  cache даёт идентичные canonical feature hashes и byte-identical reports;
- duplicated team/league requests реально дедуплицируются;
- provider/quota failure выражен reason code и market-only fallback;
- reports воспроизводимы и hash-bound;
- CLI не читает результаты и не влияет на вероятности, package, scheduler,
  `PLAY` или `.bet-ready`;
- старые БД и существующие 1354+ tests остаются совместимы.

## Out-of-sample путь после накопления snapshots

Это следующий milestone, не часть первого среза:

1. Накапливать только frozen pre-deadline snapshots и затем связывать их с
   authoritative post-draw results.
2. Использовать chronological expanding/walk-forward split; один и тот же
   тираж не может участвовать и в обучении, и в оценке.
3. Сравнивать на одинаковом покрытии:
   - bookmaker market prior;
   - sports-only model;
   - blend, вес которого выбран только на прошлом train/validation.
4. Метрики: multiclass log loss, Brier, ECE/reliability, coverage/fallback,
   per-sport и material per-league sample sizes.
5. Sports остаётся audit-only минимум до frozen 30 drawings / 450 events и
   достаточного полного-feature coverage.
6. Влияние на package можно обсуждать только если out-of-sample blend
   воспроизводимо не ухудшает bookmaker baseline; точный activation threshold
   фиксируется до просмотра holdout.
7. До прохождения gate `p_final = p_market`, а sports snapshot используется
   только в сравнительном отчёте.

## Следующий срез после acceptance

Подключить утренний scheduler к `collect-sports-stats` и использовать последний
eligible frozen snapshot в evening probability report с явным market-only
fallback. Даже на этом шаге sports probabilities ещё не влияют на `PLAY`.
