# TOTO-FULL-HISTORY-DATA-AUDIT — Remediation Plan

## 1. Цель и исходная точка

Этот документ не повторяет аудит. Он опирается на:

- `REPORT.md`;
- `anomalies.csv`;
- `raw_comparison.csv`;
- действующие safety-инварианты из `memory-bank/`.

Подтверждённая исходная точка:

- в SQLite есть 2 199 тиражей и по 15 позиций в каждом;
- 369 завершённых тиражей не имеют полного набора терминальных результатов;
- отсутствуют 754 результата отдельных событий;
- 215 тиражей содержат непригодный pool `0/0/0` во всех 15 событиях;
- для 2 184 тиражей нет локального RAW/detail evidence;
- immutable result snapshots есть только у 4 тиражей;
- settlements отсутствуют.

Цель исправления — не «заполнить NULL любой ценой», а построить проверяемый
жизненный цикл данных:

```text
обнаружение тиража
-> immutable RAW snapshot
-> контролируемый импорт
-> data-health classification
-> reconciliation/backfill
-> допуск или запрет для генерации/бэктеста
-> terminal results/VOID
-> settlement
-> post-draw report
```

История не считается полностью восстановленной, пока это не подтверждено
field-level provenance. Неизвестное значение нельзя угадывать, выводить из
счёта без подтверждённого правила или автоматически считать `VOID`.

## 2. Неподвижные safety-инварианты

1. **RAW first.** Любой принятый ответ TotoBrief сначала сохраняется как
   неизменяемый canonical RAW с SHA-256, временем получения, endpoint и точной
   identity тиража. Только после durable archive разрешена мутация SQLite.
2. **Append-only evidence.** Новый ответ не перезаписывает старый RAW или
   result snapshot. Повтор идентичного payload идемпотентен по hash.
3. **No destructive downgrade.** `null`, пустая строка и `0/0/0` из более
   слабого/старого payload не стирают ранее подтверждённое значение.
4. **Finished means terminally reconciled only with evidence.** Статус
   `finished` сам по себе не означает 15 готовых результатов.
5. **Exactly 15 positions.** Для аналитической пригодности обязательны
   уникальные event orders `0..14`, стабильная drawing identity и отсутствие
   конфликтующих event identities.
6. **Unknown is not VOID.** Отсутствующий результат остаётся
   `unknown/pending_source`; `void/cancelled` принимается только из
   авторитетного payload либо из отдельного reviewed evidence с provenance.
7. **`0/0/0` is invalid pool.** Ненулевой факт наличия строки `quotes` не
   считается доказательством пригодности вероятностей.
8. **Fail closed.** Нездоровый тираж исключается из соответствующего
   бэктеста/генерации/settlement; причина сохраняется машинно-читаемо.
9. **No future leakage.** Исторический прогноз использует только snapshot,
   полученный до соответствующего дедлайна. Финальный payload нельзя выдавать
   за pre-match input.
10. **No profitability claim without settlements.** Hit rate, payout, profit и
    ROI — разные метрики. ROI не вычисляется без фактических payout evidence.

## 3. Full-history data-health contract

Нужен один чистый доменный классификатор с версионируемым контрактом, а не
несколько несовпадающих проверок.

### 3.1 Проверки на уровне тиража

Контракт возвращает:

- `health_schema_version`;
- drawing ID/number/status/deadline;
- статус каждого обязательного компонента;
- список reason codes;
- field-level provenance/recoverability;
- отдельные eligibility-флаги для разных задач.

Обязательные компоненты:

| Компонент | Условие здоровья |
|---|---|
| Structure | ровно 15 уникальных orders `0..14` |
| Identity | непустые стабильные имена/identity всех событий |
| Pool | 15 полных положительных троек; `0/0/0` запрещён |
| BK | 15 полных положительных троек |
| Pre-match provenance | для исторического прогноза snapshot получен до дедлайна |
| Results | для finished-тиража 15 терминальных состояний |
| Result evidence | immutable snapshot либо эквивалентная hash-bound provenance |
| Package evidence | canonical archive, не rehearsal |
| Settlement | package и terminal result snapshot связаны hash-ами |

