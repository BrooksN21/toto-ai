#5000 — ограниченный offline replay: остановлен до генерации

Время: 2026-09-15T13:43:17.387600+00:00. **BLOCKED_NATIVE_CLI_REQUIRES_MISSING_ARTIFACTS**.

RAW пригоден как подлинный ранний market-input:15событий,15Bkquotes,исходов/счёта нет;9predrawRAW в реестре. Последний снимок07.09в19:32:08МСК, закрытие08.09в18:00МСК(T−10=17:50). Данные не рефетчил и финальные котировки не использовал.

## Почему существующимCLI нельзя выполнить этотscope
-`replay-quality-v2-v3` требует исторические scheduler-plan,final-input и уже сохранённый baseline-пакет. Это не генераторконтроляизRAW.
-`replay-quality-sports-v2-robust` дополнительно требуетsports-artifact и точное воспроизведение archivedquality-v2; режимаskip-sports нет.
-`compare-package-strategies` тоже требуетplan+final-input, а сравнивает другой наборEV/BK/Cover.
-Полныйoffline `run-drawing` требует отдельно проверяемыйschedule-cache иfinal-windowfixture; он не являетсяmarket-only3model replay.
-В точномdispatcher-record5000 `plan_id=null`, `plan_path=null`, `status=deferred`; baseline-архива нет. Нельзя выдать заново составленныйplan/final-input/archive за исторически существовавшие.

| Модель | Статус | Besthits | Категории9–15 |
|---|---|---|---|
| quality-v2 | NOT_COMPARABLE_NOT_RUN | — | — |
| quality-v3 | NOT_COMPARABLE_NOT_RUN | — | — |
| robust | NOT_COMPARABLE_NOT_RUN | — | — |
| sports-shadow | SKIPPED_NO_PREDRAW_SPORTS | — | — |

## Минимальный следующий шаг
Нужен небольшой отдельно разрешённый **research-only RAW replay adapter/CLI**: проверкаRAW/chronology→marketfrozeninput→фиксированныйcommonseed/банк4980/ставка30/nativeограничения→генерацияquality-v2/v3/robust→freezeoutputs→только потомactualscoring. Sports-shadowSKIPPED_NO_PREDRAW_SPORTS. Не менятьproductionпланы/БД/consent и не сочинятьисторическийbaseline. В этойзадаче реализациюне начинал.

**n=1 запланирован; n=0 исполнен.** Никакогоlift/prospective/profitabilityвывода. Новых пакетов/метрикнет, ничего не запущено, работающихпроцессовнет.
ПолныйJSON: `/Users/turshevr/toto-ai/plans/TOTOAI-RESUME-20260915/replay5000/replay-status.json`

Дополнительное подтверждённое ограничение: раннийpool=78 748₽, native effective_selection_budget даёт **780₽/26купонов**, не4 980₽/166. Подмена финальнымпулом/отключениеограничения не выполнялись.
