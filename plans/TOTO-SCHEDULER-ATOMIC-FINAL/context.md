# TOTO-SCHEDULER-ATOMIC-FINAL: контекст и postmortem

Собрано 2026-07-27 только из standalone-репозитория
`/Users/turshevr/toto-ai`.

Прочитаны:

- корневой `AGENTS.md`;
- все файлы `memory-bank/`;
- scheduler/runner/preparation код;
- артефакты и логи запуска №4957 из
  `reports/rehearsal/evening-4957-20260727T095815Z`.

Не использовались Arcadia, Yandex, Gena, Startrek и внешняя память. Это
planning-only задача: код, коммиты, push и установка LaunchAgent не выполнялись.

## Текущее состояние репозитория

- Ветка: `feature/initial-toto-ai`.
- HEAD: `b8d7608 Add audit-only sports statistics snapshots`.
- Исходный operational hardening до sports-stats:
  `9f5dbfd Harden drawing lifecycle evidence`.
- Рабочее дерево содержит только существующие untracked `plans/` и `reports/`;
  operational reports не должны попадать в исходный коммит.
- Последняя подтверждённая полная проверка на HEAD:
  `1384 passed`, Ruff и `git diff --check` прошли.

## Что произошло на тираже №4957

Целевой тираж:

- visible drawing: `4957`;
- internal ID: `11983`;
- дедлайн: `2026-07-27T15:00:00Z` / `18:00 МСК`;
- банк: `4980 ₽`;
- ставка на купон: `30 ₽`.

### Хронология

1. **T−45, 17:15 МСК**

   LaunchAgent запустил единственный процесс `scheduler-execute`. Preflight
   вызвал cache-only `prepare-drawing` и завершился ошибкой:

   ```text
   drawing detail cache is stale: age=15754.9s, limit=60.0s
   ```

   Процесс сразу стал terminal `FAILED`. Поскольку plist содержит один
   `StartCalendarInterval`, самостоятельных T−30/T−15/T−10 запусков не было.

2. **17:34 МСК, ручной повтор**

   Ещё один запуск снова выполнил cache-only preflight и отклонил кэш возрастом
   `98.4s` при лимите `60s`.

3. **17:35–17:36 МСК**

   После отдельного fresh `sync-prepare` подготовка стала READY 15/15.
   Зафиксирован detail:

   - fetched at: `2026-07-27T14:35:12.703390Z`;
   - detail payload hash из sidecar:
     `2571db29b1457d98b45511c6645c76f65469415277db099be05b5fe31620c418`;
   - normalized BK probability hash:
     `083eabf452eecb0cf314b98572884ab58242b35ae8c020fcab74eb7905e724e0`;
   - preparation update:
     `2026-07-27T14:35:58.428946Z`;
   - mapped/playable: `15/15`.

4. **17:36:44–17:39:14 МСК, diagnostic fallback**

   Runner полностью отработал примерно за `149.48s`, получил свежую
   revalidation 15/15 и вычислил пакет. Package safety отвергла купоны:

   ```text
   package_safety:extreme_concentration,zero_exposure_material_outcome
   ```

   Это корректный `NO BET`, но scheduler не принял manifest:

   ```text
   NO BET runner manifest is not zero-cost
   ```

   Денежные поля и coupons уже были нулевыми, но
   `derived_brief` сериализовался как 15 пустых строк, а строгий контракт
   требует пустой список.

5. **T−15, 17:45 МСК, authoritative final**

   `run-drawing` получил новую live detail-версию. Пул/BK legitimately
   изменились после подготовки 17:35. `_prepare_runner_resources()` сравнил
   текущий normalized probability hash с хешем старой preparation row и
   завершился:

   ```text
   preparation_fail:probability_input_changed_or_missing
   ```

   Неудачный final response не был сохранён отдельным immutable artifact,
   поэтому точную изменившуюся матрицу из артефактов восстановить нельзя.

6. **T−10, 17:50 МСК**

   Final package отсутствовал, fallback был невалидным для parser, hard
   publication deadline был пропущен. Результат:

   - `FAILED / NO BET`;
   - `0` approved coupons;
   - `0 ₽`;
   - upload-ready файл не создан.

## Корневые причины

### 1. Неверная временная граница probability invariant

Текущий код требует, чтобы live probability matrix совпадала с preparation,
созданной в более ранней фазе. Для меняющегося пула это неверный invariant:
изменение между T−45/T−30 и final ожидаемо.

Защищать нужно не неизменность рынка между фазами, а неизменность **одного
exact final snapshot внутри попытки**, из которой одновременно выполнены:

- final preparation evidence;
- runner target;
- package probability input;
- safety evaluation;
- package/report/archive.

### 2. Несколько live detail views внутри одной package-фазы

Production `run-drawing` сейчас может читать drawing detail несколько раз:

1. preflight target resolve;
2. final target resolve;
3. `_build_runner_package()` снова вызывает `drawing_info()`.

Даже если каждый запрос корректен, они могут видеть разные версии live пула.
Затем результат сравнивается с ещё более ранней mutable preparation row.

### 3. `final_inputs_sha256` не включает final detail

Текущий `_final_inputs_sha256()` включает plan/config/deadline/bank/stake и
timing-override hash, но не raw detail, probability matrix или source fetch
time. Поэтому имя обещает более сильную гарантию, чем реально даёт.

### 4. Warmup/preflight является terminal dependency

Ошибка T−45 немедленно завершает весь scheduler. Final phase не имеет
самостоятельного запуска и не может восстановиться после transient stale-cache
или network ошибки.

