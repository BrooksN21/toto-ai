# Улучшение вероятностей, пакетов и локальных skills — предлагаемый план

Task `TOTOAI-4998-PARALLEL-INTEGRATION-20260906`. 2026-09-06T21:53:09.513770+03:00.
**PROPOSED — согласовано только планирование, не реализация/запуски/rollout.**
Существующий незавершённый checklist не заменяется. Пользователь может одним разрешением утвердить весь явно определённый план/объём либо выбранную часть; после этого включённые обычные checkpoints выполняются без повторного запроса на каждом шаге. Это не новый постоянный approval gate. Отдельно сохраняются только действующие границы: новая ставка и exact drawing/plan-bound consent, расширение согласованного scope/rollout и необходимая авторизация внешней публикации. Пока утверждено только планирование, не исполнение.

## Граница4999 и исходные факты

План `b742aac1fea2d42d`: реальный preflight **PASS,exit0,5.888s**, по сохранённому receipt21:44:43МСК. В этом планировании runtime заново не проверялся. Более раннее NO PASS в MODEL_QUALITY_BANK_CONTEXT устарело. Primary/parallel/watcher, банк4980/ставка30, bindings и расписания не менять; nextprimary07.09 15:30, parallel17:00, expiry17:20, close17:30МСК. Exact manual-release consent4999 **не получен**; технический PASS не является разрешением ставки.

**До4999 безопасно:** этот план, обсуждение критериев, чтение уже вычисленных отчётов, подготовка отдельно согласованного документационного diff. Не запускать fit/sweep/тяжёлый replay рядом с primary; не переносить новые модели, skills-поведение, настройки банка или рефакторинг в работающий4999. Кандидаты ниже — позднее, изолированно, после отдельного разрешения, review и решения о rollout.

Разделение объектов:
- **BK / SportsV2 / SportsV3** дают вероятности матчей. BK — замороженный рыночный baseline; его откалиброванный вариант является отдельным кандидатом.
- **quality-v2 / quality-v3 / robust** выбирают пакеты. `sports-shadow` — пакетная ветка на V2. Название quality-v3 не означает SportsV3; G1 — refinement поиска, не футбольный предиктор.
- Больший банк не улучшает вероятность отдельного матча. Ни один пункт не обещает13/15,15/15 или прибыль.

## Последовательность контрольных точек

### C1. Сначала зафиксировать контракт сравнения
**Выход:** один manifest/protocol: frozen BK/V2 inputs, code/config/seed/pool/bank/as_of/fold hashes, исходный primary и selector; матрица predictor × optimizer. Для V3 пока явный `INELIGIBLE`, не подставлять V2/G1/ручные веса. Генераторы не видят outcomes/payouts до freeze.
**Успех:** воспроизводимый baseline и одинаковые inputs/бюджет/сценарии сравнения, сохранённые denominator/failures. **Отклонить:** drift, отсутствующий hash/as_of, выбор победителя по уже известным4996/97 или oracle. Существующие90labels и terminal4996label уже есть — не собирать повторно.4990–4995 design-informed;4996/97 — не объявлять слепым holdout.

### C2. Закрыть именно данные и границы настоящего V3
**Выход:** проверенная event-wise таблица identity/scope/competition/independent features/captured_at/as_of/availability, equal-input BK/V2/plan/fold bridge; отдельно4996 feature/V2 extension. Сохранить core37/full53 и отдельные rejected/missing/fallback denominators.
**Стоп сейчас:**30 chronology-rejected +8 missing; даже идеальное extension даёт **67/105=63.81% <70% (нужно≥74/105)**. Один scope bridge недостаточен. Поздняя загрузка не становится pre-as-of capture; не удалять неудобные строки из frozen корпуса. Независимые opponent-history/standings/margin bindings неполны. Требуется источник с доказанным историческим as_of либо новый явно отдельный prospective корпус; старые отказы остаются.
**Успех:** все provenance/chronology/scope gates и неизменный coverage gate; лишь затем отдельная интеграция совместимых ACCEPT06 изменений и реальный fit→freeze→evaluate. Узкий F4 code ACCEPT — не probability PASS. После research-screen остаётся прежний prospective минимум **30drawings/450events,≥70% coverage** и остальные gates; редким13+/15 может не хватить мощности даже на таком числе.

