# Следующий тираж и постмортем4998 — context only

Проверено 2026-09-06T20:29:23.425616+03:00. Код/DB/jobs/consent не менялись.

##4999 / ID12106
Свежий локальный dispatcher record от 2026-09-06T17:24:21.668183Z: deadline **07.09.2026 17:30МСК**. Mapping15/15, external coverage12/15, preparation `ready`, но operational dispatch **deferred: timing unknown3/15** (zero-based8,11,13; позиции9,12,14). Playability `unknown`/false — это статус локального gate, НЕ доказательство отсутствия открытого тиража на сайте.
`plan_id=null`, `plan_path=null`, activation `not_requested`, label/path=null: per-drawing scheduler/watcher не подготовлены в этом реестре. Общий morning-dispatch daemon не проверялся.
Источник: `/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/drawing-12106-20260907T143000Z-b2596e1df489092a.json`. Один разрешённый публичный TotoBrief summary GET завершился ConnectTimeout6s; без повторов, live-source status **не проверен**. Сохранённая идентичность не исправлялась.
Осталось: отдельная работа с reviewed timing evidence для3строк; затем план и вопрос владельцу о ручной ставке с новым exact4999/plan/bank/stake consent до cutoff.4998 consent не переносится.

## Постмортем4998 / ID12102
План `/Users/turshevr/toto-ai/reports/rehearsal/evening-4998-20260906T153000Z/post-draw/post-draw-12102.json`; label `com.toto-ai.post-draw-12102` реально загружен: **not running, runs0, never exited**. Первый запуск **07.09 12:00МСК**, далее каждые3часа,6попыток до08.09 03:00МСК. Postmortem/state/review-request пока: False/False/False.
План привязан к одному source-package из paper-package/checkpoints (166/4980/30), не доказывает разбор owner-reported quality-v3 ставки или всех4моделей. Квитанция/реальная сумма/ставочные байты не подтверждены.
4998 primary: **not running, runs8, exit0**; watcher: **not running, runs1, exit0**. Их прошедшие слоты не являются подготовкой4999.

Следующий контроль:07.09 12:00МСК — состояние/результат запланированного постмортема; подготовку4999 и consent вести отдельно до его deadline. Никаких новых запусков, планов, публикаций или активаций этим job. Точные поля/labels/ошибка запроса — в JSON companion.


## Уточнение по коду: автоматическая ветка4моделей VERIFIED

Один package_binding ограничивает primary settlement, НЕ весь job. `finished_draw.py:1488` автоматически вызывает sidecar settlement (:1617), а `final_hybrid_settlement.py:20-107` обрабатывает quality-v2, sports-shadow, quality-v3, robust с проверкой hashes/count/stake/cost. Дополнительный план/активация для этой ветки не нужны.

Точные read-only проверки фактических4998файлов, seals, связи final-input и archived operator сохранены в JSON.clarifications[-1], включая все false/несовпадения без сокрытия. Сам native settlement не перечитывает final-input или operator companion/upload: он проверяет sealed comparison и4researchpackages. Поэтому его отчёт не является проверкой реальной ставки владельца.

После07.09 12:00 проверять также post-draw/parallel-comparison-status.json и parallel-comparison/final-hybrid-settlement.json/.md. Optional failed/skipped не блокирует основной complete; завершённый план не повторяет эту ветку автоматически. При несовпадении — отдельная точечная проверка уже сохранённых companion/upload/sidecar/comparison/final-input, без нового расчёта/изменения архива. Код/jobs/DB/API/результаты не тронуты.

Итог hash-проверки: все4пакета по166, seals sidecar/report/companion и archived quality-v3 semantic hash совпали. Final-input seal тоже VERIFIED по его native ensure_ascii=True (final_input.py:246–249); первоначальный generic ensure_ascii=False probe был несовместимым способом сериализации, не порчей данных. Comparison указывает на тот же snapshot/plan/run.
