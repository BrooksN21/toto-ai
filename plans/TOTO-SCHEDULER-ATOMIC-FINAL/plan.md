# TOTO-SCHEDULER-ATOMIC-FINAL Implementation Plan

> **Для исполнителя:** выполнять задачи последовательно, через TDD. Этот план
> не разрешает автоматическое размещение ставок. В текущей planning-only
> итерации код, commit и push не выполняются.

## Статус реализации на 2026-07-28

Кодовая часть плана реализована в рабочем дереве: atomic one-snapshot final,
пять независимых ticks T−45/T−30/T−20/T−16/T−12, T−12 cutoff, persistent
state/lock, bounded retry, crash recovery, manifest/archive provenance и
нулевой `NO BET`. Динамический morning dispatcher реализован по отдельному
addendum.

После закрытия финальных review findings проверки: полный pytest —
`1428 passed`, focused scheduler/morning/CLI набор — `175 passed`,
детерминированная fixture rehearsal — `42 passed` один раз; Ruff и
`git diff --check` прошли.
Ни generic morning dispatcher, ни schema-v4 evening scheduler не установлены.
Пять устаревших LaunchAgent удалены. Activation-disabled live drill 4958
deferred без plan/package, потому что API-Sports не содержит женское событие
№5. Следующий шаг — provider-neutral schedule fallback и повторный 15/15 drill.
Чек-листы ниже сохранены как исходная пошаговая спецификация, а не как текущий
operational status.

## Корректирующий статус на 2026-07-29

Четыре дефекта из `context-2026-07-29.md` исправлены regression-first:

- после network preparation используется новый UTC sample; morning dispatch
  не создаёт план в/после T−45;
- `FinalInputSnapshot.captured_at` фиксирует completion exact-detail response;
- late archive recovery удаляет `package.csv` и `package-archive.json` перед
  zero-cost `NO BET`;
- final calculation, subprocess timeout и каждый retry admission применяют
  actionable cutoff `T−12 − publication_reserve_seconds`;
- package/archive-manifest write, durable archive, recovery, status и
  `.bet-ready` marker используют зарезервированный интервал и hard T−12.
  Recovery не позже hard T−12 может завершить publication; после hard T−12
  stale package/archive files удаляются и результат становится zero-cost
  `NO BET`.

Проверки remaining reserve semantics: exact boundary set —
`5 passed in 0.68s`; focused scheduler/morning/final-input/state/CLI набор —
`175 passed in 6.11s`; полный pytest — `1443 passed in 221.96s`; Ruff и
`git diff --check` прошли. LaunchAgent не устанавливался, commit/push не
выполнялись, автоматическое размещение ставок не добавлено.

**Цель:** заменить хрупкий старый one-shot scheduler на resumable
phase-state protocol, в котором один immutable fresh final detail snapshot
является единственным входом final preparation, package calculation, safety и
publication.

**Архитектура:** LaunchAgent вызывает idempotent scheduler tick в T−45, T−30,
T−20, T−16 и T−12. Warmup/refresh являются diagnostic и не блокируют final.
Final attempt атомарно сохраняет один direct-network drawing detail и передаёт
тот же payload всем downstream компонентам без повторного fetch. Package и
archive криптографически связаны с snapshot; T−12 является hard publish/no-bet
cutoff.

**Стек:** Python 3.12, Typer, SQLAlchemy/SQLite, launchd plist, pytest,
существующие canonical JSON/SHA-256/atomic-file helpers.

## Global constraints

- Только standalone `/Users/turshevr/toto-ai`.
- Не использовать Arcadia/Yandex/Gena/Startrek или внешнюю память.
- Не изменять BK/pool probability math, EV ranking, package safety thresholds,
  category, bank или stake semantics.
- Не добавлять автоматическое размещение ставок.
- Research, offline replay и historical backtests должны сохранить поведение.
- Все production package inputs должны быть pre-deadline и immutable.
- Warmup market changes считаются нормальными; post-capture tamper — ошибкой.
- Успешный calculation завершается до actionable cutoff; package publication
  выполняется сразу после него и завершается не позднее hard T−12.
- Любой `NO BET` обязан быть coupon-free и zero-cost.

---