### C3. Главный quality-эксперимент — калибровка и bounded market residual
Приоритет: (1) raw BK против train-only calibration; (2) существующий V2 против calibrated/bounded residual; (3) реальный fitted V3 только после C2. Далее **по одной семье абляций**: opponent adjustment, home/away, recency/time weighting, затем rest/standings при независимых своевременных данных. Глубина модели сама по себе не критерий.
**Выход:** expanding whole-drawing chronological folds, train-only transforms/imputation/calibrators, hyperparameters только на ранних/внутренних folds; frozen кандидат и новый нетронутый prospective holdout.
**Основная предложенная метрика:** paired Δmulticlass log loss против frozen baseline; sum-Brier, draw-class Brier/reliability и non-draw losses — обязательные co-metrics. ECE с фиксированными bins/top-correct — диагностика, не единственная цель. На90событиях V2 имел ΔLL≈−0.001702, ΔBrier≈−0.001184, но ECE0.02580→0.05274: это не доказательство лучшей калибровки. Ноль top-X среди28ничьих не означает нулевую P(draw) и не оправдывает boost ничьих.
**Предложенный критерий качества, согласовать до запуска:** upper95% paired drawing-cluster CI для ΔLL<0, отсутствие Brier/draw/non-draw и worst-fold/league деградации сверх заранее замороженных действующих tolerances; multiplicity учесть. Если CI пересекает0 — `INCONCLUSIVE`, не PASS. Малые league-срезы только описательные. Никакой правки текущих gates этим документом.

### C4. Проверить четыре пакетные ветки и эффект банка, не смешав причины
Сначала один одинаковый frozen input/bank4980: qv2/sports-shadow/qv3/robust с неизменным selector; V3-arm допускается отдельно после C2/C3. Отделять raw лидерство от **eligible selected strategy и причин отказа**. Затем отдельно согласованный трёхбанковый research experiment по таблице ниже.
**Метрики:** exact union P13+/P14+/P15 на общей probability matrix; overlaps/intersections/добавленная масса, unique N, cost, exposure/concentration/feasibility; P9+ — отдельно sampled с common held-out stream и MC error. Сохранить предположение event-independence exact engine; купоны зависимы. После freeze: actual best/mean hits, доля тиражей с≥13/14/15 и uncertainty — не смешивать с числом выигрышных купонов.
**Успех:** baseline воспроизведён, одинаковые сценарии/политики кандидатов, все safety/non-degradation/deadline gates; никаких уменьшений search space для скорости. **Отклонить promotion:** нарушение gates, несопоставимые bindings, поздний результат или только raw P13 без eligibility. Недоказанный прирост — честный результат, не повод менять категорию.

| Requested bank, ₽ | Stake, ₽ | Номинально уникальных купонов | Минимальный pool для полного банка при1%cap, ₽ |
|---:|---:|---:|---:|
|4980|30|166|498000|
|7470|30|249|747000|
|9960|30|332|996000|

`B_eff=min(B,30×floor(0.01×pool_sum/30)); K=floor(B_eff/30)`; дополнительно действуют native feasibility/EV/safety gates. Сохранённые4999 1020₽/34 — ранний pool snapshot, не final cap.
Две заранее разделённые ветки: независимая оптимизация каждого банка и **доказанное** nesting S166⊆S249⊆S332; infeasible nesting не форсировать. Только при nesting и одной мере вероятность union не убывает. Нельзя суммировать индивидуальные P13 купонов, применять независимость купонов или складывать P13/P14/P15. Одинаковые166 купонов с большим stake не меняют hit probability; допустимость иных номиналов не предполагается.
Готового sweep нет: `replay-quality-sports-v2-robust` берёт bank из historical plan, **не имеет --bank**. Нужен отдельно разрешённый/reviewed research adapter с новыми budget-bindings и isolated DB snapshot, без изменения scheduler plan/consent. Заморозить baseline каждого банка, веса, seeds и возможный bank-derived seed confound; не обещать×1.5/×2 прирост.

### C5. Вести отдельный фактический денежный ledger
**Выход:** receipt→оплаченные coupon bytes/hash→drawing→results/category/payout/refund/tax/rounding→net/ROI. Actual ROI=Σverified net/Σverified stake; отдельно modeled и counterfactual-at-fixed-coefficients. Увеличение банка меняет тотализаторные коэффициенты: фиксированный payout-counterfactual не actual ROI.
4997 screenshot: stake4980/return10154.48/net5174.48, но strategy/coupon binding не доказан; не приписывать Sports по13-hit.4998 qv3 wager USER_REPORTED, сумма/bytes/receipt не подтверждены. Автоматический all-four postmortem не является доказательством фактической ставки.
**Успех:** разрешены все суммы и связи либо явное `UNVERIFIED`; **отказ от profit claim** при неизвестных связях, смешении counterfactual/actual или выборе только удачных тиражей.

