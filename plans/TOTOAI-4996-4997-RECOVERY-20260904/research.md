# Sports Analytics v3 / robust recovery: research baseline

**Статус:** `RESEARCH ONLY — NOT ACTIVATED — NOT OPERATOR COMPATIBLE`  
**Дата:** 2026-09-04  
**Граница:** только локальное чтение замороженных артефактов. Никаких сетевых
запросов, записи в БД, изменения source/operator/scheduler, генерации
операторского пакета или обещаний прибыли.

## Прочитанные источники

- `AGENTS.md` и обязательный контекст `memory-bank/`, в первую очередь
  `memory-bank/ACTIVE_PLAN.md`.
- 90-event aggregate:
  `reports/research/sports-v3-4990-4995/attribution-aggregate.{json,csv,md}`.
  Семантический SHA-256 отчёта:
  `94ab5d0641f23ba4a25f16830b4536cac4c4bdf8e916a83cc519ccf2e25a1189`.
- Write-disabled backfill dry-run:
  `reports/research/sports-history-backfill-4990-4995-dry-run/`.
  Manifest SHA-256:
  `dd6151f61f4d3ab89a28eeea778fa0d02f7e96deb956ecb6c9742c076758ca77`;
  audit SHA-256:
  `737db286938d5a46c4d683c29368ed398a49fb6f632816fae08a2ebbb6bc6ab1`.
- Ранее выполненный equal-input replay:
  `reports/research/constrained-hybrid-replay-v2/` для 4990–4994 и
  `reports/research/4995-equal-input-replay/` для 4995.
- Реализованные research-only границы:
  `src/toto_ai/sports_stats/v3_features.py`,
  `src/toto_ai/optimizer/hybrid_replay.py`,
  `src/toto_ai/optimizer/robust_package.py` и их целевые тесты.
- Для 4996 прочитаны только метаданные замороженного final input и sports
  snapshot, без чтения исходов или изменения operational-артефактов.

## Что показывает 90-event aggregate

| Метрика | BK | Sports v2 | Sports v2 − BK |
|---|---:|---:|---:|
| Top accuracy | 0.422222 (38/90) | 0.411111 (37/90) | -0.011111 |
| Multiclass Brier | 0.659081 | 0.657897 | -0.001184 |
| Log loss | 1.088092 | 1.086390 | -0.001702 |
| Top-confidence ECE | 0.025804 | 0.052743 | +0.026939 |

- Sports v2 покрывает 64/90 событий. Из 26 fallback-событий 24 вызваны
  `sports_history_missing`, ещё 2 — `insufficient_venue_history`.
- Из 64 изменённых событий Sports v2 повысил вероятность фактического исхода
  в 36 и понизил в 28, но один раз сломал правильный top outcome и не создал
  ни одного нового правильного top outcome.
- Фактических ничьих 28. У BK и Sports v2 на них 0 top-correct; Sports v2
  ухудшает draw-срез по Brier на `+0.000692` и по log loss на `+0.001703`.
  Это основание тестировать draw calibration, но фактический признак `DRAW`
  остаётся только меткой оценки и не может быть предиктором.
- На 30 low-margin событиях `[0.00,0.05)` Sports v2 почти не меняет Brier/log
  loss, ухудшает ECE на `+0.035351` и теряет один top-correct. На 26 событиях,
  где фактический исход имел BK rank 3, Brier/log loss также немного хуже.
  `actual market rank` — только метка оценки; допустимы лишь предматчевые BK
  margin/entropy.
- 88/90 событий лежат в широком entropy-bin `[0.95,1.00]`; лиги и отдельные
  drawing-срезы слишком малы для правил или выводов о превосходстве.
- Package attribution: ни у одной стратегии нет zero actual exposure или
  fixed-wrong событий. Universal miss лучшего реализованного купона встречался
  19 раз у quality-v2, 15 у sports-v2, 25 у quality-v3 и 17 у robust. Это
  описательная post-draw метрика, не цель подгонки.

## Что показывает backfill dry-run

Dry-run выполнил `network_requests=0`, `database_writes=0`, `inserted=0`,
`reused=0`.

