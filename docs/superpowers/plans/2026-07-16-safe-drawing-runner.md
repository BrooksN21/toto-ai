# Safe Drawing Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one fail-closed `run-drawing --open` command that preflights immediately, starts final work at T-20, suppresses output at T-5, and orchestrates existing fresh collection, timing, audit, and EV package behavior without placing a bet.

**Architecture:** A small `toto_ai.runner` package owns immutable configuration, target binding, the UTC timing state machine, orchestration, and deterministic reports. Existing prospective collection gains optional pinned-target and stop-time inputs while preserving standalone behavior. The Typer command wires real clients, SQLite, existing audit/EV engines, and Rich progress into the provider-neutral runner.

**Tech Stack:** Python 3.12, Typer, Rich, SQLAlchemy/SQLite, pytest, Ruff, existing TotoBrief/API-Sports, external-odds, and EV modules.

## Global Constraints

- Default final start is T-20; default safety stop is T-5.
- Validate `final_lead_minutes > safety_stop_minutes >= 1`.
- Bank is any positive integer exactly divisible by the configured positive stake; stake defaults to 30 RUB.
- The runner always uses a fresh invocation cache and never exposes shared-cache reuse.
- Preflight and final targets must match drawing ID, number, deadline, and canonical target fingerprint.
- No new runner phase or package publication starts at or after T-5; a package finishing at or after T-5 is suppressed to zero-cost `NO BET`.
- A provider-odds fallback alone does not veto the current TotoBrief-BK package.
- External coverage `GO/PENDING/STOP` remains diagnostic and external probabilities remain audit-only.
- Probability, EV, payout proxy, ranking, category, bank, stake, consensus, coverage-gate, and multi-day eligibility definitions do not change.
- The command never submits a bookmaker bet.
- No API key may enter persistence, cache payloads, reports, progress output, or exception text.
- Real network calls and real sleeping are forbidden in tests.

---

## File Structure

- Create `src/toto_ai/runner/__init__.py`: public runner exports only.
- Create `src/toto_ai/runner/models.py`: immutable runner configuration, pinned target, schedule, and terminal result summaries.
- Create `src/toto_ai/runner/timing.py`: UTC window classification and injectable waiting.
- Create `src/toto_ai/runner/orchestration.py`: provider-neutral preflight-to-package state machine.
- Create `src/toto_ai/runner/reports.py`: canonical JSON/Markdown rendering and rollback-safe pair publication.
- Create `tests/test_runner_timing.py`: configuration, target, window, and fake-clock tests.
- Create `tests/test_runner_orchestration.py`: phase ordering, target binding, cutoff, and decision tests.
- Create `tests/test_runner_reports.py`: deterministic artifacts, path collision, rollback, and coupon suppression tests.
- Create `tests/test_runner_cli.py`: Typer validation, dependency wiring, progress, errors, and secret sanitation.
- Create `tests/test_runner_end_to_end.py`: no-network/no-sleep acceptance through SQLite, audit, EV, and reports.
- Modify `src/toto_ai/external_odds/prospective.py`: optional pinned target and safety stop between passes.
- Modify `tests/test_external_odds_prospective.py`: backward compatibility, target bypass, and stop-time tests.
- Modify `src/toto_ai/cli.py`: register `run-drawing` and operator tables.
- Update project memory and this plan after final verification.

### Task 1: Immutable Runner Domain and UTC Timing

**Files:**
- Create: `src/toto_ai/runner/__init__.py`
- Create: `src/toto_ai/runner/models.py`
- Create: `src/toto_ai/runner/timing.py`
- Create: `tests/test_runner_timing.py`