## File map

### Новые файлы

- `src/toto_ai/runner/final_input.py`
  - immutable `FinalInputSnapshot`;
  - direct exact-detail capture;
  - canonical serialization/load/hash verification;
  - normalized probability hash.
- `src/toto_ai/runner/scheduler_state.py`
  - persistent plan-scoped state;
  - phase/attempt transitions;
  - lock, lease, retry classification и restart recovery.
- `tests/test_runner_final_input.py`
  - snapshot identity, deterministic bytes, one-fetch и tamper tests.
- `tests/test_scheduler_atomic_final_end_to_end.py`
  - fake-clock acceptance matrix из требований задачи.

### Изменяемые файлы

- `src/toto_ai/runner/scheduler.py`
  - plan schema v4;
  - новые deadlines/triggers;
  - tick orchestration;
  - package publication from final-input-bound attempt.
- `src/toto_ai/runner/orchestration.py`
  - execution from already pinned final target;
  - no second target/detail resolve in atomic mode.
- `src/toto_ai/runner/models.py`
  - final-input provenance in runner result.
- `src/toto_ai/runner/reports.py`
  - manifest schema v5 and canonical zero-cost `NO BET`.
- `src/toto_ai/cli.py`
  - internal final-snapshot option/command;
  - `scheduler-execute` resumable tick behavior.
- `src/toto_ai/ev/drawing.py`
  - `derived_brief=()` for suppressed `NO BET`;
  - preserve existing payload-injection path.
- `src/toto_ai/operations/sync_prepare.py`
  - reuse parser/persistence from an already captured payload without network.
- `src/toto_ai/external_odds/preparation.py`
  - preparation result bound to exact final snapshot evidence.
- `src/toto_ai/external_odds/team_registry.py`
  - load/refresh readiness using exact source snapshot hash and CAS.
- `src/toto_ai/db/models.py`
  - additive pre-bet archive final-input provenance.
- `src/toto_ai/operations/finished_draw.py`
  - pre-bet manifest v2 import/verification.
- `tests/test_runner_scheduler.py`
  - plan/tick/state/retry/publication tests.
- `tests/test_runner_orchestration.py`
  - atomic mode makes no later target fetch.
- `tests/test_runner_reports.py`
  - canonical computed/uncomputed zero-cost `NO BET`.
- `tests/test_runner_cli.py`
  - CLI and exact one-detail-call acceptance.
- `tests/test_sync_prepare_operation.py`
  - captured-payload preparation without network.
- `tests/test_finished_lifecycle.py`
  - archive v2 final-input binding and legacy compatibility.
- `memory-bank/ARCHITECTURE.md`
  - only after implementation passes.
- `memory-bank/CURRENT_STATE.md`
  - exact verification and operational migration state.
- `memory-bank/DECISIONS.md`
  - temporal invariant and scheduler state decision.
- `memory-bank/ROADMAP.md`
  - production blocker completion state.

---

## Task 1: Canonical zero-cost NO BET

**Deliverable:** любой computed или uncomputed `NO BET` имеет нулевые поля,
`coupons=[]`, `derived_brief=[]` и принимается scheduler parser.

**Files:**

- Modify: `src/toto_ai/ev/drawing.py`
- Modify: `src/toto_ai/runner/reports.py`
- Test: `tests/test_runner_reports.py`
- Test: `tests/test_runner_scheduler.py`
- Test: `tests/test_ev_drawing.py`

- [ ] Добавить regression fixture из manifest №4957: safety отвергает
  вычисленный пакет после EV.
- [ ] Проверить RED: producer выдаёт 15 пустых `derived_brief`, parser отвечает
  `NO BET runner manifest is not zero-cost`.
- [ ] Изменить `_empty_no_bet()` так, чтобы `derived_brief=()` и все package
  monetary/count fields были нулевыми.
- [ ] Добавить один canonical report helper для computed/uncomputed `NO BET`,
  чтобы runner report не собирал нулевой пакет несколькими способами.
- [ ] Проверить, что diagnostic safety evidence может сохраняться, но
  `uploadable_coupons=[]`, package bytes/path/hash отсутствуют.
