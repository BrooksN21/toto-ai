# TOTO-REVIEWED-SCHEDULE-FALLBACK: контекст

Собрано 2026-07-29 только из standalone-репозитория
`/Users/turshevr/toto-ai`.

## Границы задачи

- Task id: `TOTO-REVIEWED-SCHEDULE-FALLBACK`.
- Это только сбор и анализ контекста.
- Прочитаны корневой `AGENTS.md`, все `memory-bank/*.md` и текущая
  реализация pin/preparation/revalidation/scheduler/external odds.
- Не использовались Arcadia, Yandex, Gena, внутренние skills или внешняя
  проектная память.
- Не выполнялись Git-команды, commit, push, установка scheduler или сетевые
  действия.
- Код проекта не изменялся. Единственный созданный файл — этот handoff.

## Зачем нужен fallback

Текущий production-контур намеренно fail-closed и способен подготовить тираж
только при точном разрешении всех 15 событий одним API-Sports provider:

- тираж 4958 остановился на `14/15`, потому что API-Sports не содержал женский
  матч Huracán Women — River Plate Women;
- тираж 4959 остановился на `14/15`, потому что API-Sports не содержал Iceland
  3. Deild, КВ Вестурбеяр — Рейнир Сандгерди;
- для 4959 это event order `8` в коде и матч №9 в пользовательском интерфейсе;
- resolver правильно вернул `source_missing_competition`, не создал фиктивный
  API-Sports fixture и не опубликовал частичные pins.

Roadmap уже фиксирует следующий незавершённый шаг: добавить законный
provider-neutral schedule fallback. Там же явно сказано, что подтверждение на
официальном сайте и независимом публичном источнике ещё не является provider
pin и не должно выдаваться за API-Sports fixture.

## Обязательные действующие инварианты

Новая реализация не должна менять эти правила:

1. **Atomic 15/15 preparation**
   - READY публикует ровно 15 event pins с orders `0..14`;
   - любой unresolved/ambiguous/failure публикует ноль authoritative pins;
   - partial `14+1` нельзя собирать последовательными `write_pin()`;
   - готовый pin set публикуется одной транзакцией.

2. **Exact target binding**
   - drawing internal ID, visible number, deadline, target fingerprint,
     target event ID и event order должны совпадать;
   - изменение target fingerprint инвалидирует старые pins;
   - fallback не может быть drawing-specific условием по номеру тиража.

3. **No invented identity**
   - нельзя придумывать API-Sports fixture/team IDs;
   - нельзя записывать reviewed evidence с `provider="api-sports"`;
   - reviewed alias или provider team ID подтверждает только team identity,
     но не существование конкретного fixture;
   - normalization/transliteration/fuzzy names не авторизуют fallback.

4. **Conservative resolver**
   - sport, country, competition/league level, gender/age class, date,
     orientation и pair uniqueness остаются обязательными;
   - `source_missing_competition` остаётся non-match;
   - ambiguous API-Sports result нельзя “исправить” reviewed fallback;
   - transport/date/quota failure нельзя выдавать за доказанное отсутствие
     события у API-Sports.

5. **Final revalidation**
   - PLAY разрешён только после повторной точной проверки всех 15 pins;
   - проверяются source/provider identity, fixture identity, team identity,
     orientation, start time, freshness и полное получение required dates;
   - missing/stale/changed/conflicting evidence означает NO BET;
   - TotoBrief BK fallback после identity failure остаётся только
     диагностическим и не авторизует PLAY.

6. **Scheduler boundary**
   - morning dispatcher остаётся passive по умолчанию;
   - evening activation запрещена до activation-disabled live 15/15 drill;
   - `_ineligibility_reason()` по-прежнему требует READY, mapped `15`,
     playable и обычный двухдневный span;
   - новый fallback должен сделать preparation действительно READY, а не
     обходить morning/scheduler gate.

