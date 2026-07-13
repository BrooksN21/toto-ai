# Development Strategy Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed `diagnose-strategies` command that explains the frozen development result without reading holdout data or changing package generation.

**Architecture:** A new `strategy_diagnostics` module loads only development identifiers and frozen rows, regenerates and hash-verifies the original packages, then loads development results and computes structural and paired metrics. The CLI renders progress and exports deterministic CSV/Markdown reports; production strategy code remains unchanged.

**Tech Stack:** Python 3.10, SQLAlchemy, Typer, Rich, pytest, Ruff, standard-library CSV/statistics/hashlib.

## Global Constraints

- Use only the first `last - holdout_size` IDs from the frozen manifest.
- Do not query holdout drawings, events, quotes, or results.
- Do not add or tune a strategy.
- Regenerated package hashes must match the frozen CSV before results are loaded.
- Recomputed best-hit and 13/14/15 fields must match frozen rows.
- Fail without a final report on missing, duplicate, invalid, timed-out, or mismatched data.
- Keep bank, stake, category, seed, and strategy settings fixed by the manifest.

---

### Task 1: Frozen Development Boundary

**Files:**
- Create: `src/toto_ai/optimizer/strategy_diagnostics.py`
- Create: `tests/test_strategy_diagnostics.py`

**Interfaces:**
- Consumes: manifest dictionaries returned by `load_strategy_experiment_manifest()` and frozen `StrategyBacktestRow` CSV fields.
- Produces: `development_drawing_ids(manifest) -> list[int]` and `load_frozen_development_rows(path, manifest) -> dict[tuple[int, str], StrategyBacktestRow]`.

- [ ] **Step 1: Write failing boundary and CSV-validation tests**

```python
def test_development_ids_exclude_holdout():
    manifest = {"last": 5, "holdout_size": 2, "drawing_ids": [1, 2, 3, 4, 5]}
    assert development_drawing_ids(manifest) == [1, 2, 3]

def test_frozen_rows_require_one_row_per_development_strategy(tmp_path):
    path = write_frozen_rows(tmp_path, drawing_ids=[1], omit="weighted_coverage")
    with pytest.raises(ValueError, match="exactly one frozen row"):
        load_frozen_development_rows(
            path,
            {"last": 2, "holdout_size": 1, "drawing_ids": [1, 2]},
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: FAIL because `strategy_diagnostics` does not exist.

- [ ] **Step 3: Implement manifest slicing and strict frozen-row parsing**

```python
STRATEGIES = ("baseline_brief", "top_probability", "weighted_coverage")

def development_drawing_ids(manifest: dict[str, object]) -> list[int]:
    last = int(manifest["last"])
    holdout = int(manifest["holdout_size"])
    drawing_ids = list(manifest["drawing_ids"])
    if len(drawing_ids) != last or holdout < 0 or holdout > last:
        raise ValueError("Invalid frozen development split.")
    return drawing_ids[: last - holdout]

def load_frozen_development_rows(path, manifest):
    development = set(development_drawing_ids(manifest))
    rows = {}
    with Path(path).open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            drawing_id = int(raw["drawing_id"])
            if drawing_id not in development:
                continue
            row = _parse_strategy_backtest_row(raw)
            key = (drawing_id, row.strategy)
            if key in rows:
                raise ValueError("Expected exactly one frozen row per strategy.")
            rows[key] = row
    expected = {(drawing_id, strategy) for drawing_id in development for strategy in STRATEGIES}
    if set(rows) != expected:
        raise ValueError("Expected exactly one frozen row per strategy.")
    return rows
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/optimizer/strategy_diagnostics.py tests/test_strategy_diagnostics.py
git commit -m "Add frozen development diagnostics boundary"
```

### Task 2: Package Structure Metrics

**Files:**
- Modify: `src/toto_ai/optimizer/strategy_diagnostics.py`
- Modify: `tests/test_strategy_diagnostics.py`

**Interfaces:**
- Consumes: `list[str]` coupons and `ProbabilityMatrix`.
- Produces: `PackageStructureMetrics`, `PackageOverlapMetrics`, `package_structure_metrics()`, and `package_overlap_metrics()`.

- [ ] **Step 1: Write failing deterministic metric tests**

```python
def test_package_structure_metrics_measure_probability_and_diversity():
    probabilities = normalize_probability_matrix([{"1": 60, "X": 30, "2": 10}] * 2)
    metrics = package_structure_metrics(["11", "1X", "X1"], probabilities)
    assert metrics.mean_pairwise_hamming == pytest.approx(4 / 3)
    assert metrics.max_log_probability == coupon_log_probability("11", probabilities)
    assert metrics.min_log_probability == coupon_log_probability("X1", probabilities)