### 5. LaunchAgent одноразовый

Сгенерированный plist имеет один `StartCalendarInterval` на T−45. Он не
перезапускает scheduler в T−30/final/cutoff и не поддерживает restart/resume.

### 6. Final window слишком узкий

Current final starts at T−15, publication waits until T−10. Реальный полный
4957 fallback занял около `149.5s`; остаётся слишком мало времени для:

- transient retry;
- package archive;
- marker publication;
- ручной загрузки пакетной ставки.

### 7. Неканонический computed NO BET

`ev.drawing._empty_no_bet()` сохраняет `derived_brief` как tuple пустых строк.
Scheduler правильно требует реальный zero-cost manifest, но producer нарушает
этот контракт.

## Что не является причиной

- API key был доступен из secure `.env`.
- `cwd`, absolute project paths и LaunchAgent wrapper были корректны.
- Drawing identity `4957/11983/deadline` была корректна.
- 15/15 team/fixture preparation после fresh sync была корректна.
- Fail-closed защита не позволила поставить неподтверждённый пакет. Ошибка в
  том, что защита привязана к неправильной временной границе и не умеет
  восстанавливаться.

## Рассмотренные архитектурные варианты

### A. Один долгоживущий процесс T−45 → T−12

Плюсы: минимальные изменения текущего scheduler loop.

Минусы: падение процесса, reboot/sleep или terminal preflight снова уничтожают
все последующие фазы. Restart/recovery остаётся сложным.

### B. Resumable scheduler ticks с persistent state — выбран

LaunchAgent запускает одну и ту же idempotent command в несколько времён.
Каждый tick под lock читает state, выполняет только due work и завершается.
Final не зависит от warmup success.

Плюсы: независимые final/retry/cutoff, crash recovery, отсутствие долгого sleep,
понятные append-only attempts.

Минусы: требуется новый state schema и миграция scheduler plan/artifacts.

### C. Отдельный LaunchAgent на каждую фазу

Плюсы: фазы физически разделены.

Минусы: несколько plist/wrapper, больше риска version/config drift и сложнее
единая idempotency. Преимуществ перед вариантом B нет.

## Выбранный протокол

### Времена по умолчанию

- T−45: optional warmup/identity/cache preparation;
- T−30: optional refresh/readiness check;
- T−20: первая authoritative final попытка;
- T−16: независимый retry tick, если final ещё не завершён;
- T−12: hard publication/no-bet cutoff.

Успешный final публикуется сразу после полной проверки, не ждёт T−12.
T−12 — крайний срок, а не плановое время публикации.

### Atomic final input

Каждая final attempt:

1. проверяет exact planned drawing identity;
2. получает **один** fresh direct-network `drawing-info/{id}` response;
3. валидирует 15 ordered events, deadline, pool/BK rows;
4. атомарно сохраняет immutable run-scoped snapshot;
5. использует один parsed object для preparation/revalidation и EV/package;
6. запрещает последующий `drawing_info()` в этой attempt;
7. связывает package/safety/report/archive с snapshot SHA-256.

Изменение пула до snapshot допустимо. Изменение API после snapshot не
проверяется и не инвалидирует package. Изменение сохранённых snapshot bytes,
normalized probabilities, preparation evidence или package binding после
capture считается tamper/concurrency failure.

### Retries

- transient errors: timeout, connection reset, HTTP 429/5xx, временно
  недоступный cache/provider;
- permanent errors: wrong drawing identity/deadline, malformed 15-event
  payload, invalid config, hash/tamper conflict, unsafe path;
- warmup failure записывается, но не блокирует final;
- одна final invocation имеет bounded retries/backoff;
- повторный T−16 tick может создать новую append-only attempt;
- новая attempt допустима только если остаётся минимум `180s` вычисления плюс
  `45s` publication reserve;
- hard stop T−12 всегда запрещает PLAY publication.

Конкретные budgets являются scheduler config и покрываются fake-clock tests;
они не должны быть размазаны magic numbers по коду.

### Terminal semantics

- valid approved package before T−12 → `BET READY`;
- model/safety/timing/no-package/transient exhaustion/deadline miss →
  canonical zero-cost `NO BET`;
- target identity/config/path/hash/tamper corruption → `FAILED`;
- ни `NO BET`, ни `FAILED` не содержат package bytes и не создают
  `.bet-ready`.

## Scope boundary

Изменение применяется только к production scheduler/final path.

Должны остаться неизменными:

- research `run-drawing`;
- offline replay;
- historical backtests;
- current probability/EV math;
- package safety thresholds;
- category/bank/stake definitions;
- automatic bet placement остаётся запрещённым.

## Resolution status — 2026-07-28

The code remediation described by this postmortem is implemented in the
working tree: immutable one-fetch final input, independent
T−45/T−30/T−20/T−16/T−12 ticks, persistent state/lock, bounded retry, recovery,
T−12 publication cutoff, and canonical zero-cost `NO BET`. The dynamic morning
dispatcher is implemented in `morning-preanalysis.md`.

After closing the remaining review findings, verification is `1428 passed` for
the full suite, `175 passed` for the focused scheduler/morning/CLI suite, and
one deterministic fixture rehearsal of `42 passed`; Ruff and
`git diff --check` pass. The five obsolete LaunchAgents were removed. No
replacement dispatcher or evening scheduler is installed. The
activation-disabled 4958 drill deferred without plan/package because the
API-Sports schedule lacks women event 5; a provider-neutral schedule fallback
and a repeated 15/15 drill remain the operational gate.
