# TOTO-SPORTS-STATS-STATUS-AUDIT

Дата аудита: 2026-07-29
Область: только фактическая реализация в репозитории и локальная БД `data/toto.db`.
Сеть не использовалась. Production-код не изменялся.

## Краткий вывод

Спортивная статистика в TotoAI реализована как отдельный **audit-only конвейер сбора доказательств**, но ещё не как часть прогнозной модели.

Сейчас она:

- умеет привязать футбольные события тиража к API-Sports;
- умеет собирать завершённые матчи команд и таблицу лиги;
- строит базовые показатели формы, результатов, голов и отдыха;
- сохраняет неизменяемые снапшоты и provenance в SQLite;
- формирует JSON/CSV/Markdown-отчёты.

Но она **не влияет** ни на вероятности `1/X/2`, ни на бриф, ни на отбор/ранжирование купонов, ни на `gross_ev`/`net_ev`, ни на решение `PLAY/NO BET`, ни на scheduler.

Практический статус: инфраструктура вертикального среза готова, пригодного источника данных и доказанной прогнозной модели пока нет. Текущий пакет рассчитывается по рыночным данным TotoBrief, а не по спортивной статистике.

Проверенные реализации:

- `src/toto_ai/sports_stats/`;
- `src/toto_ai/external_odds/`;
- `src/toto_ai/optimizer/brief.py`;
- `src/toto_ai/optimizer/coupon_probabilities.py`;
- `src/toto_ai/optimizer/direct_package.py`;
- `src/toto_ai/ev/drawing.py`;
- `src/toto_ai/package/`;
- `src/toto_ai/runner/final_input.py`;
- `src/toto_ai/runner/orchestration.py`;
- `src/toto_ai/runner/morning_dispatch.py`;
- `src/toto_ai/runner/scheduler.py`;
- `src/toto_ai/cli.py`;
- DB-модели и фактическое содержимое локальной `data/toto.db`.

---

## 1. Реализованные источники

### 1.1 TotoBrief

Используется как основной источник данных тиража:

- состав и порядок 15 событий;
- сроки тиража;
- `pool_win_1`, `pool_draw`, `pool_win_2`;
- `bk_win_1`, `bk_draw`, `bk_win_2`;
- результаты и выплаты завершённых тиражей.

Это не спортивная статистика команд. Именно TotoBrief BK/pool сейчас является фактическим входом оптимизатора.

### 1.2 API-Sports: спортивная статистика

Единственный реализованный stats-provider — `APISportsFootballStatsProvider`.

Используемые endpoint-классы:

- `/fixtures?id=...` — контекст целевого матча;
- `/fixtures?team=...&season=...&status=FT-AET-PEN...` — последние завершённые матчи команды;
- `/standings?league=...&season=...` — таблица лиги.

Поддерживается только футбол. Для другого спорта возвращается `unsupported_sport`.

### 1.3 API-Sports: внешние коэффициенты

Это отдельный конвейер `external_odds`, не stats-модель. Он собирает:

- расписание и идентичность события;
- букмекера;
- рынок;
- время обновления;
- decimal odds на `1/X/2`;
- provenance и payload hash.

Поддерживаются:

- футбол: full-time 1X2;
- хоккей: regulation-time 1X2.

Внешний odds consensus сейчас также остаётся audit-only и не заменяет TotoBrief BK в production-расчётах.

### 1.4 Reviewed schedule

`reviewed-schedule` — ручной/проверенный источник идентичности и времени матча для событий, которые API-Sports не разрешил автоматически.

Он не является источником статистики. Для таких pins намеренно не создаются фиктивные API-Sports fixture/team IDs.

---

## 2. Какие поля спортивной статистики собираются

### Целевой матч

- provider fixture ID;
- UTC start;
- provider home team ID;
- provider away team ID;
- league ID;
- season;
- признак доступности standings;
- provider/endpoint;
- request fingerprint SHA;
- payload SHA;
- `fetched_at`.

### Завершённые матчи команды

- provider fixture ID;
- UTC start;
- status: только `FT`, `AET`, `PEN`;
- home/away team IDs;
- home/away goals;
- provenance источника.

### Таблица лиги

- provider team ID;
- rank;
- points;
- played;
- wins/draws/losses;
- goals for/against;
- provenance источника.

### Вычисляемые features

По последним максимум 10 допустимым матчам каждой команды:

- число матчей;
- W/D/L;
- goals for / goals against;
- points per game;
- form points за последние пять матчей;
- timestamp последнего завершённого матча;
- rest days перед целевым матчем;
- home split: played/W/D/L/GF/GA;
- away split: played/W/D/L/GF/GA;
- опциональная строка таблицы хозяев и гостей.

Не реализованы:

- xG;
- удары, владение, опасные атаки;
- составы и подтверждённые стартовые составы;
- травмы и дисквалификации;
- индивидуальная статистика игроков;
- Elo/силовой рейтинг команд;
- стоимость состава;
- плотность календаря как отдельный feature;
- travel/weather;
- хоккейная статистика.

---

## 3. Что хранится в БД

### `sports_stats_runs`

