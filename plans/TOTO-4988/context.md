# TOTO-4988 — локальный контекст перед вечерними автозапусками

Срез собран локально 2026-08-27 около 13:17 MSK. Внешние модели и внутренние
сервисы не использовались. Пользовательский пакет не формировался.

## Тираж и расписание

- BaltBet: видимый тираж `4988`, внутренний TotoBrief ID `12071`.
- План scheduler: schema v7, `plan_id=095bea62149ea735`.
- TotoBrief identity `ended_at`: `2026-08-27T19:00:00Z` (22:00 MSK).
- Проверенный operational cutoff: `2026-08-27T16:00:00Z` (19:00 MSK).
- T-10: `2026-08-27T15:50:00Z` (18:50 MSK).
- Банк/ставка: 4 980 / 30, максимум 166 купонов.
- План требует не менее 300 секунд на финальный расчёт и резервирует 45 секунд
  на публикацию.
- Основной LaunchAgent загружен, `runs=0`, расписание MSK:
  `17:00, 17:30, 18:00, 18:15, 18:30, 18:40, 18:44, 18:50`.
- Отдельный daytime-preflight LaunchAgent загружен, `runs=0`, запуск в 16:00
  MSK.
- Последний ручной exact preflight завершился `PASS` за ~5 секунд в 12:56 MSK:
  точная цель, данные, конфигурация и каталог подтверждены; пакет не создавался.

Основной каталог:
`data/scheduler/evening-4988-20260827T190000Z/`.

## Что уже подтверждено

- Подготовка 4988 READY 15/15; все 15 событий сейчас закреплены через
  `schedule-evidence`.
- Исправление вчерашнего дефекта 4987 (дочерний `run-drawing` ожидал raw
  `ended_at`, а не более ранний `operational_cutoff`) уже находится в текущем
  коммите/рабочей базе и описано в `memory-bank/CURRENT_STATE.md`.
- Свежий standalone research-расчёт 4988 выбрал 166 купонов на 4 980 и занял
  около 74 секунд. Это только диагностика производительности/ёмкости банка:
  у него нет scheduler-owned provenance, поэтому это не пользовательский и не
  разрешённый к ставке пакет.

## Найденные дефекты и риски

### P0 — лишняя зависимость от live API-Sports при 15/15 schedule-evidence

Первый production-like canary завершился `NO BET` примерно за 139 секунд.
Сама collection заняла 132.316 секунды и трижды запросила API-Sports schedule,
хотя все 15 pins успешно revalidated через `schedule-evidence`. Аккаунт
API-Sports сейчас возвращает suspended; итоговые флаги были ошибочно
`required_dates_complete=false`, `schedule_fresh=false`,
`ready_for_play=false`.

Локально, но ещё не закоммичено:

- `src/toto_ai/external_odds/collection.py` — live schedule не запрашивается
  для `totobrief-baseline`, `reviewed-schedule`, `schedule-evidence`; freshness
  требует live provider snapshot только при наличии настоящих live-provider
  pins.
- `tests/test_partial_enrichment.py` — регрессия для 15/15
  `schedule-evidence` и suspended provider.

Проверка текущего diff: четыре релевантных теста прошли (`4 passed in 5.10s`).

### P0 — atomic final input может разойтись с preparation probability hash

Повторный canary после первого фикса остановился до collection с
`preparation_fail:probability_input_changed_or_missing`; отчёт не был записан,
каталог canary пуст. Причина подтверждается текущим кодом:
`CommandSchedulerPhaseRunner` сначала capture/load делает свежий
`final-input.json`, но перед запуском дочернего `run-drawing` не обновляет
READY-preparation на probability hash именно этого immutable snapshot.
Изменение BK между daytime/warmup и final поэтому корректно ловится нижним
fail-closed guard, но делает вечерний запуск ложным `NO BET`.

Нельзя ослаблять hash-проверку. Требуется перед дочерним процессом:

1. распарсить exact target из `atomic_input.payload` с
   `atomic_input.captured_at`;
2. вызвать существующий
   `refresh_ready_preparation_for_target(..., provider=plan.provider)` через
   DB session factory;
3. только затем запускать `run-drawing` с тем же `TOTO_FINAL_INPUT`;
4. покрыть порядок и idempotent retry регрессией в
   `tests/test_runner_scheduler.py`.

### P0 — в активном каталоге остались future-simulated terminal artifacts

В активном output уже существуют созданные 2026-08-26 ускоренным drill:

- `paper-package-result.json` с `completed_at=2026-08-27T15:50:00Z` и
  `NO BET`;
- `runs/4988/20260827T151500000000Z-1ef44d89/status.json` с симулированными
  будущими фазами до T-10.

При этом реального `scheduler-state.json` ещё нет, основной LaunchAgent имеет
`runs=0`, а `operator-result.json` отсутствует. Старый run без `.bet-ready` не
должен сам по себе запретить новый реальный run, однако
`_ensure_terminal_paper_result()` безусловно возвращает уже существующий
`paper-package-result.json`. Это может оставить пользователю stale `NO BET`
вместо результата реального вечернего запуска. До 17:00 требуется
поддерживаемым recovery/cleanup-путём убрать или безопасно архивировать именно
симуляционный terminal binding и добавить защиту от future-simulated result;
не редактировать JSON вручную.

### Ожидаемое ограничение, не операционный дефект

`quality_v2.release_protocol_version=quality-v2-paper-only-v1`. Даже
технически корректно рассчитанный пакет остаётся PAPER/NO BET до выполнения
release gate. Это отдельно от таймаута и не является доказательством
прибыльности.

## Локальное состояние Git

- HEAD: `7fbb7b4 Guard project Git and review drawing 4987`.
- Незакоммиченные tracked-файлы:
  - `src/toto_ai/external_odds/collection.py`;
  - `tests/test_partial_enrichment.py`.
- Этот файл контекста новый и также не закоммичен.
- Ничего не пушилось.

## Обязательные проверки до вечерних запусков

1. Реализовать atomic probability refresh и регрессии, не ослабляя fail-closed
   проверку.
2. Устранить влияние simulated future terminal artifacts и доказать тестом,
   что реальный terminal result не подменяется stale paper result.
3. Повторить изолированный scheduler-bound daytime canary на exact plan 4988:
   15/15 revalidation, ноль ненужных API-Sports schedule requests, отсутствие
   `probability_input_changed_or_missing`, runtime с запасом до 300 секунд.
4. Проверить, что canary не пишет `operator-result.json`, не меняет реальный
   scheduler state и не создаёт пользовательский пакет.
5. Выполнить целевые scheduler/runner/collection тесты, затем default pytest,
   Ruff и `scripts/project-git diff --check`.
6. Перед 17:00 повторно проверить оба LaunchAgent, отсутствие лишних процессов
   и целостность plan/wrapper. После каждого реального checkpoint проверить
   state/status/logs; не считать `process exited` эквивалентом готового пакета.

До выполнения пунктов 1–3 утверждать, что 4988 защищён от повторного вечернего
сбоя, нельзя.