7. **Timing override is not fixture evidence**
   - `timing_overrides.py` может дополнить только время;
   - timing override не доказывает fixture/team/orientation и не может
     закрывать отсутствующий pin.

## Текущая архитектура и ограничения

### Domain/provider contract

`src/toto_ai/external_odds/domain.py`

- `ProviderEvent` уже содержит provider, provider event ID, sport, league,
  start, teams, fetch time, payload hash и optional provider team IDs.
- `ExternalOddsProvider` формально provider-neutral, но объединяет две
  способности одного provider:
  - `fetch_schedule()`;
  - `fetch_event_markets()`.
- Весь operational orchestration фактически предполагает один provider client
  и один `provider_name`.

Следствие: простого добавления второго `ProviderEvent` недостаточно. Текущий
collection попытается получить schedule и markets всех pins через один client.

### Team resolution

`src/toto_ai/external_odds/team_resolution.py`

- `ResolutionContext` содержит один provider.
- Candidate принимается только при `candidate.provider == context.provider`.
- Контекст проверяет sport/date/gender/country/competition/team evidence.
- Provider IDs и reviewed contextual aliases имеют приоритет.
- Missing competition остаётся отдельным unresolved status.

Этот resolver должен остаться строгим для API-Sports. Reviewed schedule
evidence лучше валидировать отдельным exact parser/adapter, а не ослаблять
fuzzy thresholds существующего resolver.

### Preparation

`src/toto_ai/external_odds/preparation.py`

- `fetch_preparation_schedule()` вызывает один provider client по датам,
  накапливает candidates и после каждой успешной даты повторяет resolution.
- `prepare_drawing()`:
  - загружает/проверяет ready pins одного provider;
  - фильтрует candidates по одному provider;
  - создаёт pin specs с одинаковым `provider`;
  - READY возможен только при 15 matched, playable timing и отсутствии
    required-date failures;
  - иначе пишет unresolved diagnostics и ноль pins.
- Reuse готовых pins также ищет все fixture IDs в candidates того же provider.
- Readiness summary содержит probability hash и target fetch time, но не
  provider distribution, reviewed evidence IDs или catalog hash.
- `load_local_schedule()` может прочитать normalized events, но присваивает им
  переданный единый provider. Использовать это для маскировки reviewed source
  под API-Sports нельзя.

### Pin/preparation persistence

`src/toto_ai/db/models.py`
`src/toto_ai/external_odds/team_registry.py`

- `DrawingEventPin.provider` сейчас одновременно означает:
  - namespace authoritative pin set;
  - реальный source provider конкретного fixture.
- Pin uniqueness:
  - drawing/fingerprint/event/order/provider;
  - drawing/fingerprint/provider/provider_fixture_id.
- `DrawingPreparation` также имеет один provider и uniqueness
  `(drawing_id, drawing_fingerprint, provider)`.
- `load_drawing_pins()` и `load_ready_drawing_pins()` выбирают все 15 rows по
  одному provider.
- `publish_drawing_preparation()` атомарен, но удаляет/публикует rows только в
  namespace одного provider.
- `write_pin()` технически может создавать отдельные rows, но не создаёт
  authoritative ready preparation и не должен применяться для fallback.

Следствие: база может физически хранить pins с разными providers, но текущий
authoritative preparation/load contract не умеет считать их одним готовым
15-event set.

### Eligibility

`src/toto_ai/external_odds/eligibility.py`

- Timing sources: `totobrief`, `provider`, `unresolved`.
- Eligibility считает общий `provider_count`, не различая provider names.
- Это допустимо для календарной классификации, если reviewed schedule остаётся
  внешним provider timing, но точный source должен сохраняться отдельно в pin
  и revalidation provenance.

### Prospective collection and final revalidation

`src/toto_ai/external_odds/collection.py`
`src/toto_ai/external_odds/prospective.py`