Хранит один неизменяемый snapshot-run:

- run/content/schema ID;
- drawing ID/number/fingerprint;
- provider;
- размер запрошенной истории;
- `captured_at`, `as_of`, deadline;
- aggregate status;
- complete/partial/missing/unsupported counts;
- requests/cache hits;
- source request fingerprints;
- полный snapshot JSON.

Уникальность: `(drawing_id, drawing_fingerprint, provider, as_of)`.

### `sports_event_feature_snapshots`

Хранит результат по каждому из 15 событий:

- run/drawing/event identity и event order;
- sport/status/missing reasons;
- fixture/team/league/season/start IDs;
- feature SHA;
- полный feature JSON;
- source evidence JSON.

Уникальность:

- `(run_id, event_order)`;
- `(run_id, target_event_id)`.

### Фактическое состояние локальной БД

На момент аудита:

- `sports_stats_runs`: **3**;
- `sports_event_feature_snapshots`: **45**;
- все три запуска относятся только к тиражу **4957**;
- complete events во всех запусках: **0**;
- сохранённые home history windows: **25**;
- сохранённые away history windows: **25**;
- сохранённые standings rows: **0**.

Последний запуск:

- 15 partial events;
- 0 complete;
- 0 history windows;
- 0 standings rows;
- основная причина: `provider_plan_unavailable`;
- у одного события дополнительно `standings_unavailable`.

Следовательно, более ранние два запуска сохранили часть истории, но текущий источник не обеспечивает стабильный полный snapshot.

---

## 4. Что реально влияет на расчёт

| Слой | Фактический вход сейчас | Спортивная статистика влияет? |
|---|---|---:|
| Вероятности `1/X/2` | нормализованные `bk_*` TotoBrief | Нет |
| Мнение толпы | `pool_*` TotoBrief | Нет |
| Baseline brief | BK probability, entropy, gap top-1/top-2, слабый pool-vs-BK tie-break | Нет |
| Direct package | переданная BK probability matrix | Нет |
| Coupon probability | произведение вероятностей исходов из BK matrix | Нет |
| Coupon EV/ranking | TotoBrief BK как true probability + TotoBrief pool как crowd | Нет |
| `gross_ev` / `net_ev` | EV-модель по market/crowd inputs и стоимости | Нет |
| Package safety | структура и матрица, переданная runner | Нет |
| `PLAY/NO BET` | EV/safety/readiness/temporal gates | Нет |
| Scheduler | deadlines, readiness, external-odds collection и package runner | Нет |

Подтверждение по связям кода:

- `load_latest_eligible_snapshot(...)` реализован, но за пределами `sports_stats` не используется;
- `optimizer`, `ev`, `package` и `runner` не импортируют sports-stats features;
- `runner/final_input.py` строит probability hash из `target.events[].bk_probabilities`;
- `ev/drawing.py` фиксирует источники вероятностей как `totobrief_bk`.

Таким образом, текущие спортивные features нельзя считать частью прогнозного продукта.

---

## 5. Что является только подготовительной инфраструктурой

### Team resolution / preparation

Реализованы:

- exact drawing fingerprint;
- строгий порядок 15 событий;
- нормализация названий;
- reviewed aliases;
- sport/country/competition/league context;
- date/start/orientation matching;
- uniqueness и margin проверки;
- жёсткая граница пола команд;
- запрет частичного canonical pin set;
- API-Sports pins;
- reviewed-schedule pins.

Это решает задачу: «какому реальному матчу соответствует строка TotoBrief». Само по себе это не улучшает вероятность исхода.

### Provider-neutral contracts

Протокол provider и типизированные domain-модели позволяют позже заменить API-Sports другим источником. Пока второго stats-provider нет.

### Append-only evidence

Хэши, provenance, as-of, raw/cache проверки и immutable snapshots обеспечивают воспроизводимость исследования, но не являются прогнозной моделью.

### External odds consensus

Де-виг, медиана по букмекерам и fallback реализованы, но источник ещё не активирован в production probability path.

---

## 6. Coverage и quality gates

### 6.1 Sports-stats event gate

При сборе применяются:

- событие должно иметь корректный target pin;
- target fixture/team orientation/start должны совпасть;
- используются только завершённые `FT/AET/PEN`;
- target fixture исключается из истории;
- данные после `min(snapshot_as_of, target_start)` запрещены;
- future/non-finished/cancelled/postponed матчи исключаются;
- cache/provenance должны существовать на допустимый `as_of`;
- missing/plan-denied остаётся unknown, а не превращается в ноль.

Статусы:

- `complete`;
- `partial`;
- `missing`;
- `unsupported`.

`complete` требует обе history windows и отсутствия missing reason. Недоступные standings делают событие partial.

### 6.2 Исторический replay gate

Historical mode:

- строго cache-only;
- сеть запрещена;
- canonical RAW и sidecar должны существовать;
- hash должен совпадать;
- `fetched_at <= as_of`;
- невалидный snapshot отклоняется.

### 6.3 Sports-model activation gate

В memory-bank зафиксирована политика:

- минимум 30 тиражей;
- минимум 450 событий;
- хронологическая out-of-sample проверка;
- сравнение sports-only и ограниченного market+stats blend;
- log loss/Brier/calibration не хуже принятого baseline;
- до прохождения gate: `p_final = p_market`.

Важно: это пока **документированная политика, а не исполняемый sports activation gate в коде**.

### 6.4 External-odds coverage gate

В коде есть отдельный audit:

- минимум 30 тиражей / 450 событий;
- unique match rate не ниже 80%;
- usable consensus не ниже 70%;
- ambiguity = 0;
- explicit disposition для всех событий.

Фактическая локальная выборка:

- 6 тиражей;
- 90 событий;
- unique matches: 62/90 = **68.89%**;
- usable external consensus: 61/90 = **67.78%**;
- ambiguity consumed: 0;
- explicit dispositions: 90/90.

Статус этого gate — **PENDING**: не достигнуты ни sample floor, ни пороги coverage.

---

## 7. Команды

### Спортивная статистика

```bash
python -m toto_ai.cli collect-sports-stats \
  --open \
  --db data/toto.db \
  --provider api-sports \
  --last 10
```

Поддерживаются selectors:

- `--open`;
- `--drawing-id`;
- `--drawing-number`.

Дополнительные параметры:

- `--report-dir`;
- `--cache-root`;
- `--raw-cache-dir`;
- `--env-file`;
- `--historical-as-of`.

Команда сама маркирует результат:

- `mode: AUDIT ONLY`;
- `package_influence: NONE`;
- `fallback: MARKET ONLY`.

### External odds

```bash
python -m toto_ai.cli collect-external-odds --open
python -m toto_ai.cli audit-external-coverage --db data/toto.db --last 30
```

### Preparation / team resolution

Основные CLI:

- `prepare-drawing`;
- `sync-prepare`.

### Package / runner / scheduler

- `build-brief`;
- `ev-package`;
- `package-audit`;
- `run-drawing`;
- `scheduler-plan`;
- `scheduler-execute`;
- `morning-preanalysis-plan`;
- `morning-dispatch`.

---

## 8. Scheduler jobs

Реализованы два вида automation:

1. Утренний pre-analysis/dispatch:
   - синхронизация текущего тиража;
   - подготовка и team resolution;
   - передача exact drawing в вечерний scheduler.

2. Вечерний scheduler:
   - фазы T-45/T-30/T-20/T-16/T-12;
   - readiness/preflight;
   - prospective external-odds collection;
   - финальная генерация и публикация package либо `NO BET`.

Критический факт:

- ни утренний dispatcher, ни вечерний scheduler **не вызывают `collect-sports-stats`**;
- отдельного sports-stats scheduler job нет;
- sports stats сейчас собирается только ручной CLI-командой.

---

## 9. Текущие блокеры production-использования

### P0: нет пригодного stats source

API-Sports на текущем доступном плане не отдаёт необходимые current-season history/standings стабильно. Последний snapshot содержит ноль history windows и ноль standings.

### P0: stats не подключён к probability path

Нет функции/модели, которая преобразует features в откалиброванные `p_stats(1/X/2)`. Нет blend с `p_market`.

### P0: нет доказательства качества

Нет замороженного хронологического OOS-сравнения:

- TotoBrief BK baseline;
- sports-only;
- market + capped stats blend.

Нет доказательства улучшения log loss, Brier score, calibration либо фактических package outcomes.

### P0: слишком мало данных

В БД только:

- один уникальный тираж со sports stats;
- 45 snapshot rows;
- ноль complete event snapshots.

До минимального gate 30 тиражей / 450 событий далеко.

### P0: нет автоматического prospective collection

Sports stats не включён ни в morning pre-analysis, ни в вечерний scheduler. Даже пригодный ручной запуск не создаёт систематической prospective выборки.

### P0: mixed-provider pins несовместимы со stats collector

Canonical preparation уже поддерживает смешанный набор `api-sports + reviewed-schedule`, но `collect_and_store_sports_stats()` загружает только API-Sports pins и требует fixture/team IDs для всех событий.

Следствие: тираж с хотя бы одним reviewed-schedule pin не может быть полноценно обработан текущим stats collector.

### P1: только футбол

Хоккей и другие виды спорта остаются `unsupported`, хотя они встречаются в тотализаторе.

### P1: external odds ещё не прошёл gate

Даже отдельный odds consensus пока не имеет достаточного покрытия и sample size для promotion.

### P1: историческая data health

В memory-bank текущим P0 проекта остаётся collector/data-health lifecycle. Неполная provenance исторического корпуса ограничивает достоверность будущих backfill и OOS-исследований.

---

## 10. Фактический этап проекта

По спортивной статистике проект находится между:

1. **завершённой инфраструктурой сбора/audit evidence**;
2. **не начатой production-моделью вероятностей**.

То есть уже реализовано «как безопасно получить, проверить и сохранить данные», но ещё не реализовано и не доказано «как эти данные улучшают прогноз».

До снятия блокеров любые package/PLAY результаты нужно трактовать как market-and-pool систему, а не как спортивно-аналитическую модель.