- [ ] Запустить:

  ```bash
  .venv/bin/python -m pytest -q \
    tests/test_ev_drawing.py \
    tests/test_runner_reports.py \
    tests/test_runner_scheduler.py
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Canonicalize zero-cost no-bet manifests"
  ```

---

## Task 2: Immutable atomic final-input snapshot

**Deliverable:** один fresh exact-detail payload сохраняется run-scoped,
детерминированно хешируется и загружается только после полной проверки.

**Files:**

- Create: `src/toto_ai/runner/final_input.py`
- Create: `tests/test_runner_final_input.py`
- Modify: `src/toto_ai/runner/models.py`

**Required interface:**

```python
@dataclass(frozen=True)
class FinalInputSnapshot:
    schema_version: int
    plan_id: str
    attempt_id: str
    drawing_id: int
    drawing_number: int
    deadline: datetime
    captured_at: datetime
    target_fingerprint: str
    detail_payload_sha256: str
    probability_input_sha256: str
    timing_override_sha256: str | None
    payload: Mapping[str, object]

def capture_final_input(
    *,
    client: TotoBriefClient,
    plan: SchedulerPlan,
    attempt_id: str,
    captured_at: datetime,
    destination: Path,
    timing_override_sha256: str | None,
) -> FinalInputSnapshot: ...

def load_final_input(path: Path, *, expected_plan: SchedulerPlan) \
        -> FinalInputSnapshot: ...
```

- [ ] Написать RED tests:
  - direct exact detail вызывается ровно один раз;
  - 15 event orders и drawing identity обязательны;
  - canonical bytes/hash детерминированы;
  - snapshot future/after-deadline отклоняется;
  - изменение одного probability value меняет оба relevant hash;
  - изменение сохранённых bytes отклоняется при load.
- [ ] Сохранять canonical JSON через существующий exclusive atomic/fsync
  boundary; symlink/path escape запрещены.
- [ ] Вычислять:
  - `detail_payload_sha256` из canonical exact response;
  - `probability_input_sha256` из normalized ordered 15×3 BK matrix;
  - snapshot content SHA из metadata + payload hashes.
- [ ] Не читать mutable preparation row при вычислении snapshot identity.
- [ ] Добавить final-input provenance в `DrawingRunnerResult`, но оставить
  `None` для research/offline/legacy paths.
- [ ] Запустить:

  ```bash
  .venv/bin/python -m pytest -q tests/test_runner_final_input.py
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Add immutable final drawing input snapshots"
  ```

---

## Task 3: Consume one snapshot through preparation and EV

**Deliverable:** final preparation, target pin и package используют один
`FinalInputSnapshot`; внутри attempt нет второго `drawing_info()`.

**Files:**

- Modify: `src/toto_ai/runner/orchestration.py`
- Modify: `src/toto_ai/cli.py`
- Modify: `src/toto_ai/operations/sync_prepare.py`
- Modify: `src/toto_ai/external_odds/preparation.py`
- Modify: `src/toto_ai/external_odds/team_registry.py`
- Test: `tests/test_runner_orchestration.py`
- Test: `tests/test_runner_cli.py`
- Test: `tests/test_sync_prepare_operation.py`

**Required interfaces:**

```python
def synchronize_drawing_payload(
    payload: Mapping[str, object],
    *,
    fetched_at: datetime,
    session_factory: sessionmaker[Session],
    expected_drawing_id: int,
    expected_drawing_number: int,
) -> DetailSyncResult: ...

def run_drawing_from_final_input(
    *,
    snapshot: FinalInputSnapshot,
    config: DrawingRunnerConfig,
    ...,
) -> DrawingRunnerResult: ...
```

- [ ] Написать RED end-to-end spy test:
  - pool меняется между warmup и final;
  - final capture видит новую matrix;
  - preparation refresh получает этот hash;
  - EV и safety используют этот же hash;
  - после capture любые client detail calls вызывают test failure.
- [ ] Разделить runner orchestration на:
  - legacy/research resolver path;
  - production atomic-final path с already-pinned target.
- [ ] Передать `snapshot.payload` в существующий
  `build_open_ev_package(payload=..., fetched_at=...)`.
- [ ] Удалить production final re-fetch из `_build_runner_package`; legacy
  direct research API сохранить.
