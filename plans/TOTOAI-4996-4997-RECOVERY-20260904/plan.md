# Leakage-safe Sports Analytics v3 and robust improvement plan

**Статус:** `RESEARCH ONLY — NO SOURCE/OPERATOR/SCHEDULER MUTATION`  
**Цель:** улучшать вероятности до оптимизации пакета и проверить кандидаты на
одинаковых замороженных input/bank/stake для тиражей 4990–4996.

## 1. Неподвижные границы

1. P0 automation имеет безусловный приоритет. Research-команды:
   - не импортируют и не вызывают scheduler/operator/morning/post-draw код;
   - не обращаются к сети и не используют внешние модели;
   - не пишут в `data/`, `reports/rehearsal/`, operator/scheduler каталоги или
     production SQLite;
   - пишут только в явно переданный `reports/research/<run-id>/`, работают с
     `max_workers=1`, ограниченным runtime и видимым progress не реже 10 секунд;
   - при любой identity/hash/chronology ошибке завершаются fail-closed, оставляя
     BK/control неизменным.
2. Текущий этап не меняет source/operator/scheduler и не генерирует wagering
   package. Все будущие output имеют `operator_compatible=false`,
   `automatic_wagering=false`, `profitability_proven=false`.
3. Существующие ordered coupon bytes неизменяемы. Replay читает купоны в
   исходном порядке; не сортирует, не переставляет и не пишет их заново.
   Best-coupon ranking хранится отдельным списком `(one_based_position,
   objective, model, probability)` и никогда не меняет package order.
4. Никаких выводов о прибыли. Hits, P(13+), P(14+), P(15) и concentration —
   разные метрики. Payout/profit/ROI не вычисляются без фактически поставленного
   hash-bound пакета и authoritative payout evidence.

## 2. Immutable replay contract 4990–4996

Для каждого тиража фиксируется один `ReplayFoldManifest`:

- drawing ID/number, plan ID и SHA-256 scheduler plan;
- exact final-input path/hash, probability-input hash и `captured_at`;
- exact archived quality-v2 package path/hash;
- Sports v2 artifact/path/hash и его `as_of`/coverage/fallback;
- Sports v3 source manifest/snapshot hashes и per-event source availability;
- terminal result snapshot/hash, но он открывается только после фиксации
  probability/package prediction hashes;
- requested/effective bank, stake и exact coupon count.

Обязательная equal-input матрица: один и тот же final input, 4 980 RUB, stake
30 RUB и 166 coupons для каждой стратегии каждого тиража. Любое расхождение
делает fold `INVALID_EQUAL_INPUT`, а не «исправляется» пересчётом.

4990 остаётся в scoreboard, но Sports v3 использует exact BK fallback из-за
отклонённого raw-history target binding. 4991 — обязательный all-missing
negative-control. 4996 остаётся `PENDING_RESULT`, пока terminal result не
пройдёт identity/hash verification.

## 3. Leakage-safe walk-forward

Единица разбиения — целый тираж, не событие. Для target drawing `d`:

1. Разрешены labels только из тиражей `< d`, чьи result snapshots были доступны
   до `prediction_as_of(d)`. Ни один исход того же тиража не участвует в fit,
   scaling, imputation, calibration, threshold/hyperparameter selection.
2. `prediction_as_of` равен времени замороженного Sports snapshot и не позже
   final-input `captured_at`. Исторический матч допустим только если:
   - exact team/event identity подтверждена;
   - raw source capture `<= prediction_as_of`;
   - terminal status уже присутствует в raw capture;
   - history kickoff строго меньше target kickoff.
3. Imputer, scaler, residual model и calibrator обучаются заново только на
   training portion fold. Hyperparameter selection использует вложенный
   expanding-window по более ранним тиражам; target fold никогда не участвует.
4. Cold start: пока нет минимум 3 полностью завершённых training drawings и 45
   target events, Sports v3 обязан вернуть exact BK identity. Это применяется
   без исключений к ранним folds.
5. Сначала записываются и хэшируются feature table, fitted transform/model,
   probabilities и package prediction; только затем открывается result snapshot
   и считается settlement.
6. Отчёт хранит для каждой строки `train_drawing_max`, train row IDs,
   `prediction_as_of`, source timestamps и результат автоматического
   `leakage_violation_count`. Допустимое значение — только 0.

4990–4995 являются design-informed development replay, потому что их aggregate
уже прочитан при выборе эксперимента. 4996 может считаться первым locked
holdout только при доказуемой pre-result фиксации candidate hash; иначе он тоже
диагностический, без OOS-claim.

## 4. Sports v3 probability definition

BK остаётся untouched prior. Primary candidate — регуляризованный
multinomial residual:

```text
z_bk = centered(log(p_bk))
q_raw = softmax(z_bk + w_reliability * r_theta(x))
q_v3  = project_to_residual_cap(q_raw, p_bk)
```

- `r_theta(x)` имеет sum-to-zero class logits и L2 regularization.
- `w_reliability` вычисляется только из предматчевой source/feature coverage и
  prior-match counts; диапазон `[0, 0.20]`.