Проверка вероятностной тройки должна учитывать формат источника
(проценты/коэффициенты), конечность, положительность и допустимую
нормализацию. Нельзя считать пропущенную тройку валидной только потому, что
helper пропустил её при расчёте суммы.

### 3.2 Раздельные допуски

- `eligible_for_live_generation`:
  текущая identity 15/15, свежие валидные pool/BK, все live safety gates.
- `eligible_for_probability_backtest`:
  15 валидных pre-deadline probability inputs + 15 terminal results.
- `eligible_for_result_only_research`:
  identity 15/15 + 15 terminal results; pool/BK могут отсутствовать.
- `eligible_for_settlement`:
  canonical actionable package archive + terminal result snapshot +
  проверенное правило обработки VOID.
- `eligible_for_roi`:
  settlement + фактические выплаты/таблица выплат.

Один флаг `healthy` недостаточен: тираж может быть пригоден для исследования
исходов, но непригоден для probability backtest.

### 3.3 Терминальные результаты

Нужна явная модель:

- `pending_source` — источник ещё не отдал результат;
- `decided_1`, `decided_x`, `decided_2`;
- `void` — событие признано недействительным для расчёта;
- `cancelled`/`postponed` — состояние матча, которое **не переводится
  автоматически** в `void` без правила TotoBrief/BaltBet;
- `conflict` — два authoritative snapshots расходятся;
- `unknown_legacy` — историческое значение невозможно подтвердить.

Храним отдельно:

- source event status;
- итоговый toto outcome;
- settlement treatment;
- evidence source/hash/time;
- rule/version, преобразовавшую source status в settlement treatment.

До документального подтверждения правил BaltBet по отменам такие события
могут считаться terminal для data inventory, но не допускаются к денежному
settlement.

## 4. Классификация восстановления

### 4.1 Можно восстановить офлайн из локального RAW

Класс `importer_loss`:

- локальный RAW/result snapshot содержит однозначное поле;
- SQLite его не содержит либо содержит менее полное значение;
- payload проходит identity/hash/schema проверки.

Действия:

1. читать RAW только через общий валидатор;
2. выполнить dry-run diff;
3. импортировать names/championship/sport/quotes/results/status/payments,
   доступные в payload;
4. не стирать более сильные значения;
5. записать repair provenance и before/after hashes;
6. повторный запуск обязан дать zero changes.

По текущему аудиту сюда относятся подтверждённые class-A случаи, в частности
полные локальные payload для 4954–4956. Восстанавливается только то, что
реально присутствует в RAW.

### 4.2 Требует будущего повторного обращения к TotoBrief

Классы:

- `source_missing_at_snapshot`: локальный RAW был сделан до появления
  результатов либо уже неполон;
- `no_local_evidence`: локального RAW нет, поэтому нельзя отличить source gap
  от старой потери импорта;
- visible number gaps 3843/3844 — сначала нужно проверить, существовали ли
  такие тиражи в authoritative listing; нельзя создавать строки по одному
  числовому разрыву.

Будущий network backfill:

- отдельная explicit-команда, никогда не запускаемая неявно из backtest;
- приоритет: новые finished gaps → class B → class C от новых к старым;
- bounded batches, rate limit, server `Retry-After`, exponential backoff;
- checkpoint/resume после каждого drawing;
- idempotency по `(drawing_id, endpoint, payload_sha256)`;
- каждый 2xx payload сначала попадает в immutable RAW;
- итог каждой попытки: `repaired`, `source_still_missing`,
  `source_not_found`, `conflict`, `retryable_error`, `terminal_error`;
- сеть/429/5xx не превращаются в `source_missing`;
- прерывание процесса не оставляет частично опубликованный импорт.

### 4.3 Может остаться навсегда неизвестным