- [ ] Final preparation должна обновлять mutable DB evidence из snapshot, но
  downstream final run обязан доверять run-scoped snapshot, а не сравнивать с
  более ранней warmup row.
- [ ] Проверить exact 15 pins, fixture orientation/start revalidation и
  readiness source hash относительно snapshot.
- [ ] Запустить:

  ```bash
  .venv/bin/python -m pytest -q \
    tests/test_runner_orchestration.py \
    tests/test_runner_cli.py \
    tests/test_sync_prepare_operation.py \
    tests/test_team_resolution.py
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Run final package from one atomic input snapshot"
  ```

---

## Task 4: Persistent resumable scheduler state machine

**Deliverable:** warmup failures не завершают execution; final и cutoff
выполняются отдельными idempotent ticks с bounded retry.

**Files:**

- Create: `src/toto_ai/runner/scheduler_state.py`
- Modify: `src/toto_ai/runner/scheduler.py`
- Test: `tests/test_runner_scheduler.py`

**State model:**

```text
warmup: pending|running|complete|retryable_failed|permanent_failed
refresh: pending|running|complete|retryable_failed|permanent_failed
final: pending|running|retryable_failed|complete|no_bet|integrity_failed
publish: pending|complete|no_bet|integrity_failed
terminal: null|bet_ready|no_bet|failed
```

Каждый transition содержит timestamp, attempt ID, reason code, previous state
SHA и current state SHA.

- [ ] Написать RED fake-clock tests:
  - T−45 transient failure не блокирует T−20 final;
  - T−20 first failure и T−16 retry success;
  - permanent identity/tamper failure не retry;
  - duplicate tick после success ничего не меняет;
  - concurrent tick не создаёт второй attempt;
  - orphan `running` attempt восстанавливается как abandoned, не переиспользует
    partial artifacts.
- [ ] Добавить plan schema v4 deadlines/config:

  ```text
  warmup_at = T−45
  refresh_at = T−30
  final_at = T−20
  retry_at = T−16
  publish_deadline = T−12
  minimum_final_runtime_budget = 180s
  publication_reserve = 45s
  max_final_attempts = 2
  transient_backoff = bounded 2s/5s/10s
  ```

- [ ] Использовать process/file lock внутри output boundary. Lock не является
  state; после crash новый tick может продолжить.
- [ ] Каждая final attempt имеет отдельный immutable directory. Ничего не
  перезаписывается.
- [ ] Retry разрешать только если:

  ```text
  now + minimum_final_runtime_budget + publication_reserve
      <= publish_deadline
  ```

- [ ] Warmup/refresh не создают package и не pin final probabilities.
- [ ] Deadline miss без tamper/config corruption переводит execution в
  canonical `NO BET`, а не оставляет `FAILED` из ранней transient ошибки.
- [ ] Запустить:

  ```bash
  .venv/bin/python -m pytest -q tests/test_runner_scheduler.py
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Add resumable scheduler phase state"
  ```

---

## Task 5: Multi-trigger LaunchAgent and restart-safe CLI

**Deliverable:** один сгенерированный LaunchAgent независимо запускает ticks в
T−45, T−30, T−20, T−16 и T−12.

**Files:**

- Modify: `src/toto_ai/runner/scheduler.py`
- Modify: `src/toto_ai/cli.py`
- Test: `tests/test_runner_scheduler.py`
- Test: `tests/test_runner_cli.py`

- [ ] Написать RED plist test: `StartCalendarInterval` — массив из пяти exact
  local timestamps, не один dict.
- [ ] `scheduler-execute --plan ...` должен быть short-lived resumable tick,
  а не sleeping process до T−12.
- [ ] При запуске:
  - до due phase — deterministic no-op;
  - после missed warmup — выполнить следующую due phase;
  - после T−12 — только finalize zero-cost `NO BET`;
  - после terminal — verify и no-op.
- [ ] Старый schema-v3 plan разрешить только для inspection/dry-run. Production
  execute должен fail closed с сообщением о regeneration.
- [ ] LaunchAgent/wrapper остаются secret-free кроме secure `.env` загрузки;
  current absolute cwd/path checks сохранить.