**Interfaces:**
- Produces: `DrawingRunnerConfig(bank, stake=30, mode="playable", final_lead_minutes=20, safety_stop_minutes=5)`.
- Produces: `PinnedDrawing(target: TargetDrawing, fingerprint: str)` and `pin_drawing(target) -> PinnedDrawing`.
- Produces: `RunnerSchedule(deadline, final_starts_at, safety_stops_at)`.
- Produces: `build_runner_schedule(deadline, config) -> RunnerSchedule`.
- Produces: `runner_window(schedule, now) -> Literal["waiting", "final", "closed"]`.
- Produces: `wait_for_final_window(schedule, now, sleep, progress_callback=None, maximum_sleep_seconds=30.0) -> Literal["final", "closed"]`.

- [ ] **Step 1: Write failing domain and timing tests**

Add tests that instantiate the real types and prove strict validation, fingerprint determinism, exact boundary semantics, a wall-clock jump to closed, bounded sleep, and progress updates:

```python
def test_runner_window_uses_exact_t20_and_t5_boundaries():
    config = DrawingRunnerConfig(bank=4980, stake=30)
    schedule = build_runner_schedule(DEADLINE, config)

    assert runner_window(schedule, DEADLINE - timedelta(minutes=21)) == "waiting"
    assert runner_window(schedule, DEADLINE - timedelta(minutes=20)) == "final"
    assert runner_window(schedule, DEADLINE - timedelta(minutes=5, microseconds=1)) == "final"
    assert runner_window(schedule, DEADLINE - timedelta(minutes=5)) == "closed"


def test_wait_rechecks_wall_clock_and_never_sleeps_past_final_window():
    times = iter((T_MINUS_21, T_MINUS_20))
    sleeps = []
    updates = []

    result = wait_for_final_window(
        schedule,
        now=lambda: next(times),
        sleep=sleeps.append,
        progress_callback=updates.append,
        maximum_sleep_seconds=60.0,
    )

    assert result == "final"
    assert sleeps == [60.0]
    assert updates[0]["phase"] == "waiting"
```

Also reject booleans/non-integers, non-divisible banks, non-UTC datetimes, `final_lead_minutes <= safety_stop_minutes`, invalid modes, malformed fingerprints, and a maximum sleep that is non-finite or non-positive.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runner_timing.py
```

Expected: collection failure because `toto_ai.runner` does not exist.

- [ ] **Step 3: Implement minimal immutable models and timing state machine**

Implement the public shapes exactly:

```python
RunnerWindow = Literal["waiting", "final", "closed"]


@dataclass(frozen=True)
class DrawingRunnerConfig:
    bank: int
    stake: int = 30
    mode: EVMode = "playable"
    final_lead_minutes: int = 20
    safety_stop_minutes: int = 5

    def __post_init__(self) -> None:
        validate_config_bank(self.bank, self.stake)
        if self.mode not in ("research", "playable"):
            raise ValueError("mode must be research or playable")
        _require_positive_int("final_lead_minutes", self.final_lead_minutes)
        _require_positive_int("safety_stop_minutes", self.safety_stop_minutes)
        if self.final_lead_minutes <= self.safety_stop_minutes:
            raise ValueError("final lead must be greater than safety stop")

    @property
    def ev_config(self) -> EVConfig:
        return EVConfig(bank=self.bank, stake=self.stake, mode=self.mode)


def pin_drawing(target: TargetDrawing) -> PinnedDrawing:
    return PinnedDrawing(
        target=target,
        fingerprint=target_fingerprint(
            target.drawing_id,
            target.drawing_number,
            target.deadline,
            target.events,
        ),
    )
```

`wait_for_final_window` must calculate `min(maximum_sleep_seconds, seconds_until_final)`, call no sleeper when already final/closed, and classify again from the injected wall clock after every sleep.

- [ ] **Step 4: Verify GREEN and public exports**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runner_timing.py
.venv/bin/python -m ruff check src/toto_ai/runner tests/test_runner_timing.py
```