Если после контролируемого backfill authoritative source:

- больше не хранит тираж;
- возвращает неполный результат;
- не позволяет доказать VOID;
- конфликтует без достаточного evidence;
- не даёт pre-deadline snapshot для исторической вероятностной модели,

поле получает `unknown_legacy`/`source_unrecoverable` с evidence последней
попытки. Такие тиражи:

- не «чинятся» синтетическими значениями;
- исключаются из standard backtest и ROI;
- могут использоваться только в явно разрешённом partial research;
- всегда учитываются в denominator отчёта о покрытии истории.

Финальный post-draw RAW не может восстановить потерянный pre-match pool:
результаты восстановятся, но честный historical probability backtest всё
равно останется невозможным.

## 5. Исправления по компонентам

## P0 — доверие к данным и прекращение новых потерь

### P0.1 Data-health domain и read-only CLI

Сначала тестами зафиксировать контракт и известные дефекты:

- complete healthy fixture;
- 14/15 result;
- missing-all-results;
- explicit VOID;
- cancelled без settlement rule;
- blank names;
- missing quote row;
- pool `0/0/0`;
- BK incomplete;
- result conflict;
- pre-deadline и post-deadline snapshots;
- package rehearsal vs actionable archive.

Затем реализовать один модуль и CLI:

```text
toto-ai data-health --db ... [--number N|--all] [--json ...] [--strict]
```

`--strict` завершает процесс ненулевым кодом при наличии hard failures.
Контракт должен использоваться будущими gates, а не быть только отчётом.

### P0.2 Collector freshness

Red tests:

1. active drawing с 15 events и quotes после перехода summary в `finished`
   обязательно требует detail refresh;
2. finished drawing с 14/15 terminal results требует refresh;
3. finished drawing с 15 terminal results и valid immutable snapshot не
   требует fetch без явного force;
4. `0/0/0` не удовлетворяет quote freshness;
5. network failure не отмечает drawing как reconciled.

Новая freshness-модель учитывает lifecycle:

- active: structure + required current input freshness;
- finished: structure + terminal result completeness + immutable result
  evidence;
- status transition в `finished` всегда инициирует result reconciliation.

### P0.3 Полноценный finished-result importer

Finished-result path должен использовать общий full-detail parser/upsert:

- восстанавливать names/championship/sport;
- восстанавливать pool/BK и другие реально присутствующие quotes;
- импортировать results/scores/source statuses/payments;
- сохранять immutable RAW и result snapshot;
- обновлять SQLite одной транзакцией после archive;
- применять field-strength merge, не destructive overwrite.

TDD:

- fixture 4954–4956 типа «SQLite shell + полный RAW»;
- null/zero payload не стирает good data;
- повторный импорт идемпотентен;
- ошибка после RAW, но до commit безопасно возобновляется;
- identity mismatch блокирует весь импорт;
- 14 results + 1 reviewed VOID дают complete только при валидном evidence.

### P0.4 RAW-first immutable archive

Ввести единый repository/service:

- canonical payload bytes;
- SHA-256;
- endpoint/request identity;
- fetched/retrieved time;
- drawing identity;
- as-of phase (`listing`, `pre_match`, `post_draw`);
- atomic write + fsync + commit marker;
- immutable index in SQLite.

Никакой normal collector/result refresh не должен мутировать analytical
tables, если archive не подтверждён.

### P0.5 Gates

Подключить data-health contract:

- historical backtests по умолчанию выбирают только
  `eligible_for_probability_backtest`;
- live generation требует `eligible_for_live_generation`;
- settlement требует `eligible_for_settlement`;
- override разрешён только явным diagnostic-флагом, отражается в отчёте и
  никогда не становится production PLAY.

Вывод каждой команды содержит:

- total considered;
- eligible;
- excluded by reason;
- health schema/version;
- hashes входных snapshots.

## P1 — восстановление истории и ежедневная reconciliation

### P1.1 Offline repair из локального RAW