| Тираж | Результат | Complete events | Missing events | Available / unavailable raw sources |
|---:|---|---:|---:|---:|
| 4990 | rejected: `final input deadline mismatch` | 0 | 0 | 0 / 0 |
| 4991 | validated | 0 | 15 | 0 / 30 |
| 4992 | validated | 15 | 0 | 30 / 0 |
| 4993 | validated | 11 | 4 | 22 / 8 |
| 4994 | validated | 13 | 2 | 26 / 4 |
| 4995 | validated | 13 | 2 | 26 / 4 |

- 4990 нельзя «чинить» нормализацией времени или синтетическим history. До
  появления отдельно проверяемого target evidence весь Sports v3 fold обязан
  использовать точный BK fallback и помечаться `SOURCE_REJECTED`.
- У 4991 отсутствие всех 30 источников явно зафиксировано. Это необходимый
  negative-control для missing-history handling: Sports v3 должен быть
  побитово/численно тождествен BK, а Sports v2 — воспроизводить quality-v2.
- 4992 — complete-history positive-control; 4993–4995 дают реальные смешанные
  complete/missing события без права заполнять отсутствующие fixture/history.
- Source availability и non-null predictor coverage — разные показатели.
  Даже complete raw event может получить null venue/rolling feature из-за
  `minimum_prior_matches`; будущий coverage audit должен публиковать оба слоя.

## Equal-input package baseline 4990–4995

Во всех шести replay использованы 4 980 RUB, stake 30 RUB и 166 купонов.
Quality-v2 воспроизведён из замороженного input; все артефакты research-only.

| Тираж | qv2 best | Sports v2 | qv3 | robust | 13+ купонов у каждой стратегии |
|---:|---:|---:|---:|---:|---:|
| 4990 | 11 | 9 | 11 | 11 | 0 |
| 4991 | 11 | 11 | 10 | 11 | 0 |
| 4992 | 10 | 10 | 10 | 9 | 0 |
| 4993 | 8 | 10 | 8 | 10 | 0 |
| 4994 | 10 | 10 | 10 | 10 | 0 |
| 4995 | 9 | 9 | 10 | 9 | 0 |

Средний best hit: quality-v2 10.00, Sports v2 10.00, quality-v3 9.83,
robust 10.00. Шесть тиражей и ноль 13+ не доказывают превосходство и ничего не
говорят о прибыли.

Максимальная доля одного event/outcome у quality-v2 по тиражам находится в
диапазоне 0.746988–0.801205. Новый robust-кандидат не должен превышать
соответствующий control-relative предел ни в одном fold.

## Замороженная граница 4996

- Plan: `0d8c2cdfb10ef9c5`.
- Final input SHA-256:
  `fddd407deff8816eb09c3997d79f3bb4f9ffb57360f5d1cd4e1ad338f0205968`.
- Probability input SHA-256:
  `d647aa67eff0d1583fe792b5bbf72f99a88dffc00301855c0fbb4b9bd140e7fb`.
- Тот же bank/stake/capacity: 4 980 / 30 / 166.
- Замороженный Sports v2 source snapshot имеет coverage 12/15, fallback 3/15;
  final rebased sports probability SHA-256:
  `c9efb27f69c3ad39a622c8e69f08ab11a348bc8c4bfe85810ac565e3a3b0e48d`.
- Parallel sidecar был остановлен до полного четырёхстратегийного результата.
  В inspected post-draw каталоге нет terminal settlement. Поэтому 4996 входит
  в обязательный replay только после появления hash-bound terminal result и
  до этого имеет статус `PENDING_RESULT`, не влияет на дизайн и пороги.

Если нельзя доказать, что спецификация/хэш кандидата зафиксированы до чтения
исходов 4996, этот тираж остаётся development diagnostic, а не untouched
holdout. Первым настоящим prospective holdout тогда становится следующий
тираж после фиксации реализации.

## Вывод для следующего шага

1. Сначала нужен детерминированный 90-event feature/source coverage audit без
   fitting и без записи backfill в БД.
2. Затем — bounded residual вокруг untouched BK с drawing-level walk-forward,
   отдельными draw и missing-history абляциями.
3. Только probability-кандидат, прошедший predeclared gate, допускается к
   новому robust package research. Перестановка существующих купонов не может
   считаться улучшением модели.
4. Любой результат 4990–4996 — лишь исторический экран. Активация и заявления
   о превосходстве остаются запрещены до минимум 30 prospective drawings / 450
   events; прибыль требует фактических payout и доказанного placed package.