- [ ] Добавить restart acceptance: первый invocation падает после T−45,
  второй в T−20 успешно формирует и публикует package.
- [ ] Запустить:

  ```bash
  .venv/bin/python -m pytest -q \
    tests/test_runner_scheduler.py \
    tests/test_runner_cli.py
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Make scheduler launch resumable across phase ticks"
  ```

---

## Task 6: Bind publication/archive to exact final input

**Deliverable:** `.bet-ready`, package snapshot и durable archive доказывают,
какой exact final detail был использован.

**Files:**

- Modify: `src/toto_ai/runner/scheduler.py`
- Modify: `src/toto_ai/runner/reports.py`
- Modify: `src/toto_ai/db/models.py`
- Modify: `src/toto_ai/operations/finished_draw.py`
- Test: `tests/test_runner_scheduler.py`
- Test: `tests/test_runner_reports.py`
- Test: `tests/test_finished_lifecycle.py`

- [ ] Добавить runner manifest schema v5:

  ```text
  final_input.path
  final_input.captured_at
  final_input.snapshot_sha256
  final_input.detail_payload_sha256
  final_input.probability_input_sha256
  final_input.attempt_id
  ```

- [ ] Package manifest и archive manifest v2 должны включать те же hashes.
- [ ] Добавить nullable legacy-safe archive columns:
  `final_input_sha256`, `probability_input_sha256`,
  `final_input_captured_at`.
- [ ] Legacy archive rows остаются читаемыми, но не могут быть переобозначены
  как atomic-final provenance.
- [ ] Перед publication проверить:
  - snapshot bytes/hash;
  - package bytes/hash;
  - safety probability hash == final probability hash;
  - preparation evidence source hash == final snapshot hash;
  - attempt/plan/drawing/deadline identity;
  - package calculation completed at
    `<= T−12 − publication_reserve_seconds`;
  - current publication time `<= T−12`.
- [ ] Не выполнять live API re-fetch на freeze/publication. API может
  legitimately измениться после captured final snapshot.
- [ ] Crash recovery:
  - archive создан, marker отсутствует, time не позже hard T−12 →
    verify and finish;
  - time позже hard T−12 → удалить stale package/archive manifest, не
    создавать `.bet-ready`, terminal `NO BET`;
  - tampered archive/snapshot → terminal `FAILED`.
- [ ] Запустить:

  ```bash
  .venv/bin/python -m pytest -q \
    tests/test_runner_scheduler.py \
    tests/test_runner_reports.py \
    tests/test_finished_lifecycle.py
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Bind pre-bet publication to atomic final evidence"
  ```

---

## Task 7: End-to-end acceptance matrix

**Deliverable:** весь требуемый протокол доказан fake-clock tests, включая
реальное изменение пула и failures.

**Files:**

- Create: `tests/test_scheduler_atomic_final_end_to_end.py`
- Modify: `tests/test_runner_end_to_end.py`
- Modify: `tests/test_runner_offline_replay.py`

- [ ] Реализовать one shared fake API, которая возвращает:
  - T−45 detail A;
  - T−25 detail B;
  - final detail C;
  - optional transient first failure;
  - optional tampered saved snapshot.
- [ ] Acceptance 1: A→B→C не считается mismatch; package/safety/report/archive
  используют только C.
- [ ] Acceptance 2: первый final exact fetch transient-fails, bounded retry
  succeeds; package published before T−12.
- [ ] Acceptance 3: process exits after warmup failure; later tick resumes and
  final succeeds.
- [ ] Acceptance 4: после final capture изменяется live API response D; package
  остаётся valid, потому что consumed C immutable.
- [ ] Acceptance 5: saved C bytes или preparation source hash изменён после
  capture; fail closed, no package publication.
- [ ] Acceptance 6: calculation/archive crosses T−12; terminal zero-cost
  `NO BET`, no `.bet-ready`, no upload package.
- [ ] Acceptance 7: safety rejection serializes valid computed `NO BET` with
  `coupons=[]`, `derived_brief=[]`, `cost=0`.
- [ ] Acceptance 8: duplicate/overlapping ticks produce one terminal package
  and one archive.