- Prepared pins должны содержать ровно 15 orders.
- Required dates строятся из start каждого pin.
- Все даты запрашиваются через один `ExternalOddsProvider`.
- `_match_targets_from_pins()` для каждого pin требует:
  - exact drawing/fingerprint/event binding;
  - exact provider fixture ID;
  - `candidate.provider == pin.provider`;
  - oriented provider team IDs;
  - start difference не более действующего tolerance;
  - schedule age не более `PIN_SCHEDULE_MAX_AGE`;
  - отсутствие required-date failures.
- При stale/missing/changed identity markets вообще не запрашиваются.
- `_pinned_revalidation_summary()` выводит exact 15-event summary и
  `ready_for_play`.
- `pinned_revalidation_is_ready()` требует expected=15, matched=15 и ready.
- Snapshot имеет один top-level provider.
- После успешного match collection пытается получить market по тому же
  provider fixture ID.
- Если market consensus недоступен, event может использовать явный
  `TOTOBRIEF_BK_FALLBACK`.

Следствие: mixed-provider pins потребуют source-aware schedule revalidation.
Для reviewed schedule-only provider нельзя вызывать API-Sports odds с reviewed
fixture ID; probabilities должны остаться explicit TotoBrief BK fallback.

### Runner/scheduler

`src/toto_ai/cli.py`
`src/toto_ai/runner/morning_dispatch.py`
`src/toto_ai/runner/orchestration.py`
`src/toto_ai/runner/scheduler.py`
`src/toto_ai/runner/reports.py`

- CLI `prepare-drawing`, `morning-dispatch`, `run-drawing` и scheduler plan
  принимают только literal `api-sports`.
- `_prepare_current_for_morning()` создаёт только `APISportsClient`.
- `_prepare_runner_resources()` загружает ready pins только с
  `provider="api-sports"`.
- Runner останавливается до timing/audit/EV, если final pinned revalidation не
  ready 15/15.
- Scheduler preflight требует API key, запускает `prepare-drawing --open` и
  отклоняет любой non-ready exit.
- `SchedulerPlan.semantic_payload()` связывает provider, aliases и optional
  timing override path, но не reviewed schedule catalog.
- Generated prepare/final commands не передают schedule evidence path.
- Manifest parser строго проверяет exact pinned-revalidation fields и
  самостоятельно пересчитывает `ready_for_play`.
- Текущий exact schema не допускает незаявленные provider/evidence fields:
  расширение требует явного schema change, а не “тихого” добавления JSON keys.
- Morning persisted identity не содержит preparation evidence/catalog hash.

## Безопасный provider-neutral дизайн

### 1. Отделить pin-set identity от source-provider identity

Нельзя продолжать использовать одно поле `provider` сразу в двух смыслах.
Безопасный контракт:

- один authoritative `DrawingPreparation` представляет exact preparation set;
- каждый из 15 pins хранит собственный `source_provider`;
- pins связываются с preparation через `preparation_id` или immutable
  `pin_set_id`;
- loader выбирает pins по exact preparation set, а не по одному provider;
- API-Sports-only existing rows мигрируются/считаются одним homogeneous set;
- fixture uniqueness проверяется по `(source_provider, source_fixture_id)`,
  а event orders всё равно обязаны быть exact `0..14`.

Не рекомендуется скрывать mixed sources под fake provider
`api-sports`, `composite` или `provider-neutral` только в provenance. Реальный
source должен быть first-class и входить в pin hash.

### 2. Выделить schedule evidence из odds provider

Нужен provider-neutral schedule/revalidation boundary, независимый от markets:

- schedule evidence provider/adapter:
  - перечисляет schedule records;
  - revalidates exact pinned fixture;
  - сообщает freshness и source provenance;
- optional market provider capability:
  - имеется у API-Sports;
  - отсутствует у reviewed schedule source.

API-Sports adapter сохраняет текущую логику. Reviewed source становится
отдельным adapter/provider, а не специальным условием для 4958/4959.

### 3. Строгий reviewed schedule catalog

Минимально безопасный reviewed fallback должен иметь отдельный strict JSON
catalog по образцу `timing_overrides.py`, но с fixture identity, а не только
временем.