Expected: all new tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/runner tests/test_runner_timing.py
git commit -m "Add safe runner timing model"
```

### Task 2: Pinned Prospective Collection and Safety Stop

**Files:**
- Modify: `src/toto_ai/external_odds/prospective.py`
- Modify: `tests/test_external_odds_prospective.py`

**Interfaces:**
- Consumes: existing `TargetDrawing` and `ProspectiveCollectionResult`.
- Extends: `ProspectiveStopReason` with `"safety_stop"`.
- Extends: the existing keyword-only `collect_fresh_open_external_odds`
  signature with `target: TargetDrawing | None = None` and
  `stop_at: datetime | None = None`.
- Preserves: all existing callers when both new arguments are omitted.

- [ ] **Step 1: Write failing pinned-target and cutoff tests**

Add focused tests:

```python
def test_supplied_target_bypasses_open_resolution(monkeypatch, tmp_path):
    monkeypatch.setattr(
        prospective,
        "resolve_open_target",
        lambda *_args, **_kwargs: pytest.fail("must not resolve another target"),
    )
    result = collect_fresh_open_external_odds(
        target=target,
        totobrief_client="unused",
        provider_factory=provider_factory,
        session_factory=session_factory,
        aliases={},
        cache_root=tmp_path,
        now=lambda: NOW,
        monotonic=monotonic,
        sleep=sleep,
    )
    assert result.snapshot.drawing_id == target.drawing_id


def test_safety_stop_prevents_retry_after_first_pass(monkeypatch, tmp_path):
    times = iter((T_MINUS_6, T_MINUS_5))
    result = collect_fresh_open_external_odds(
        target=target,
        stop_at=T_MINUS_5,
        totobrief_client=sentinel_client,
        provider_factory=provider_factory,
        session_factory=session_factory,
        aliases={},
        cache_root=tmp_path,
        now=lambda: next(times),
        monotonic=monotonic,
        sleep=sleep_calls.append,
        max_passes=3,
        retry_delay_seconds=65.0,
    )
    assert result.stop_reason == "safety_stop"
    assert result.base_pass_count == 1
    assert provider_calls == [1]
    assert sleep_calls == []
```

Also prove a retry sleep is shortened to the remaining safe duration, expansion cannot start after the cutoff, `stop_at` must be UTC-aware, a cutoff reached before pass one raises a stable `ValueError`, and the existing no-target path still resolves exactly once.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_external_odds_prospective.py
```

Expected: failures for unknown `target`, `stop_at`, and `safety_stop` behavior.

- [ ] **Step 3: Implement target selection and stop checks**

Use this selection at the top of the function:

```python
started_at = now()
resolved_target = (
    resolve_open_target(totobrief_client, fetched_at=started_at)
    if target is None
    else target
)
_validate_stop_at(stop_at)
if stop_at is not None and started_at >= stop_at:
    raise ValueError("safety stop reached before first collection pass")
```

Check the injected wall clock before every subsequent base/expansion pass and immediately after each pass. Before retry sleep, sleep only for:

```python
remaining = (stop_at - now()).total_seconds()
if remaining <= 0:
    stop_reason = "safety_stop"
    break
sleep(min(retry_delay_seconds, remaining))
if now() >= stop_at:
    stop_reason = "safety_stop"
    break
```

Never discard an already completed immutable pass. Return its snapshot with `stop_reason="safety_stop"`.

- [ ] **Step 4: Verify GREEN and regression behavior**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_external_odds_prospective.py \
  tests/test_external_odds_cli.py \
  tests/test_external_odds_end_to_end.py
.venv/bin/python -m ruff check src/toto_ai/external_odds/prospective.py \
  tests/test_external_odds_prospective.py
```

Expected: all tests pass; standalone collection behavior is unchanged.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/external_odds/prospective.py \
  tests/test_external_odds_prospective.py
git commit -m "Bind prospective collection to runner deadline"
```

### Task 3: Provider-Neutral Runner Orchestration

**Files:**
- Create: `src/toto_ai/runner/orchestration.py`
- Create: `tests/test_runner_orchestration.py`
- Modify: `src/toto_ai/runner/__init__.py`