- [ ] Acceptance 9: existing research, offline replay и backtest tests
  produce unchanged decisions/hashes where their schemas did not change.
- [ ] Запустить focused suite:

  ```bash
  .venv/bin/python -m pytest -q \
    tests/test_scheduler_atomic_final_end_to_end.py \
    tests/test_runner_end_to_end.py \
    tests/test_runner_offline_replay.py
  ```

- [ ] Запустить полный quality gate:

  ```bash
  .venv/bin/python -m pytest -q
  .venv/bin/python -m ruff check .
  git diff --check
  ```

- [ ] Commit после реализации:

  ```bash
  git commit -m "Verify atomic final scheduler end to end"
  ```

---

## Task 8: Operational migration and first drill

**Deliverable:** новый scheduler установлен только после network-free
acceptance и bounded live rehearsal; старые v3 artifacts не исполняются.

**Files:**

- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/DECISIONS.md`
- Modify: `memory-bank/ROADMAP.md`
- Create at runtime only: `reports/rehearsal/<drawing>-atomic-final-drill/`

- [ ] Обновить memory только фактически реализованными гарантиями и точными
  test counts.
- [ ] Сгенерировать новый schema-v4 scheduler plan в новом output directory;
  не перезаписывать старый 4957 artifact.
- [ ] Выполнить `--simulate` с fake clock и проверить все пять ticks.
- [ ] Выполнить ранний live `RESEARCH ONLY` drill на активном тираже:
  - exact final snapshot создан;
  - detail fetch count внутри attempt равен 1;
  - no package/PLAY marker в research mode.
- [ ] Только после успешного drill вручную установить новый LaunchAgent.
- [ ] До первого реального запуска проверить:
  - plist содержит 5 triggers;
  - `.env` owner/mode;
  - plan exact drawing ID/number/deadline;
  - output path новый и пустой;
  - T−12 не оставляет меньше 12 минут на ручную загрузку.
- [ ] После завершения тиража обязательно выполнить result sync, settlement и
  expected-vs-actual разбор; прибыльность не объявлять по одному тиражу.

---

## Acceptance criteria

Реализация принимается только если одновременно выполнено всё:

1. Final attempt делает ровно один exact detail fetch и downstream не ходит за
   новым detail.
2. Pool/BK changes между warmup и final разрешены.
3. Package, safety, report и archive содержат один final snapshot hash.
4. Post-capture file/evidence tamper блокирует publication.
5. Warmup failure не блокирует самостоятельный final tick.
6. Transient final failure имеет bounded retry/backoff.
7. Calculation, subprocess execution и retry admission прекращаются не позже
   `T−12 − publication_reserve_seconds`.
8. Package/archive/recovery/status/marker могут использовать reserve, но
   завершаются не позже hard T−12.
9. Publication/recovery после hard T−12 завершается zero-cost `NO BET` и
   удаляет stale package/archive files.
10. NO BET не содержит package bytes, coupons или non-empty derived brief.
11. Restart/duplicate/concurrent ticks идемпотентны.
12. Old schema-v3 scheduler plan не становится actionable без regeneration.
13. Research/offline/backtest поведение не изменено.
14. Full pytest, Ruff и `git diff --check` проходят.

## Migration risks

- **Plan/manifest schema churn.** Нужен explicit v3 non-actionable migration,
  иначе старый plist может вызвать старую семантику.
- **Mutable global preparation row.** Она не должна снова стать primary final
  evidence; source snapshot hash обязателен.
- **Double execution.** Multi-trigger launchd требует lock и plan-scoped
  idempotency, иначе возможны два package/archive.
- **Crash между archive и marker.** Recovery может завершиться внутри reserve,
  но должен учитывать hard T−12 и не публиковать поздний marker.
- **Runtime regression.** T−20/T−16/T−12 budgets должны измеряться по stage
  timings; новый provider/statistics код не должен съесть final reserve.
- **Over-classifying errors as transient.** Identity/hash/config/path errors
  никогда не retry.
- **False freshness.** Final exact detail обязан быть direct-network; warmup
  cache не может незаметно стать final snapshot.
- **Manual upload time.** Даже математически valid package бесполезен, если
  опубликован позже T−12; deadline является product requirement.