На record нужны как минимум:

- schema version и unique evidence ID;
- exact drawing ID или number;
- exact target fingerprint;
- event order и target event ID;
- sport, competition/league и gender/age class;
- exact home/away orientation;
- starts_at UTC;
- source fixture/team IDs, если источник их публикует;
- fixture status (`scheduled`/equivalent; postponed/cancelled запрещены);
- reviewer и reviewed_at;
- captured_at/fetched_at;
- один или несколько HTTPS source refs;
- captured source payload/content SHA-256;
- stable source/provider name;
- expiry/freshness policy.

Для production PLAY рекомендуется требовать согласие:

- официального competition/federation source;
- независимого публичного source.

Оба claims должны совпасть по паре, orientation, competition и start. Один URL
без зафиксированного content hash недостаточен. Если source не даёт устойчивых
fixture/team identifiers, это ограничение должно быть явно отражено в
reviewed-evidence identity; нельзя выдавать name-derived value за native
provider ID. Если строгую identity доказать нельзя, record остаётся
диагностическим и не закрывает 15/15.

Parser должен:

- отклонять duplicate JSON keys и неизвестные поля;
- канонически сортировать/хешировать semantic content;
- отклонять duplicate evidence/target/source claims;
- строго проверять UTC, freshness, HTTPS, drawing/fingerprint/event identity;
- отклонять contradictory sources и source data из будущего;
- поддерживать pin-at-preflight и reload/compare для TOCTOU защиты.

`timing_overrides.py` можно использовать как реализационный образец, но не как
сам fallback storage.

### 4. Fallback admission policy

Порядок preparation:

1. Получить полный bounded API-Sports schedule и применить текущий strict
   resolver без изменений.
2. Fallback разрешать только для отдельных targets, для которых:
   - required API-Sports dates успешно получены;
   - resolver доказал source absence (`source_missing_competition` или
     эквивалентный exact missing результат);
   - нет ambiguity, transport/date/quota failure или competing provider
     candidate.
3. Найти ровно один strict reviewed evidence record exact target.
4. Проверить catalog freshness, source agreement и отсутствие конфликта с
   API-Sports.
5. Сформировать единый mixed-source draft из 15 pin specs.
6. Опубликовать весь set одной транзакцией только при exact 15/15 и playable
   eligibility; иначе опубликовать ноль pins.

Нельзя использовать reviewed fallback, чтобы маскировать:

- API outage;
- quota exhaustion;
- failed required date;
- ambiguous pair;
- gender/competition mismatch;
- stale or changed evidence.

### 5. Source-aware final revalidation

Final revalidation должен группировать pins по `source_provider`:

- API-Sports pins:
  - действующая fresh schedule revalidation без name rematching;
  - fixture/team/orientation/start/date checks без ослабления.
- Reviewed schedule pins:
  - strict reload catalog;
  - exact record/drawing/fingerprint/event/source identity;
  - exact fixture/team/orientation/start/status;
  - fresh `captured_at` в пределах явного max age;
  - semantic/content hashes и source refs;
  - no conflict/no newer contradictory claim;
  - catalog TOCTOU equality внутри final attempt.

Aggregation снова выдаёт ровно 15 per-event results. PLAY возможен только если
все source adapters успешно revalidated свои pins. Для reviewed schedule-only
event market fetch пропускается, а probability source явно остаётся TotoBrief
BK. Это допустимо только потому, что fixture pin успешно revalidated; BK не
заменяет identity gate.

Pinned-revalidation schema нужно расширить или version-bump, добавив как
минимум:

- per-event `source_provider`;
- `revalidation_method`;
- evidence/record ID и semantic hash;
- provider distribution;
- reviewed evidence freshness/integrity booleans;
- aggregate evidence/catalog hash.

Scheduler должен продолжать самостоятельно выводить `ready_for_play` из exact
15 rows и всех boolean checks.

### 6. Scheduler/runner binding