**Interfaces:**
- Consumes: Task 1 `DrawingRunnerConfig`, `PinnedDrawing`, timing functions.
- Consumes: Task 2 pinned collection callable.
- Produces: `DrawingRunnerResult` with target/timestamps, terminal decision/reason, optional collection/audit/EV run, and exact timing eligibility.
- Produces: `run_drawing(config, resolve_target, collect_target, resolve_timing, audit_coverage, build_package, now, monotonic, sleep, progress_callback=None) -> DrawingRunnerResult`.
- Callback types:
  - `resolve_target(datetime) -> PinnedDrawing`
  - `collect_target(TargetDrawing, datetime) -> ProspectiveCollectionResult`
  - `resolve_timing(PinnedDrawing) -> PlayTimingEligibility`
  - `audit_coverage() -> CoverageAudit`
  - `build_package(int) -> EVPackageRun`

- [ ] **Step 1: Write failing orchestration tests**

Cover the state machine with real immutable runner records and recording
callables. In the test module, define small local factories for complete real
`TargetDrawing`, `ProspectiveCollectionResult`, `CoverageAudit`,
`PlayTimingEligibility`, and `EVPackageRun` records. Define a sequence clock
that returns the final supplied timestamp after its sequence is exhausted, a
monotonic counter, and recording resolver/collector callables that append
their phase names before returning configured records. Do not mock
runner-owned models:

```python
def test_normal_playable_run_orders_every_phase():
    result = run_drawing(
        config=config,
        resolve_target=recording_resolver(preflight, final),
        collect_target=recording_collector(collection),
        resolve_timing=lambda _target: playable_timing,
        audit_coverage=lambda: audit,
        build_package=lambda drawing_id: playable_ev_run(drawing_id),
        now=fake_clock(T_MINUS_21, T_MINUS_20, T_MINUS_19, T_MINUS_18),
        monotonic=fake_monotonic(),
        sleep=fake_sleep,
        progress_callback=updates.append,
    )
    assert result.decision == "PLAY"
    assert calls == ["preflight", "final", "collect", "timing", "audit", "ev"]


def test_target_change_fails_closed_before_provider_access():
    result = run_drawing(
        config=config,
        resolve_target=recording_resolver(preflight, changed_final),
        collect_target=lambda *_args: pytest.fail("provider must not run"),
        resolve_timing=lambda _target: playable_timing,
        audit_coverage=lambda: audit,
        build_package=lambda drawing_id: playable_ev_run(drawing_id),
        now=fake_clock(T_MINUS_19),
        monotonic=fake_monotonic(),
        sleep=fake_sleep,
    )
    assert result.decision == "NO BET"
    assert result.terminal_reason == "final target does not match preflight"
```

Also test immediate final-window launch, already-closed launch, unknown/multi-day/absent playable timing skipping EV, research mode retaining `RESEARCH ONLY`, coverage `PENDING` not changing EV input or decision, safety cutoff before collection/audit/EV, cutoff after EV discarding the EV run and coupons, EV-produced `NO BET`, and progress phase order.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runner_orchestration.py
```

Expected: import failure because runner orchestration does not exist.

- [ ] **Step 3: Implement the minimal state machine**

Use one return helper for fail-closed outcomes and exact target comparison:

```python
def _same_target(left: PinnedDrawing, right: PinnedDrawing) -> bool:
    return (
        left.target.drawing_id == right.target.drawing_id
        and left.target.drawing_number == right.target.drawing_number
        and left.target.deadline == right.target.deadline
        and left.fingerprint == right.fingerprint
    )
```

The implementation order is preflight, wait, final resolve, collect, timing, audit, EV. Re-read `now()` at every safety boundary. In playable mode, timing other than exact `playable` returns `NO BET` without EV. After `build_package`, re-read time; if closed, return `NO BET` with `ev_run=None`, so no caller can publish late coupons. Research mode still obeys T-5 because this command is a deadline-adjacent runner.

`DrawingRunnerResult.__post_init__` must reject `PLAY` without an EV `PLAY`
package, `RESEARCH ONLY` without an EV research package, a `NO BET` whose
attached package still has nonzero cost or selected package coupons, mismatched
target identities, naive timestamps, or non-chronological phase timestamps.
An ordinary EV-threshold `NO BET` may retain its zero-cost `EVPackageRun` for
diagnostics, but reports must not serialize `top_coupons`. A package suppressed
because it completed at or after T-5 must use `ev_run=None`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_runner_timing.py tests/test_runner_orchestration.py
.venv/bin/python -m ruff check src/toto_ai/runner \
  tests/test_runner_timing.py tests/test_runner_orchestration.py
```

