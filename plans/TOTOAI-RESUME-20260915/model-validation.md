# TOTOAI-RESUME-20260915 — ограниченная офлайн-проверка моделей

Завершено: 2026-09-15T13:39:33.614717+00:00. История4999–5006; генераторы/обучение/сетевые запросы не запускались. БД только read-only,5007/задания/код/ACTIVE_PLAN не изменялись.

## 4999: точные сохранённые пакеты
**EXPIRED / POST-CUTOFF RESEARCH ONLY — ANALYSIS ONLY, NOT FOR WAGERING OR UPLOAD.**

Официальные импортированные исходы: `X2112X222X1XX22`. Plan `b742aac1fea2d42d`. Вход сохранён07.09в17:00:02МСК, параллельный расчёт закончен17:08:51МСК доT−10=17:20. По manifest банк4 980₽, ставка30₽,166купонов — не догадка по истории чата.

| Модель | Купонов / уникальных | Максимум | 9 | 10 | 11 | 12 | 13 | 14 | 15 | Ниже9 |
|---|---|---|---|---|---|---|---|---|---|---|
| quality-v2 | 166/166 | 11 | 6 | 2 | 1 | 0 | 0 | 0 | 0 | 157 |
| quality-v3 | 166/166 | 11 | 18 | 5 | 1 | 0 | 0 | 0 | 0 | 142 |
| robust | 166/166 | 11 | 6 | 2 | 1 | 0 | 0 | 0 | 0 | 157 |
| sports-shadow | 166/166 | 11 | 20 | 10 | 1 | 0 | 0 | 0 | 0 | 135 |

Во всех четырёх пакетах13+нет. sports-shadowдал31купонов9+, quality-v3—24, quality-v2/robust—по9. Это НЕ доказательство доходности: коэффициентов/квитанции4999в проверенных входных и связанных post-drawартефактах нет, TotoBriefpayments=null. **Выплата/чистый результат/ROI: UNKNOWN.**

### Предматчевый лучшийP(13+) отдельно от лучшего фактического
Позиции1-based. Исходные записи рейтинга сохранены, затем проверены повторным точным вычислением по связанным вероятностям; все совпали.
| Модель | Исходно highestP13 купон | Позиция | Модель вероятностей | P(13+) | Реальных попаданий |
|---|---|---|---|---|---|
| quality-v2 | `1211221211X1122` | 74 | bk | 0.026721817% | 7 |
| quality-v3 | `1211221211X1122` | 9 | bk | 0.026721817% | 7 |
| robust | `1211221211X1122` | 74 | bk | 0.026721817% | 7 |
| sports-shadow | `121111121111122` | 1 | sports | 0.027088855% | 7 |

Критерий: maximum_probability_at_least_13. Первый купон пакета не считается лучшим автоматически.

**Лучшие фактические купоны** (11попаданий; не предматчевая рекомендация):
- quality-v2: позиция71: `X2112X121X11122`
- quality-v3: позиция42: `X21121221111X22`
- robust: позиция71: `X2112X121X11122`
- sports-shadow: позиция71: `X2112X121X11222`

### Проверенные привязки
- Native settle_final_hybrid_comparison: внутренние хеши sidecar/comparison, хеш файлаcomparison, canonicalкупонныехеши, count/stake/cost всех4пакетов — PASS.
- Native load_scheduler_plan/load_final_input: plan/drawing/deadline/target fingerprint/вход/вероятности — PASS; исходы и счёт во входномRAW пусты.
- PrimaryCSV bytesSHA и archive manifestSHA, связанный final-inputSHA; исходный controlCSV точно равен baseline research coupons — PASS.
- Все4оригинальныеhighestP13-записи повторно рассчитаны по boundbk/sportsвероятностям и совпали по купону, позиции иP13.
- Файлы не реконструировались и не изменялись. Это постмортем реально сохранённых pre-cutoffoutputs, не новый прогноз.

##5000–5006: доступность независимой оценки
| Тираж | Предматчевые activeRAW | Frozenпакеты | Sports snapshots | Результат |
|---|---|---|---|---|
| 5000 | 9 | 0 | 0 | PREDRAW_MARKET_ONLY_FOUR_MODEL_REPLAY_INPUTS_INCOMPLETE |
| 5001 | 0 | 0 | 0 | NOT_EVALUABLE_PROSPECTIVELY |
| 5002 | 0 | 0 | 0 | NOT_EVALUABLE_PROSPECTIVELY |
| 5003 | 0 | 0 | 0 | NOT_EVALUABLE_PROSPECTIVELY |
| 5004 | 0 | 0 | 0 | NOT_EVALUABLE_PROSPECTIVELY |
| 5005 | 0 | 0 | 0 | NOT_EVALUABLE_PROSPECTIVELY |
| 5006 | 0 | 0 | 0 | NOT_EVALUABLE_PROSPECTIVELY |

5000:есть9ранних настоящих снимков; последний07.09в19:32МСК, за день до закрытия08.09в18:00МСК. ЕгоRAW+metadatahash проверены,15событий сBkquotes и без исходов. Но нет сохранённых пакетов и спортивного предматчевого входа: честного equal-inputсравнения **четырёх** моделей сейчас нет. Возможен отдельно ограниченный market-onlyретроспективный replay трёх семейств, не prospectiveкачество/неfour-model.
5001–5006:в проверенныхnativeреестрах нет предматчевых снимков/пакетов; только сегодняшниеfinishedRAW. Подставлять ихfinalodds в генератор запрещено — получился бы look-ahead. **Новые прогнозы не создавались.**

## Что фактически внедрено в сохранённом4999
-quality-v2: основной166купонный контроль.
-quality-v3: `quality-v3-bounded-uncertainty-v1`; отдельный прямойcandidatepool, category13, flatten0.1/0.2.
-robust: сохранённый итоговый пакет **в точности совпадает сquality-v2**; lineage `robust-family-g1-v1`, applied=false. Это не четыре разных успешных улучшения.
-sports-shadow: текущийhybrid,13позиций соsportdata+2fallback; sportsv3trainedmanifest в boundартефактах не указан.
-Sportsv3: **не подтверждён как обученный/активированный прогноз**. В boundreportO1 `NO_INDEPENDENTLY_REVIEWED_EVENT_LOCAL_INPUT_ADAPTER`, descriptive evidence only, activation_allowed=false. G1researchrefinementDISABLED.

## Вывод и следующий ограниченный шаг
1. На4999все4максимум11; sports-shadow иquality-v3шире покрыли9–11, но13+не достигли. Одного тиража недостаточно для выбора «лучшей навсегда» модели или причинных выводов.
2. Предматчевыйquality-v3P13был выше, но селектор отклонил по `bk_p15_below_control`. Факт одинаковых11после тиража не доказывает оптимальность этого правила.
3. Для5000не запускатьfull4replayбезmissingSportsfixture. Точная последняяmarketRAWссылка и хеш записаны вJSON; дополнительныйmarket-onlyreplay — отдельный малыйscope, замороженныйoutputдоscoring, без сегодняшнихкотировок.
4. Для5001–5006нельзя ретроспективно восстановить факт предматчевого прогнозирования изоднихрезультатов. Приоритет — обеспечить ежедневное сохранение входов/спортивнойистории, а не рисовать статистику наfinaldata.

## Артефакты
-JSON: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/model-validation.json`
-CSV: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/model-validation-4999/table.csv`
-Native settlement: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/model-validation-4999/final-hybrid-settlement.json`
-Native Markdown: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/model-validation-4999/final-hybrid-settlement.md`