Reviewed schedule catalog path/policy необходимо провести через:

- `MorningDispatchConfig`;
- `SchedulerPlan` и его semantic payload/plan ID;
- generated `prepare-drawing` command;
- generated `run-drawing` command;
- runner protected input paths;
- final input snapshot;
- runner manifest/report;
- durable archive и scheduler manifest parser.

Morning preparation evidence и persisted dispatch record должны содержать
immutable preparation/pin-set hash и reviewed evidence identity. Иначе старый
scheduled plan может быть повторно использован после замены catalog.

При final phase catalog надо:

1. строго загрузить и pin его semantic hash;
2. выполнить source-aware revalidation;
3. перед publication повторно загрузить и сравнить semantic hash;
4. сохранить exact final catalog/evidence hash в manifest/archive.

Missing, changed, expired или malformed catalog означает NO BET. Не следует
ослаблять `_ineligibility_reason()`, scheduler preflight или runner
`pinned_revalidation_is_ready()`.

## Рекомендуемая декомпозиция реализации

Это не реализация, а безопасные границы будущих изменений.

1. **Reviewed schedule contract**
   - новый strict catalog parser/canonical hash/pin/reload;
   - только validators и adversarial tests;
   - без влияния на preparation или PLAY.

2. **Mixed-source persistence**
   - отделить preparation set от pin source provider;
   - additive migration/backward compatibility;
   - exact atomic publish/load/invalidate tests.

3. **Preparation fallback**
   - API-Sports first;
   - reviewed evidence только после доказанного source absence;
   - one atomic 15/15 publish or zero.

4. **Provider-aware revalidation**
   - adapter registry;
   - API-Sports path unchanged;
   - reviewed catalog revalidation;
   - schedule-only event skips external market request and uses explicit BK
     fallback.

5. **Scheduler/CLI/schema binding**
   - catalog path/hash in plan/final snapshot/manifest/archive;
   - exact schema versioning and strict parser updates;
   - no silent optional fields.

6. **Acceptance**
   - sanitized 4958 women and 4959 Iceland regressions;
   - all-API-Sports regression unchanged;
   - activation-disabled live 15/15 drill;
   - only после него можно отдельно рассматривать evening activation.

## Обязательные тесты

- 14 API-Sports + 1 valid reviewed source atomically produces one 15-pin set.
- Та же подготовка без reviewed record produces zero pins.
- Partial/malformed/duplicate-key/tampered catalog produces zero pins.
- Wrong drawing/fingerprint/event/order produces zero pins.
- Reversed home/away, wrong competition, wrong gender/age or conflicting start
  produces zero pins.
- Reviewed record cannot replace ambiguous API-Sports candidate.
- Reviewed record cannot mask failed API schedule date/quota/transport.
- Duplicate fixture identity is checked within source namespace.
- Mixed-source ready load returns exact orders `0..14`.
- Existing API-Sports-only ready preparation remains compatible.
- Final API pin change, reviewed record change, stale capture, source conflict,
  catalog TOCTOU or missing record each yields `ready_for_play=False`.
- Market fetch is never called for a schedule-only reviewed fixture ID.
- Reviewed event receives explicit TotoBrief BK probability provenance.
- Manifest parser independently rejects inconsistent aggregate readiness.
- Scheduler plan/artifact/final archive reject catalog path/hash tampering.
- Morning remains deferred unless preparation is real READY 15/15/playable.
- No EV/package/marker is produced for any failed fallback case.

## Основные риски

1. **Ложная fixture identity.**
   Две похожие команды или один URL не доказывают конкретный матч.

2. **Подмена API-Sports identity.**
   Fake fixture/team IDs или `provider="api-sports"` для reviewed data
   уничтожат смысл final revalidation.

3. **Stale/rescheduled/cancelled fixture.**
   Morning evidence может устареть к final. Нужен explicit max age, status и
   повторная проверка.

4. **TOCTOU catalog mutation.**
   Файл может измениться между preflight, collection и publication.