Expected: all tests pass and orchestration has no network/filesystem dependency.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/runner tests/test_runner_orchestration.py
git commit -m "Add safe drawing runner orchestration"
```

### Task 4: Deterministic Runner Reports

**Files:**
- Create: `src/toto_ai/runner/reports.py`
- Create: `tests/test_runner_reports.py`
- Modify: `src/toto_ai/runner/__init__.py`

**Interfaces:**
- Produces: `RunnerReportLinks(external: tuple[Path, ...], ev: tuple[Path, ...])`.
- Produces: `drawing_run_id(result) -> str` as a 12-character lowercase SHA-256 prefix.
- Produces: `drawing_run_report_paths(result, report_dir="reports") -> tuple[Path, Path]`.
- Produces: `write_drawing_run_reports(result, links=RunnerReportLinks(), report_dir="reports", input_paths=()) -> tuple[Path, Path]`.

- [ ] **Step 1: Write failing report tests**

Prove deterministic paths/bytes, distinct IDs for distinct preflight timestamps
or configs, canonical JSON, complete Markdown, path-collision rejection, no
secrets, no coupons for `NO BET`, permitted coupons only for
`PLAY`/`RESEARCH ONLY`, and rollback after `BaseException` during second final
replace. Define `_runner_result(decision, coupon="UNIQUE-COUPON")` in this test
module using complete real runner/EV records; for `NO BET`, keep the sentinel
only in diagnostic `top_coupons` while its package is empty and zero-cost.
Define `_interrupt_second_install(monkeypatch)` to wrap `os.replace`, count only
temporary-to-final installs, and raise `KeyboardInterrupt` on the second such
install:

```python
def test_no_bet_report_never_contains_discarded_coupon(tmp_path):
    result = _runner_result("NO BET")
    json_path, markdown_path = write_drawing_run_reports(result, report_dir=tmp_path)
    combined = json_path.read_text() + markdown_path.read_text()
    assert "UNIQUE-COUPON" not in combined
    assert '"decision":"NO BET"' in json_path.read_text()