- Жёсткий residual cap: `sum(abs(q_v3 - p_bk)) <= 0.20` для каждого события
  (total variation `<= 0.10`). Нарушение даёт exact BK fallback.
- Никаких league/team one-hot на текущем малом корпусе и никакого oversampling
  ничьих: оба ухудшают оценку calibration при 90–105 событиях.

### Предматчевые predictors

- симметричные разности rolling PPG, goal difference, goals for/against;
- opponent-adjusted strength/form, рассчитанные только из более ранних матчей;
- exponential recency weights, venue splits, rest и 7/14-day congestion;
- standings rank/points/goal difference только при exact league/season/team
  identity и timestamp `<= prediction_as_of`;
- предматчевые BK margin/entropy и explicit reliability/missing indicators.

`actual outcome`, `actual draw`, actual market rank, score/result target event,
post-kickoff lineup и post-result package metrics запрещены в predictor
allowlist. Lineups/injuries не входят в v3 до появления отдельного надёжного
timestamped source contract.

### Missing-history policy

- Нет exact target fixture или обеих team histories: exact BK probabilities;
  равенство проверяется с tolerance `1e-15` и canonical probability hash.
- Частичная feature availability: numeric imputation только training-fold
  median + explicit missing indicator; residual вес уменьшается пропорционально
  минимальной reliability стороны.
- Недостаточный venue history не заменяется aggregate league form.
- Source rejection (включая 4990 deadline mismatch) не маскируется как обычный
  null: это отдельный reason и полный BK fallback.

## 5. Предобъявленные абляции

| ID | Вероятности | Draw calibration | Missing handling | Назначение |
|---|---|---|---|---|
| A0 | untouched BK | off | n/a | основной control |
| A1 | frozen Sports v2 | current v2 | event-local BK fallback | текущий challenger |
| A2 | v3 core residual | off | strict complete-event fallback | эффект новых sports features |
| A3 | v3 core residual | on | strict complete-event fallback | чистый эффект draw calibration |
| A4 | v3 full residual | on | fold-only imputation + indicators + reliability gate | полный кандидат |
| A5 | v3 full residual | off | как A4 | interaction sanity-check draw × missing |

Draw calibration — только один bounded draw-vs-nondraw logit residual,
обученный на предыдущих fold labels. Его inputs — предматчевые BK margin,
entropy и sports reliability; фактический DRAW не является входом.

Порядок сравнения фиксирован: A0→A1→A2→A3→A4/A5. Нельзя выбирать лучший
вариант по одному тиражу или менять пороги после просмотра 4996.

## 6. Feature coverage audit — acceptance

Первый implementation slice только строит и проверяет таблицы, без fitting.

1. Ровно 90 target rows для 4990–4995, 15 уникальных orders на тираж; 4996
   добавляется отдельным 15-row extension после exact snapshot binding.
2. Source-level dry-run disposition воспроизводится точно:
   - 4990 `SOURCE_REJECTED/final input deadline mismatch`;
   - complete counts 4991–4995: `0, 15, 11, 13, 13`;
   - missing counts: `15, 0, 4, 2, 2`.
3. Для каждой predictor-колонки опубликованы non-null count/rate, distribution
   prior/venue match count и reason counts. Source availability не смешивается
   с predictor non-null coverage.
4. `leakage_violation_count=0`, `post_as_of_source_count=0`,
   `same_or_future_kickoff_history_count=0`, duplicate identity count 0.
5. Повторный запуск на тех же bytes даёт одинаковые semantic/output hashes;
   изменение одного source byte или timestamp либо меняет hash, либо fail-closed.
6. Audit сообщает фактическую coverage без минимального «целевого» числа. Если
   full-feature coverage ниже 70%, activation review запрещён; данные не
   заполняются для достижения порога.

## 7. Probability acceptance gate

Сначала публикуются A0–A5 по всем доступным folds. A4 допускается к package
research только если после completion 4996 выполнены все условия:

1. 7/7 folds и 105/105 events имеют valid equal-input manifests; для 4990/4991
   допустим exact BK fallback, но не исключение из denominator.
2. Aggregate paired deltas A4 vs A0:
   - multiclass log loss `<= -0.0015`;
   - multiclass Brier `<= -0.0010`;
   - top-confidence ECE `<= 0`;
   - top-correct count не ниже BK более чем на 1 событие.
3. Stability: ни один fold не ухудшает BK больше чем на `+0.020` log loss или
   `+0.010` Brier. Публикуется deterministic 10 000-sample drawing-cluster
   bootstrap 95% CI; CI не превращается в claim при семи clusters.
4. Draw block A3 vs A2 и A4 vs A5:
   - one-vs-rest draw Brier улучшается минимум на `0.0010` против BK;
   - non-draw multiclass log loss ухудшается не более чем на `0.0010`;
   - aggregate log loss не хуже соответствующей no-draw абляции.
   Если блок не проходит, draw calibration отключается; другие v3 features не
   получают его результат автоматически.