def test_overlap_metrics_report_unique_coupon_probability():
    metrics = package_overlap_metrics(["11", "1X"], ["11", "X1"], probabilities)
    assert metrics.intersection_size == 1
    assert metrics.jaccard == pytest.approx(1 / 3)
    assert metrics.top_unique_mean_log_probability is not None
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: FAIL because metric helpers are undefined.

- [ ] **Step 3: Implement metrics with exact deterministic ordering**

```python
@dataclass(frozen=True)
class PackageStructureMetrics:
    min_log_probability: float
    median_log_probability: float
    mean_log_probability: float
    max_log_probability: float
    mean_pairwise_hamming: float

def _hamming(left: str, right: str) -> int:
    return sum(a != b for a, b in zip(left, right, strict=True))

def package_structure_metrics(coupons, probabilities):
    logs = sorted(coupon_log_probability(coupon, probabilities) for coupon in coupons)
    distances = [
        _hamming(left, right)
        for index, left in enumerate(coupons)
        for right in coupons[index + 1 :]
    ]
    return PackageStructureMetrics(
        min(logs), median(logs), mean(logs), max(logs),
        mean(distances) if distances else 0.0,
    )
```

Implement overlap with set intersection/union and return `None` for an empty unique set.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/optimizer/strategy_diagnostics.py tests/test_strategy_diagnostics.py
git commit -m "Add strategy package diagnostic metrics"
```

### Task 3: Fail-Closed Development Runner

**Files:**
- Modify: `src/toto_ai/optimizer/strategy_diagnostics.py`
- Modify: `tests/test_strategy_diagnostics.py`

**Interfaces:**
- Consumes: SQLAlchemy `Session`, manifest, frozen CSV path, and existing `build_packages_for_probabilities()`.
- Produces: `StrategyDiagnosticsRow`, `StrategyDiagnosticsResult`, and `run_strategy_diagnostics()`.

- [ ] **Step 1: Write failing ordering, holdout-isolation, and hash tests**

```python
def test_runner_builds_and_verifies_packages_before_loading_result(monkeypatch):
    calls = []
    monkeypatch.setattr(module, "_build_development_packages", lambda *a, **k: calls.append("packages") or packages)
    monkeypatch.setattr(module, "_load_development_result", lambda *a, **k: calls.append("result") or "1" * 15)
    run_strategy_diagnostics(session, manifest, frozen_csv)
    assert calls.index("packages") < calls.index("result")

def test_runner_fails_on_package_hash_mismatch(session, manifest, frozen_csv):
    with pytest.raises(ValueError, match="package hash"):
        run_strategy_diagnostics(session, manifest, frozen_csv, package_builder=mismatching_builder)

def test_runner_never_loads_holdout_id(monkeypatch):
    loaded = []
    monkeypatch.setattr(module, "_load_development_inputs", lambda session, drawing_id: loaded.append(drawing_id) or fixture_inputs())
    run_strategy_diagnostics(session, manifest_with_holdout_3, frozen_csv)
    assert loaded == [1, 2]
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: FAIL because the runner is undefined.

- [ ] **Step 3: Implement input-only SQL loading and package verification**

Use SQLAlchemy `load_only()` for input events so `Event.result` is deferred:

```python
events = list(session.scalars(
    select(Event)
    .options(load_only(Event.id, Event.drawing_id, Event.event_order, Event.name, Event.championship, Event.sport))
    .where(Event.drawing_id == drawing_id)
    .order_by(Event.event_order)
))
```

For each development ID:

```python
packages = package_builder(probabilities, analyses, drawing_id, config)
_validate_package_set(packages, max_coupons=config.max_coupons)
for package in packages:
    frozen = frozen_rows[(drawing_id, package.strategy)]
    actual_hash = sha256(",".join(package.coupons).encode()).hexdigest()
    if actual_hash != frozen.package_hash:
        raise ValueError(f"Development package hash mismatch for {drawing_id}.")
result_string = _load_development_result(session, drawing_id)
```