Сначала dry-run manifest для всех class-A полей, затем отдельное подтверждаемое
применение. Acceptance: все однозначно recoverable class-A поля восстановлены,
zero destructive changes, повторный запуск — no-op.

### P1.2 Targeted network backfill

Реализовать после P0 и отдельно протестировать с fake provider:

- rate limiting и `Retry-After`;
- resume/checkpoint;
- crash between archive and SQL commit;
- duplicated payload;
- stale pre-result payload;
- 404/not found;
- 429/5xx/timeout;
- source payload with conflict;
- bounded batch and daily request budget.

Первый production run — малый canary batch с dry-run comparison, затем
постепенное расширение. Полный диапазон нельзя запускать одной
неконтролируемой командой.

### P1.3 Source-missing vs importer-loss ledger

Каждое проблемное поле получает одну классификацию:

- `healthy`;
- `importer_loss_recoverable_local`;
- `source_missing_at_snapshot`;
- `network_recheck_required`;
- `source_still_missing`;
- `source_not_found`;
- `conflict`;
- `source_unrecoverable`.

Классификация всегда содержит evidence hash/path/request attempt. Отсутствие
evidence не может классифицироваться как `source_missing`.

### P1.4 Nightly reconciliation

Ночная задача:

1. синхронизирует listing;
2. обнаруживает новые номера и lifecycle transitions;
3. архивирует detail каждого нового/изменившегося тиража;
4. приоритетно обновляет недавно завершённые до terminal 15/15;
5. bounded batch обрабатывает historical backlog;
6. повторяет incomplete source responses по расписанию;
7. запускает data-health;
8. инициирует settlement только для canonical actionable packages;
9. публикует machine-readable daily report.

Это отдельная non-betting automation. Её сбой не должен активировать вечернюю
ставочную автоматику.

## P2 — settlements, наблюдаемость и доказательство качества

### P2.1 Settlement lifecycle

- canonical package archive создаётся до ручной загрузки;
- статус пакета различает `generated`, `approved_for_manual_upload`,
  `confirmed_placed`, `rehearsal`;
- только `confirmed_placed` участвует в фактическом bankroll/ROI;
- после terminal result snapshot пакет рассчитывается идемпотентно;
- сохраняются hit distribution, best hits, категории, fixed misses,
  VOID treatment/version;
- payout/profit/ROI остаются `unknown`, если нет подтверждённой выплаты.

Rehearsal/simulation package никогда не считается реальной ставкой.

### P2.2 Обязательный post-draw report

Для каждого сформированного actionable package:

- какой input snapshot использован;
- что прогнозировалось;
- actual/VOID;
- hit/category distribution;
- ожидаемый EV до события;
- известная выплата и ROI либо явное `payout_unknown`;
- fixed single misses и concentration errors;
- причины расхождения;
- изменения стратегии допускаются только после накопления prospective sample.

### P2.3 Контрольная панель здоровья

Ежедневные и full-history метрики:

- drawings discovered / expected listing coverage;
- 15-event structure coverage;
- valid pool/BK coverage;
- terminal result coverage;
- immutable RAW coverage;
- immutable result snapshot coverage;
- pre-deadline snapshot coverage;
- unresolved by reason and age;
- archived/placed/settled package counts;
- settlement latency;
- source/API failure rates;
- number of destructive downgrades prevented;
- backtest eligible corpus size by year/version.

## 6. Acceptance thresholds

### P0 acceptance

- 100% известных fixtures для missing result, blank names, missing quotes,
  `0/0/0`, VOID и conflict правильно классифицируются.
- Ни один finished drawing с <15 terminal outcomes не получает
  `eligible_for_probability_backtest=true`.
- Ни одна pool-тройка `0/0/0` не считается валидной.
- Любая SQL-мутация из source detail имеет предварительный immutable RAW hash.
- Полный importer восстанавливает 100% однозначных class-A полей из доступного
  локального RAW.