5. **Overloading provider field.**
   Текущее поле одновременно задаёт pin-set namespace и source provider.
   Скрытый composite provider сделает provenance и validation недостоверными.

6. **Market/schedule capability mismatch.**
   Reviewed fixture ID нельзя отправлять в API-Sports odds endpoint.

7. **Masking provider outage.**
   Fallback допустим для доказанного отсутствия coverage, но не для failed
   schedule request.

8. **Cross-competition/gender false match.**
   Реальные 4958/4959 случаи показывают, что это operational, а не
   теоретический риск.

9. **Schema and migration risk.**
   Current DB uniqueness/load logic и strict manifest parsers homogeneous.
   Полумера может создать два независимых partial sets.

10. **Scheduler backward compatibility.**
    Plan/manifest exact-field validation потребует явного versioning и
    historical schema handling.

11. **Manual evidence availability.**
    Reviewed catalog может не быть готов к morning/final; безопасный результат
    тогда остаётся deferred/NO BET.

12. **Source legality/stability.**
    Нельзя строить production fallback на запрещённом scraping или нестабильной
    странице без сохранённого payload/hash.

13. **Overfitting to drawings 4958/4959.**
    Нельзя hardcode event order, team names, league или drawing number.

14. **Deadline latency.**
    Несколько provider adapters не должны нарушить T−12 publication boundary;
    timeout одного source обязан fail closed.

## Затрагиваемые модули будущей реализации

Обязательные:

- новый модуль наподобие
  `src/toto_ai/external_odds/reviewed_schedule.py`;
- возможно новый provider registry/schedule evidence contract в
  `src/toto_ai/external_odds/domain.py` или отдельном модуле;
- `src/toto_ai/db/models.py`;
- DB initialization/migrations в `src/toto_ai/db/session.py`;
- `src/toto_ai/external_odds/team_registry.py`;
- `src/toto_ai/external_odds/preparation.py`;
- `src/toto_ai/external_odds/collection.py`;
- `src/toto_ai/external_odds/prospective.py`;
- `src/toto_ai/external_odds/eligibility.py` только для provenance accounting,
  не для ослабления playable rule;
- `src/toto_ai/runner/morning_dispatch.py`;
- `src/toto_ai/runner/orchestration.py`;
- `src/toto_ai/runner/scheduler.py`;
- `src/toto_ai/runner/reports.py`;
- final-input/archive contracts runner-а;
- `src/toto_ai/cli.py`.

Регрессионные тесты:

- `tests/test_team_registry.py`;
- `tests/test_team_resolution.py`;
- `tests/test_team_resolution_4958.py`;
- `tests/test_team_resolution_4959.py`;
- `tests/test_progressive_preparation.py`;
- `tests/test_external_event_matching*.py`;
- `tests/test_runner_end_to_end.py`;
- `tests/test_runner_scheduler.py`;
- `tests/test_morning_dispatch.py`;
- новые strict catalog/mixed-provider/adversarial tests.

Не следует менять ради fallback:

- BK/EV/Cover/package math;
- текущие API-Sports fuzzy/confidence thresholds;
- atomic 15/15 definition;
- two-day playable policy;
- T−12 scheduler safety cutoff;
- timing override semantics.

## Краткий вывод

Безопасный fallback — это не дополнительный alias и не synthetic API-Sports
fixture. Это второй, first-class источник schedule identity с собственной
строгой provenance, объединённый с API-Sports только на уровне одного
authoritative preparation set. Подготовка по-прежнему должна публиковать ровно
15 pins или ноль, а final runner — независимо revalidate каждый pin его
source-specific способом и вывести один aggregate 15/15 gate.

Наиболее важное архитектурное изменение — разделить identity всего pin set и
реальный provider каждого pin. Без этого provider-neutral fallback либо не
загрузится текущими APIs, либо будет вынужден маскироваться под API-Sports, что
ослабит именно те гарантии, которые задача требует сохранить.