Recompute best hits and hit flags, require equality with the frozen row, then
build one paired `StrategyDiagnosticsRow` containing all strategy-prefixed and
top-versus-weighted metrics.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/optimizer/strategy_diagnostics.py tests/test_strategy_diagnostics.py
git commit -m "Add development strategy diagnostics runner"
```

### Task 4: Aggregate Summary and Reports

**Files:**
- Modify: `src/toto_ai/optimizer/strategy_diagnostics.py`
- Modify: `tests/test_strategy_diagnostics.py`

**Interfaces:**
- Consumes: `list[StrategyDiagnosticsRow]`.
- Produces: `summarize_strategy_diagnostics()` and `write_strategy_diagnostics_reports()`.

- [ ] **Step 1: Write failing summary and report tests**

```python
def test_summary_reports_paired_threshold_transitions():
    rows = [fixture_row(top_hits=13, weighted_hits=12), fixture_row(top_hits=12, weighted_hits=13)]
    summary = summarize_strategy_diagnostics(rows)
    assert summary["paired_13_transitions"] == {
        "neither": 0, "both": 0, "top_only": 1, "weighted_only": 1,
    }
    assert summary["weighted_vs_top"] == {"wins": 1, "ties": 0, "losses": 1}

def test_report_contains_all_hit_bins_and_is_deterministic(tmp_path):
    first = write_strategy_diagnostics_reports(result, tmp_path)
    first_text = first[1].read_text()
    second = write_strategy_diagnostics_reports(result, tmp_path)
    assert second[1].read_text() == first_text
    assert all(f"| {hits} |" in first_text for hits in range(16))
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: FAIL because summary/report functions are undefined.

- [ ] **Step 3: Implement aggregation and deterministic exports**

Use p25/p50/p75 nearest-rank quantiles for paired best-hit differences. Build
coverage bins with boundaries `0.000, 0.005, ..., 0.050, infinity`. Each bin
records strategy, count, mean frozen estimated coverage, and observed hit13
frequency. Write CSV fields from `StrategyDiagnosticsRow.__dataclass_fields__`
and a Markdown report with distributions, paired transitions, structural
averages, calibration, and an explicit `development-only; no winner selected`
statement.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/toto_ai/optimizer/strategy_diagnostics.py tests/test_strategy_diagnostics.py
git commit -m "Add development strategy diagnostic reports"
```

### Task 5: CLI, Historical Run, and Project Memory

**Files:**
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_strategy_diagnostics.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `memory-bank/DECISIONS.md` only if a durable definition changes
- Modify: `knowledge/direct_package_optimizer.md`

**Interfaces:**
- Consumes: `run_strategy_diagnostics()` and `write_strategy_diagnostics_reports()`.
- Produces: `python -m toto_ai.cli diagnose-strategies`.

- [ ] **Step 1: Write failing CLI tests**

```python
def test_diagnose_strategies_help():
    result = CliRunner().invoke(app, ["diagnose-strategies", "--help"])
    assert result.exit_code == 0
    assert "--manifest" in result.output
    assert "--backtest-csv" in result.output

def test_diagnose_strategies_rejects_invalid_frozen_data(tmp_path):
    result = CliRunner().invoke(app, ["diagnose-strategies", "--manifest", str(bad_manifest), "--backtest-csv", str(bad_csv)])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q`
Expected: FAIL because the command is not registered.

- [ ] **Step 3: Register command and progress output**

Add Typer options `--db`, required `--manifest`, required `--backtest-csv`, and
`--report-dir`. Load `StrategyConfig` only from the manifest, run the diagnostic
with Rich progress showing development drawing index/total, print paired counts
and transition counts, then print report paths. Convert `OSError`, `KeyError`,
`TypeError`, and `ValueError` into `typer.BadParameter`.

- [ ] **Step 4: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_strategy_diagnostics.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Expected: all tests pass, Ruff passes, and no whitespace errors.

- [ ] **Step 5: Commit CLI implementation**

```bash
git add src/toto_ai/cli.py tests/test_strategy_diagnostics.py
git commit -m "Add development strategy diagnostics command"
```

- [ ] **Step 6: Run the frozen development diagnostic**

Run:

```bash
python -m toto_ai.cli diagnose-strategies \
  --db data/toto.db \
  --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json \
  --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv
```

Expected: 350 development drawings, zero holdout drawings loaded, all package
hashes verified, and deterministic CSV/Markdown report paths printed.

- [ ] **Step 7: Record only observed findings and verify again**

Update project memory with command/module names, exact development metrics,
hash-verification status, and the explicit statement that no strategy was
selected. Run full pytest, Ruff, and `git diff --check` again.

- [ ] **Step 8: Commit project state**

```bash
git add memory-bank knowledge/direct_package_optimizer.md
git commit -m "Record development strategy diagnostics"
```