- Повторный импорт того же payload создаёт 0 новых logical changes.
- Existing live `15/15` safety boundary и passive scheduler не ослаблены.
- Все unit/integration tests и Ruff проходят.

### P1 acceptance

- 100% сетевых попыток имеют durable attempt/evidence record.
- После искусственного interruption backfill продолжает с checkpoint и не
  дублирует snapshots/imports.
- 429/5xx/timeout никогда не классифицируются как source absence.
- Каждый backlog item заканчивает batch в явном состоянии, без silent skip.
- Новые finished-тиражи автоматически попадают в reconciliation; при
  доступном полном source payload terminal snapshot появляется не позднее
  следующего успешного nightly run.
- Полный health report до/после backfill показывает изменения по причинам, а
  не только общий процент.

Нельзя установить требование «100% исторических тиражей восстановлены»:
authoritative source может уже не содержать старые данные. Требование —
100% явная классификация и отсутствие синтетического заполнения.

### P2 acceptance

- 100% `confirmed_placed` packages получают settlement после появления
  terminal authoritative results.
- 0 rehearsal packages учитываются как реальные ставки.
- 0 ROI значений вычисляется без payout evidence.
- Каждая settlement запись воспроизводима по package/result hashes и rule
  version.
- Каждая новая стратегия сравнивается только на health-eligible corpus и
  отдельно на prospective packages.

## 7. Порядок TDD-реализации

Каждый шаг — отдельный небольшой change set:

1. **Characterization tests** на текущих дефектах без изменения поведения.
2. **Data-health contract + read-only CLI.**
3. **Collector lifecycle freshness.**
4. **RAW-first archive boundary.**
5. **Full-detail finished importer + offline class-A repair.**
6. **Backtest/live/settlement gates.**
7. **Network backfill engine** с fake provider, затем canary.
8. **Nightly reconciliation.**
9. **Settlement completion и post-draw reports.**
10. **Full-history re-audit** только после реализации, как acceptance, а не
    вместо тестов.

Для каждого шага:

- сначала failing tests;
- затем минимальная реализация;
- unit + integration + migration tests;
- fault-injection для atomicity/resume;
- pytest + Ruff;
- обновление memory-bank после подтверждённого результата.

## 8. P0 / P1 / P2 в одном списке

### P0

1. Версионируемый full-history data-health contract.
2. Запрет `0/0/0` как valid pool.
3. Lifecycle-aware collector freshness для finished results.
4. RAW-first immutable archive.
5. Full-detail finished-result importer.
6. Offline восстановление однозначных class-A потерь.
7. Data-health gates для backtest/generation/settlement.

### P1

1. Rate-limited resumable targeted TotoBrief backfill.
2. Evidence-backed classification source missing vs importer loss.
3. Nightly listing/detail/result reconciliation.
4. Result snapshot coverage и backlog reporting.

### P2

1. Complete package settlement lifecycle.
2. VOID/cancelled rule registry после подтверждения правил BaltBet.
3. Обязательный post-draw разбор каждого actionable package.
4. Health/settlement dashboard и prospective quality gates.

## 9. Единственная следующая implementation task

### `TOTO-DATA-HEALTH-CONTRACT-V1`

Реализовать **только** чистый версионируемый data-health contract и read-only
CLI `data-health`, начиная с characterization tests.

В эту задачу не включать:

- сетевой backfill;
- мутацию исторической базы;
- изменение collector;
- settlement;
- scheduler;
- новый оптимизатор.

Результат задачи должен:

1. однозначно классифицировать structure, names, pool, BK, results,
   provenance и package evidence;
2. считать `0/0/0` invalid;
3. различать eligibility для live generation, probability backtest,
   result-only research и settlement;
4. выдавать стабильные reason codes и JSON/CLI summary;
5. зафиксировать тестами все известные классы дефектов из аудита.

Это единственный безопасный следующий шаг: сначала формализовать, какие данные
мы считаем пригодными, и только затем разрешать автоматике их восстанавливать
или использовать.