def test_runner_report_pair_is_restored_on_interruption(monkeypatch, tmp_path):
    original = write_drawing_run_reports(
        _runner_result("PLAY", coupon="ORIGINAL-COUPON"), report_dir=tmp_path
    )
    original_bytes = tuple(path.read_bytes() for path in original)
    _interrupt_second_install(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        write_drawing_run_reports(
            _runner_result("PLAY", coupon="CHANGED-COUPON"), report_dir=tmp_path
        )
    assert tuple(path.read_bytes() for path in original) == original_bytes
    assert not tuple(tmp_path.glob(".*.tmp"))
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runner_reports.py
```

Expected: import failure because runner reports do not exist.

- [ ] **Step 3: Implement canonical rendering and atomic publication**

Build one explicit dictionary rather than `asdict(result)` so NumPy arrays and internal diagnostic coupons cannot leak. Canonical JSON uses:

```python
json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
```

Derive `run_id` from canonical target ID/number/deadline/fingerprint, preflight timestamp, bank/stake/mode/lead/safety/provider. Sanitize deadline for filenames and include the ID in both paths. Validate output paths against all input paths before writing. Use same-directory temporary files, backups, atomic replacement, restoration on every `BaseException`, and unconditional temporary cleanup.

- [ ] **Step 4: Verify GREEN and deterministic repeat**

Run twice:

```bash
.venv/bin/python -m pytest -q tests/test_runner_reports.py
.venv/bin/python -m pytest -q tests/test_runner_reports.py
.venv/bin/python -m ruff check src/toto_ai/runner/reports.py \
  tests/test_runner_reports.py
```

Expected: both runs pass and generated byte hashes are identical inside tests.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/runner tests/test_runner_reports.py
git commit -m "Add deterministic drawing runner reports"
```

### Task 5: Production Dependency Wiring and Typer Command

**Files:**
- Modify: `src/toto_ai/cli.py`
- Create: `tests/test_runner_cli.py`

**Interfaces:**
- Adds CLI: `python -m toto_ai.cli run-drawing --open --bank <RUB>`.
- Adds private CLI bridges that convert stored `DrawingEligibility` to existing `PlayTimingEligibility`, create the API-Sports provider factory, and publish associated audit/EV reports.
- Consumes: Tasks 1-4 public runner APIs.

- [ ] **Step 1: Write failing CLI validation and wiring tests**

Use `CliRunner`, monkeypatched services, and a sentinel secret. Prove:

```python
def test_run_drawing_requires_open_and_api_key(monkeypatch):
    missing_open = runner.invoke(app, ["run-drawing", "--bank", "4980"])
    assert missing_open.exit_code != 0
    assert "--open is required" in missing_open.output

    monkeypatch.delenv("API_SPORTS_KEY", raising=False)
    missing_key = runner.invoke(
        app, ["run-drawing", "--open", "--bank", "4980"]
    )
    assert missing_key.exit_code != 0
    assert "API_SPORTS_KEY is required" in missing_key.output
```

Also verify arbitrary valid banks, invalid divisibility, provider restriction, lead/safety validation, fresh-only provider factory, exact DB and report-dir wiring, latest-30 audit, Rich phase/countdown updates, `PLAY`, `NO BET`, `RESEARCH ONLY`, exit-zero valid `NO BET`, nonzero internal failure, `KeyboardInterrupt`, associated report paths, no top-coupon table after suppression, and recursive absence of the API key from output/exceptions.

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runner_cli.py
```

Expected: failure because `run-drawing` is not registered.

- [ ] **Step 3: Register and wire `run-drawing`**

The command must expose exactly these approved controls and reuse existing
defaults:

| Option | Required/default |
|---|---|
| `--open` | required flag; reject invocation without it |
| `--bank` | required positive integer divisible by stake |
| `--stake` | `30` |
| `--mode` | `playable` |
| `--final-lead-minutes` | `20`, minimum 1 |
| `--safety-stop-minutes` | `5`, minimum 1 |
| `--db` | `data/toto.db` |
| `--report-dir` | `reports` |
| `--provider` | `api-sports` |
| `--aliases` | `data/external-odds/team-aliases.json` |
| `--quota-reserve` | `10`, minimum 0 |
| `--max-passes` | `3`, minimum 1 |
| `--max-expansion-passes` | `3`, minimum 1 |
| `--retry-delay-seconds` | `65.0`, minimum 0 |
| `--cache-root` | `data/external-cache/api-sports` |

Do not expose `--reuse-cache`, EV threshold tuning, payout overrides, or bet submission. Construct `DrawingRunnerConfig` before provider access. Use `init_db` for collection writes and the existing exact read-only timing resolver for the final EV payload. Publish coverage reports only when an audit exists, EV reports only when `ev_run` exists, then publish the runner pair with those paths. Sanitize every caught provider error with `_external_error_message(error, secret=api_key)`.

- [ ] **Step 4: Verify GREEN and CLI help**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_runner_cli.py
.venv/bin/python -m toto_ai.cli run-drawing --help
.venv/bin/python -m ruff check src/toto_ai/cli.py tests/test_runner_cli.py
```

Expected: tests pass; help shows T-20/T-5 defaults and no cache-reuse or automatic-bet option.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/cli.py tests/test_runner_cli.py
git commit -m "Add safe run-drawing command"
```

### Task 6: End-to-End Acceptance and Project Memory

**Files:**
- Create: `tests/test_runner_end_to_end.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/DATA_NOTES.md`
- Modify: `memory-bank/DECISIONS.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `knowledge/totobrief.md`
- Modify: `docs/superpowers/plans/2026-07-16-safe-drawing-runner.md`

**Interfaces:**
- Proves the full preflight-to-report operator boundary with no real network, sleep, or bet submission.

- [ ] **Step 1: Write end-to-end acceptance**

Build deterministic fake-clock scenarios through real runner orchestration,
prospective collection, SQLite save/load, audit, timing lookup, EV boundary,
and runner reports. The test module must define
`_run_acceptance_scenario(tmp_path, launch_at)` from the real application
services with fake TotoBrief/provider clients, injected clock/sleeper, and a
provider-call recorder. Patch `socket.socket`, `socket.create_connection`,
`requests.Session.request`, and the installed `httpx` request entry points to
raise if reached, proving the scenario has no unconfigured network path:

```python
@pytest.mark.parametrize(
    ("launch_at", "expected_decision", "provider_calls"),
    (
        (T_MINUS_21, "PLAY", 1),
        (T_MINUS_19, "PLAY", 1),
        (T_MINUS_5, "NO BET", 0),
    ),
)
def test_safe_runner_operator_boundary(
    monkeypatch, tmp_path, launch_at, expected_decision, provider_calls
):
    _forbid_unconfigured_network(monkeypatch)
    result, report_paths, observed_provider_calls = _run_acceptance_scenario(
        tmp_path=tmp_path,
        launch_at=launch_at,
    )
    assert result.decision == expected_decision
    assert observed_provider_calls == provider_calls
    assert all(path.exists() for path in report_paths)
```

Add separate scenarios for target mutation, day-five expansion, multi-day, unresolved/partial schedule, provider odds fallback with playable TotoBrief timing, external gate `PENDING`, cutoff during retry, cutoff after EV, report rollback, interruption, arbitrary banks such as 4800/6000/9600, and a secret-bearing provider exception. Assert all 15 dispositions, exact fingerprint binding, zero-cost suppressed outputs, no automatic bet callable, deterministic report bytes, and secret absence from SQLite/cache/reports/output/recursive exceptions.

- [ ] **Step 2: Run acceptance to verify GREEN after all feature tasks**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_runner_timing.py \
  tests/test_runner_orchestration.py \
  tests/test_runner_reports.py \
  tests/test_runner_cli.py \
  tests/test_runner_end_to_end.py \
  tests/test_external_odds_prospective.py \
  tests/test_external_odds_end_to_end.py \
  tests/test_ev_drawing.py tests/test_ev_reports.py tests/test_ev_end_to_end.py
```

Expected: all focused tests pass without real network or real sleep.

- [ ] **Step 3: Update repository memory**

Record the implemented command, timing protocol, target identity, cutoff semantics, artifacts, associated report links, exact tests, and unchanged model definitions. Mark Phase 7 runner complete. Do not mark the 30-drawing/450-event prospective gate complete.

- [ ] **Step 4: Run full verification**

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m toto_ai.cli run-drawing --help
.venv/bin/python -m toto_ai.cli collect-external-odds --help
.venv/bin/python -m toto_ai.cli ev-package --help
git diff --check
```

Expected: full suite and Ruff pass; all three help commands exit zero.

- [ ] **Step 5: Independent final review**

Review the complete feature range against the approved design. Required checks: no model-definition change, no external probability entering EV, no post-T-5 coupon publication, no target roll-forward, no real test sleep/network, no secret surfaces, deterministic rollback-safe artifacts, and clean worktree after commit. Fix every critical/important finding and re-run Step 4.

- [ ] **Step 6: Commit**

```bash
git add src/toto_ai/runner src/toto_ai/external_odds/prospective.py \
  src/toto_ai/cli.py tests memory-bank knowledge \
  docs/superpowers/plans/2026-07-16-safe-drawing-runner.md
git commit -m "Complete safe drawing runner"
```