### C6. Упростить одну доказанную дублирующуюся ветку, не защиту
Scoped audit показывает net **+1515 runtime02, +1610 observer03, +1923 F4**, не уменьшение проекта. Первое ограничение: сопоставить только два места — `src/toto_ai/sports_stats/final_hybrid_comparison.py` и `src/toto_ai/optimizer/strategy_comparison.py` — и выбрать **один действительно эквивалентный** повторяемый путь подготовки/оценивания. Если идентичность контрактов не доказана, завершить без удаления, не строить новый framework.
**Успех будущего refactor:** один canonical flow, реально удалённые production-дубликаты/ветви по scoped diff, byte/result-equivalence, те же candidate/evaluation counts и порядок суммирования; focused regression+Ruff+independent compatibility review. Тестовый код может расти: глобальный LOC не главный критерий.
**Нельзя дедуплицировать как «лишнее»:** current-primary bytes/authority/expiry проверки при reuse **и** перед публикацией, атомарность/chronology/fallback/deadline/protection tests. Это разные моменты доверия. Удалять module/API только после caller inventory и compatibility proof, не сразу по сходству текста.

### C7. Упаковать два стабильных локальных skill, не установить чужой
Первые: **totoai-algorithm-review** и **totoai-backtesting**, на основе текущих `skills/algorithm-review.md` / `skills/backtesting.md`. Отдельный документационный change: `.agents/skills/<name>/SKILL.md` с YAML `name`/`description`, явными входами, выходами, triggers и AGENTS-boundaries. Один canonical текст (перенос с прежней страницы-ссылкой либо thin discovery wrapper, но без двух копий checklist).
**Успех:** schema/link checks; позитивные/негативные trigger cases для каждого skill; категория13=distance≤2,14≤1,15=exact и provenance/бюджетные правила сохранены. Oracle помечен diagnostic-only, не качество/ROI proof. Обычный read-only вопрос не должен запускать backtest или операцию; без fixtures источники/consent не выдумываются. Никаких global/plugin/foreign installs.
Research skill — после стабилизации input/output контракта. Operator skill — позже: вынести incident/PID/review-status/drawing даты в task receipts/memory, оставить стабильную процедуру, explicit-only invocation (`allow_implicit_invocation:false` в локальном agents/openai.yaml по предоставленному аудиту). Skill не выдаёт полномочий, не меняет gate и не обещает idle-chat delivery.

## Оценки и следующий выбор

Измерено ранее: полный same-input166/четыре семейства offline replay **198.859с**, обе EV пересчитаны; это не LaunchAgent end-to-end и не249/332 benchmark. Три прежних166-size повтора≈597с — лишь арифметика, **не ETA sweep**. G1worker peak≈391MB — не total RSS. После разрешения первый ресурсный checkpoint — один bounded frozen pilot с wall/CPU/RSS/counts/progress; лишь затем оценка249/332. Fit/data/дедупликация не имеют подтверждённого ETA; количественный прирост банка неизвестен.

**Следующее решение пользователя:** утвердить весь явно определённый план/объём одним разрешением либо выбрать его часть (например C1–C3 или документационную C7). После такого утверждения обычные включённые checkpoints не требуют повторных согласований; выход за согласованные границы требует отдельного разрешения. До утверждения предложение не считается запущенным. Новые количественные данные MODELS могут дополнить C4 отдельной версией, ожидать их сейчас не нужно. Ничего не реализовано/измерено/активировано этим планом.

## Основания (сохранённый контекст, без новых web/DB/model calls)

- [MODELS context](/Users/turshevr/.codex/worktrees/a7aa/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/MODEL_QUALITY_BANK_CONTEXT.md), companion JSON SHA `a5c784ca61b9ce80a6ee79cc05b44972850b9fb1ab484e06b4e7d87626a0ad1d`.
- [REVIEW simplification/skills audit](/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/AUDIT_SIMPLIFICATION_SKILLS_HANDOFF.md), companion JSON SHA `271376c88f844099cd27c26c4234bcb317216c3abaab7e665ac6bfacec2238bf`.
- [Актуальный preflight PASS](/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/PREFLIGHT4999_RETRY_AUTHORIZED_HANDOFF.md). Это более свежий runtime receipt, чем датированные сведения дочерних контекстов.