5. Missing block:
   - fully missing/source-rejected rows совпадают с BK до `1e-15` и по hash;
   - A4 не ухудшает aggregate log loss более чем на `0.0010` относительно A3;
   - covered-event и missing-event metrics опубликованы отдельно.
6. Residual cap, finite positive normalized probabilities и deterministic hash
   проходят на 105/105 rows. Любая ошибка отклоняет A4 целиком.

Это исторический research screen, не доказательство superiority. Даже успешный
gate разрешает лишь prospective paper tracking.

## 8. Robust-v2 package improvement

Robust-v2 реализуется только после probability gate. Он создаёт отдельную
research-only package membership и не изменяет/переставляет существующие
quality-v2, Sports-v2, quality-v3 или robust-v1 packages.

### Модели и objective

- Сценарии: BK, frozen Sports v2, принятый v3, v3-no-draw и существующие
  flatten-10/flatten-20 stress models.
- Hard constraints: 166 уникальных купонов, cost 4 980 RUB, quality-v2 exposure
  floors, hard cap и control-relative concentration bounds.
- Lexicographic objective:
  1. maximize worst-model exact package P(13+);
  2. maximize worst-model exact P(14+) и P(15);
  3. maximize mean-model P(13+);
  4. minimize max event/outcome share и mean/max event HHI;
  5. deterministic membership-hash tie-break.
- Sampled coverage может создавать shortlist, но финальное решение и отчёт
  используют exact union P(13+)/P(14+)/P(15).
- Если нет допустимого улучшения, результат — exact immutable quality-v2
  fallback; это валидный non-improvement, а не повод ослабить constraints.

### Package-level acceptance

Для каждого fold и каждой стратегии отчёт обязан содержать exact P(13+),
P(14+), P(15) под каждой probability model; best/mean hits, полную hit
distribution и counts `>=13/14/15`; max event/outcome share, mean/max HHI,
zero exposure, pairwise overlap/Jaccard и package hashes.

Robust-v2 проходит historical package screen, только если:

1. input/bank/stake/capacity идентичны control во всех 7 folds;
2. его BK P(13+), P(14+), P(15) не ниже quality-v2 ни в одном fold с tolerance
   `1e-12`;
3. worst-model P(13+) не ниже robust-v1 ни в одном fold, строго выше минимум в
   2 folds и geometric-mean improvement не меньше 2%;
4. max event/outcome share и max HHI не выше одновременно quality-v2 и
   robust-v1 для соответствующего fold; zero-exposure count равен 0;
5. post-settlement diagnostic: суммарный `>=13` count и медианный best hits не
   ниже обоих controls, а worst-fold best-hits deficit к quality-v2 не хуже -1.
   Эти outcomes не участвуют в выборе membership и не доказывают edge;
6. два запуска дают те же membership и ordered-output hashes. Если membership
   совпадает с robust-v1/control, ordered bytes должны быть полностью
   идентичны; best coupon не перемещается на первую строку.

Непрохождение любого package gate оставляет robust-v2 research-rejected и не
влияет на operator/control.

## 9. Verification and reporting

- Failing-first unit tests для chronology, same-drawing leakage, train-only
  transforms, 4990 rejection, 4991 all-missing identity и package-order
  invariance.
- Determinism tests с изменением input byte/timestamp/hash.
- Focused pytest и Ruff для изменённых research-only файлов; полный pytest и
  Ruff перед любым commit. Тесты запускаются вне P0 scheduler window, одним
  worker и с bounded timeout/progress.
- Отчёт всегда разделяет:
  - event probability quality;
  - package modeled probability;
  - realized hits;
  - concentration;
  - payout/profitability (по умолчанию `UNKNOWN/NOT PROVEN`).
- После исторического screen кандидат только замораживается для минимум 30
  prospective drawings / 450 events. Один 4996 или любой один тираж не выбирает
  постоянную модель.

## 10. Ближайшие три реализации по приоритету

1. **P1 — read-only Sports v3 coverage auditor.** Соединить explicit
   validate-only manifest с `build_sports_v3_feature_table`, выпустить
   deterministic 4990–4995 source/feature coverage audit и regression на 4990/
   4991. Никакого fitting, SQLite write или operational import.
2. **P2 — drawing-level walk-forward probability/ablation harness.** Реализовать
   A0–A5, train-only transforms, bounded BK residual, draw/missing gates и
   sealed prediction-before-result artifacts; затем выполнить 4990–4996 при
   наличии terminal 4996 result.
3. **P3 — exact-P13 robust-v2 research selector and replay.** Только после
   успешного probability gate: global candidate search, exact multi-model
   category objective, hard concentration constraints, immutable package-order
   checks и полный package-level report.

## Stop conditions

- Любое вмешательство в P0, сеть, БД, scheduler/operator или недоказанная
  identity/chronology — немедленный stop.
- Нет terminal result 4996 — replay остаётся `INCOMPLETE`, пороги не меняются.
- Probability gate не пройден — robust-v2 не реализуется как кандидат.
- Coverage <70% или меньше 30 prospective drawings / 450 events — никакой
  activation/superiority claim.
- Нет authoritative placed-package/payout evidence — profit/ROI остаются
  неизвестными.
