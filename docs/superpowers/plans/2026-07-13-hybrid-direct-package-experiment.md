# Hybrid Direct Package Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and run a development-only experiment that keeps a fixed top-probability coupon core, fills the remaining budget by marginal weighted coverage, and returns a deterministic `GO` or `STOP` decision.

**Architecture:** Add a hybrid selector beside the existing weighted selector without changing either existing strategy. Add a separate evaluator that regenerates the frozen top package, verifies its hash before loading results, evaluates three fixed hybrid fractions over five chronological development folds, and writes deterministic reports through a read-only database CLI.

**Tech Stack:** Python 3.10+, Typer, Rich, SQLAlchemy/SQLite, pytest, Ruff.

## Global Constraints

- Use only the 350 development drawing IDs from the frozen manifest; never load the 150 old holdout drawings for this experiment.
- Frozen protocol is bank 5000 RUB, stake 30 RUB, category 13, and 166 coupons.
- Test only core fractions `0.50`, `0.75`, and `0.90`; they are constants, not CLI options.
- Core sizes use `ceil(max_coupons * fraction)`: 83, 125, and 150.
- Existing `top_probability` and `weighted_coverage` outputs must remain unchanged.
- Generate candidates, optimization scenarios, and validation scenarios once per drawing and reuse them for all fractions.
- Verify the regenerated top package hash before loading any actual result.
- Use five contiguous chronological folds of exactly 70 drawings and reject non-divisible development sets.
- `GO` requires at least two additional total 13+ hits over top, no worse fold-level 13+ in at least four folds, no lower average best hits, and zero failures.
- If no fraction passes, return `STOP`, select no fraction, and stop optimizer tuning.
- A `GO` is development evidence only; it is not profitability evidence and does not authorize reuse of the old holdout.
- Run pytest and Ruff before every commit and update project memory after each completed task.

---

## File Map

- Modify `src/toto_ai/optimizer/direct_package.py`: add the standalone hybrid package selector.
- Create `src/toto_ai/optimizer/hybrid_evaluation.py`: own fixed protocol constants, rows, folds, GO/STOP decision, runner, and reports.
- Modify `src/toto_ai/cli.py`: register `evaluate-hybrid` and its Rich summary tables.
- Create `tests/test_hybrid_package.py`: selector behavior, determinism, and legacy-regression tests.
- Create `tests/test_hybrid_evaluation.py`: folds, decisions, fail-closed runner, reports, and CLI tests.
- Modify `.gitignore`: ignore generated hybrid evaluation CSV and Markdown reports.
- Modify `memory-bank/ARCHITECTURE.md`, `memory-bank/CURRENT_STATE.md`, and `memory-bank/ROADMAP.md`: record implementation and final experiment result.

---

### Task 1: Add the Hybrid Package Selector

**Files:**
- Modify: `src/toto_ai/optimizer/direct_package.py`
- Create: `tests/test_hybrid_package.py`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `top_probability_coupons()`, `select_weighted_package()`, `estimate_package_coverage()`, `ProbabilityMatrix`.
- Produces: `select_hybrid_package(candidates, scenarios, probabilities, category, max_coupons, top_coupons, core_fraction, deadline=None, time_func=time.perf_counter) -> DirectPackageResult`.

- [ ] **Step 1: Write failing core-size and exact-prefix tests**

```python
from math import ceil

from toto_ai.optimizer.coupon_probabilities import normalize_probability_matrix
from toto_ai.optimizer.direct_package import select_hybrid_package


def test_hybrid_uses_exact_top_prefix_and_ceiling_core_size():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 4
    )
    top = ["1111", "111X", "11X1", "1X11"]
    result = select_hybrid_package(
        candidates=[*top, "XXXX", "2222"],
        scenarios={"1111": 10, "XXXX": 9, "2222": 8},
        probabilities=probabilities,
        category=15,
        max_coupons=4,
        top_coupons=top,
        core_fraction=0.50,
    )

    assert ceil(4 * 0.50) == 2
    assert result.selected_coupons[:2] == top[:2]
    assert len(result.selected_coupons) == 4


def test_production_core_sizes_are_fixed():
    assert [ceil(166 * value) for value in (0.50, 0.75, 0.90)] == [83, 125, 150]
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_hybrid_package.py -q`

Expected: collection fails because `select_hybrid_package` does not exist.

- [ ] **Step 3: Write failing marginal-coverage, uniqueness, and validation tests**

```python
import pytest


def test_hybrid_fill_ignores_scenarios_already_covered_by_core():
    probabilities = normalize_probability_matrix(
        [{"1": 60, "X": 30, "2": 10}] * 2
    )
    result = select_hybrid_package(
        candidates=["11", "1X", "XX", "22"],
        scenarios={"11": 100, "XX": 9, "22": 8},
        probabilities=probabilities,
        category=15,
        max_coupons=2,
        top_coupons=["11", "1X"],
        core_fraction=0.50,
    )

    assert result.selected_coupons == ["11", "XX"]
    assert result.covered_scenario_weight == 109
    assert result.estimated_coverage == pytest.approx(109 / 117)


def test_hybrid_is_unique_deterministic_and_does_not_mutate_inputs():
    candidates = ["11", "1X", "X1", "XX", "22"]
    scenarios = {"11": 4, "XX": 3, "22": 2}
    original_candidates = list(candidates)
    original_scenarios = dict(scenarios)
    kwargs = dict(
        candidates=candidates,
        scenarios=scenarios,
        probabilities=normalize_probability_matrix(
            [{"1": 50, "X": 30, "2": 20}] * 2
        ),
        category=15,
        max_coupons=4,
        top_coupons=["11", "1X", "X1", "XX"],
        core_fraction=0.50,
    )

    first = select_hybrid_package(**kwargs)
    second = select_hybrid_package(**kwargs)

    assert first == second
    assert len(first.selected_coupons) == len(set(first.selected_coupons)) == 4
    assert candidates == original_candidates
    assert scenarios == original_scenarios


@pytest.mark.parametrize("fraction", [0.0, -0.1, 1.1])
def test_hybrid_rejects_invalid_fraction(fraction):
    with pytest.raises(ValueError, match="core_fraction"):
        select_hybrid_package(
            candidates=["1"],
            scenarios={"1": 1},
            probabilities=normalize_probability_matrix([{"1": 1, "X": 1, "2": 1}]),
            category=15,
            max_coupons=1,
            top_coupons=["1"],
            core_fraction=fraction,
        )
```

- [ ] **Step 4: Implement the selector without modifying the weighted selector**

Add this public function and a private exact covered-weight helper to `direct_package.py`:

```python
def select_hybrid_package(
    candidates: list[str],
    scenarios: dict[str, int],
    probabilities: ProbabilityMatrix,
    category: int,
    max_coupons: int,
    top_coupons: list[str],
    core_fraction: float,
    deadline: float | None = None,
    time_func=time.perf_counter,
) -> DirectPackageResult:
    if not 0.0 < core_fraction <= 1.0:
        raise ValueError("core_fraction must be in (0, 1].")
    if len(top_coupons) < max_coupons:
        raise ValueError("top_coupons must contain max_coupons coupons.")
    if any(len(coupon) != len(probabilities) for coupon in top_coupons):
        raise ValueError("Top coupon and probability lengths must match.")
    if any(set(coupon) - set(OUTCOMES) for coupon in top_coupons):
        raise ValueError("Top coupon outcomes must be 1, X, or 2.")

    core_size = math.ceil(max_coupons * core_fraction)
    core = list(top_coupons[:core_size])
    if len(set(core)) != len(core):
        raise ValueError("Hybrid core coupons must be unique.")

    core_set = set(core)
    max_errors = category_max_errors(category)
    uncovered = {}
    for scenario, weight in scenarios.items():
        if deadline is not None and time_func() >= deadline:
            covered_weight = _covered_scenario_weight(core, scenarios, category)
            total_weight = sum(scenarios.values())
            return DirectPackageResult(
                core,
                covered_weight,
                total_weight,
                covered_weight / total_weight if total_weight else 0.0,
                True,
            )
        if not any(
            neighbor in core_set
            for neighbor in neighbors_within_distance(scenario, max_errors)
        ):
            uncovered[scenario] = weight
    fill = select_weighted_package(
        candidates=[coupon for coupon in candidates if coupon not in core_set],
        scenarios=uncovered,
        probabilities=probabilities,
        category=category,
        max_coupons=max_coupons - core_size,
        deadline=deadline,
        time_func=time_func,
    )
    selected = [*core, *fill.selected_coupons]
    if not fill.timed_out and len(selected) < max_coupons:
        selected_set = set(selected)
        remaining = sorted(
            (coupon for coupon in candidates if coupon not in selected_set),
            key=lambda coupon: (
                -coupon_log_probability(coupon, probabilities),
                coupon,
            ),
        )
        selected.extend(remaining[: max_coupons - len(selected)])
    covered_weight = _covered_scenario_weight(selected, scenarios, category)
    total_weight = sum(scenarios.values())
    return DirectPackageResult(
        selected_coupons=selected,
        covered_scenario_weight=covered_weight,
        total_scenario_weight=total_weight,
        estimated_coverage=(covered_weight / total_weight if total_weight else 0.0),
        timed_out=fill.timed_out,
    )


def _covered_scenario_weight(
    coupons: list[str], scenarios: dict[str, int], category: int
) -> int:
    coupon_set = set(coupons)
    max_errors = category_max_errors(category)
    return sum(
        weight
        for scenario, weight in scenarios.items()
        if any(
            neighbor in coupon_set
            for neighbor in neighbors_within_distance(scenario, max_errors)
        )
    )
```

Also add `import math`. Do not edit `select_weighted_package()`. Add a test where
the core covers every scenario and assert that the probability fallback still
returns exactly `max_coupons` unique coupons.

- [ ] **Step 5: Add legacy output regression tests**

Copy the existing weighted fixtures into `tests/test_hybrid_package.py` and assert the unchanged exact outputs:

```python
from toto_ai.optimizer.direct_package import select_weighted_package


def test_existing_weighted_selector_output_is_unchanged():
    probabilities = normalize_probability_matrix(
        [{"1": 50, "X": 30, "2": 20}] * 2
    )
    result = select_weighted_package(
        candidates=["22", "11", "XX"],
        scenarios={"11": 5, "12": 4, "22": 3, "XX": 4},
        probabilities=probabilities,
        category=14,
        max_coupons=2,
    )

    assert result.selected_coupons == ["11", "XX"]
    assert result.covered_scenario_weight == 13
```

- [ ] **Step 6: Run focused and full verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_direct_package.py tests/test_hybrid_package.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

Expected: all tests pass; Ruff prints `All checks passed!`.

- [ ] **Step 7: Update state and commit**

Add a concise completed-task entry to `memory-bank/CURRENT_STATE.md`, then run:

```bash
git add src/toto_ai/optimizer/direct_package.py tests/test_hybrid_package.py memory-bank/CURRENT_STATE.md
git commit -m "Add hybrid direct package selector"
```

---

### Task 2: Add Fold Metrics and the GO/STOP Decision Model

**Files:**
- Create: `src/toto_ai/optimizer/hybrid_evaluation.py`
- Create: `tests/test_hybrid_evaluation.py`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Produces constants `HYBRID_CORE_FRACTIONS = (0.50, 0.75, 0.90)` and `HYBRID_FOLD_COUNT = 5`.
- Produces dataclasses `HybridEvaluationRow`, `HybridDecision`, and `HybridEvaluationResult`.
- Produces `assign_chronological_folds(drawing_ids: list[int]) -> dict[int, int]`.
- Produces `summarize_hybrid_evaluation(rows: list[HybridEvaluationRow]) -> dict[str, object]`.
- Produces `decide_hybrid_experiment(summary: dict[str, object]) -> HybridDecision`.

- [ ] **Step 1: Write failing exact-fold tests**

```python
import pytest

from toto_ai.optimizer.hybrid_evaluation import assign_chronological_folds


def test_assigns_five_exact_contiguous_folds():
    drawing_ids = list(range(1, 351))
    folds = assign_chronological_folds(drawing_ids)

    assert [folds[value] for value in drawing_ids[:70]] == [1] * 70
    assert [folds[value] for value in drawing_ids[-70:]] == [5] * 70


def test_rejects_development_count_not_divisible_by_five():
    with pytest.raises(ValueError, match="five equal chronological folds"):
        assign_chronological_folds(list(range(349)))
```

- [ ] **Step 2: Define immutable rows and exact fold assignment**

Create `hybrid_evaluation.py` with these public structures:

```python
from dataclasses import dataclass

HYBRID_CORE_FRACTIONS = (0.50, 0.75, 0.90)
HYBRID_FOLD_COUNT = 5


@dataclass(frozen=True)
class HybridEvaluationRow:
    drawing_id: int
    drawing_number: int | None
    fold: int
    strategy: str
    core_fraction: float | None
    best_hits: int
    hit_13: bool
    hit_14: bool
    hit_15: bool
    package_size: int
    package_cost: int
    estimated_coverage: float
    candidate_count: int
    runtime_seconds: float
    timed_out: bool
    mean_log_probability: float
    mean_pairwise_hamming: float
    top_intersection_size: int
    top_jaccard: float


@dataclass(frozen=True)
class HybridDecision:
    status: str
    selected_core_fraction: float | None
    passing_core_fractions: tuple[float, ...]
    reason: str


@dataclass(frozen=True)
class HybridEvaluationResult:
    rows: list[HybridEvaluationRow]
    summary: dict[str, object]
    decision: HybridDecision
    manifest: dict[str, object]


def assign_chronological_folds(drawing_ids: list[int]) -> dict[int, int]:
    if len(drawing_ids) % HYBRID_FOLD_COUNT:
        raise ValueError("Development drawings must form five equal chronological folds.")
    fold_size = len(drawing_ids) // HYBRID_FOLD_COUNT
    if fold_size == 0:
        raise ValueError("Development drawings must form five equal chronological folds.")
    return {
        drawing_id: index // fold_size + 1
        for index, drawing_id in enumerate(drawing_ids)
    }
```

- [ ] **Step 3: Write failing GO/STOP and tie-break tests**

Use a local `make_rows(top_fold_hits, hybrid_fold_hits, ...)` fixture that creates 70 rows per fold and exact aggregate counts. Cover these cases:

```python
def test_go_requires_two_extra_hits_four_non_losing_folds_and_no_lower_average():
    summary = fixture_summary(
        top_total_13=6,
        candidates={
            0.50: candidate(total_13=8, non_losing_folds=4, average_best=9.0),
            0.75: candidate(total_13=7, non_losing_folds=5, average_best=10.0),
            0.90: candidate(total_13=9, non_losing_folds=3, average_best=10.0),
        },
        top_average_best=9.0,
        failure_count=0,
    )

    decision = decide_hybrid_experiment(summary)

    assert decision.status == "GO"
    assert decision.selected_core_fraction == 0.50


def test_stop_selects_no_fraction_when_no_candidate_passes():
    summary = fixture_summary(
        top_total_13=6,
        candidates={
            0.50: candidate(total_13=7, non_losing_folds=5, average_best=10.0),
            0.75: candidate(total_13=8, non_losing_folds=4, average_best=8.9),
            0.90: candidate(total_13=8, non_losing_folds=4, average_best=10.0),
        },
        top_average_best=9.0,
        failure_count=1,
    )

    decision = decide_hybrid_experiment(summary)

    assert decision.status == "STOP"
    assert decision.selected_core_fraction is None
```

Also add one table-driven test for the exact ranking order: total 13+, strictly winning folds, non-losing folds, average best hits, mean log probability, then larger fraction.

- [ ] **Step 4: Implement aggregation and decision logic**

`summarize_hybrid_evaluation()` must return this stable shape:

```python
{
    "drawing_count": 350,
    "failure_count": 0,
    "strategies": {
        "top_probability": {
            "total": {"hit_13": 6, "hit_14": 1, "hit_15": 0, "average_best_hits": 8.7},
            "folds": {1: {...}, 2: {...}, 3: {...}, 4: {...}, 5: {...}},
            "average_mean_log_probability": -13.6,
        },
        "hybrid_0.50": {...},
        "hybrid_0.75": {...},
        "hybrid_0.90": {...},
    },
}
```

Use `statistics.mean`. Calculate `strictly_winning_folds` and `non_losing_folds` by comparing each hybrid fold's `hit_13` count with top. Implement the approved pass predicate and deterministic ranking literally; do not add p-values or alternate thresholds.

- [ ] **Step 5: Verify and commit the pure decision model**

Run:

```bash
.venv/bin/python -m pytest tests/test_hybrid_evaluation.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

Update `memory-bank/ARCHITECTURE.md` with the new module and `memory-bank/CURRENT_STATE.md` with the completed decision model. Commit:

```bash
git add src/toto_ai/optimizer/hybrid_evaluation.py tests/test_hybrid_evaluation.py memory-bank/ARCHITECTURE.md memory-bank/CURRENT_STATE.md
git commit -m "Add hybrid experiment decision model"
```

---

### Task 3: Add the Fail-Closed Development Evaluator

**Files:**
- Modify: `src/toto_ai/optimizer/hybrid_evaluation.py`
- Modify: `tests/test_hybrid_evaluation.py`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Consumes: `development_drawing_ids()`, `load_frozen_development_rows()`, `_config_from_manifest()`, `_load_development_inputs()`, `_load_development_result()`, `_validate_frozen_result_fields()`, candidate/scenario generation, top enumeration, hybrid selector, and structural metrics.
- Produces: `run_hybrid_evaluation(session, manifest, frozen_csv_path, progress_callback=None) -> HybridEvaluationResult`.

- [ ] **Step 1: Write failing protocol-boundary tests**

Add fixtures equivalent to the existing diagnostics fixtures, but make the development count ten and holdout count two so five folds contain two drawings each. Test:

```python
def test_runner_never_loads_holdout_and_loads_results_after_top_hash(monkeypatch, session, manifest, frozen_csv):
    calls = []
    loaded_ids = []
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_inputs",
        lambda database_session, drawing_id: loaded_ids.append(drawing_id)
        or fixture_inputs(),
    )
    monkeypatch.setattr(
        hybrid_module,
        "_verify_top_package_hash",
        lambda *args: calls.append("hash"),
    )
    monkeypatch.setattr(
        hybrid_module,
        "_load_development_result",
        lambda *args: calls.append("result") or "1" * 15,
    )

    run_hybrid_evaluation(session, manifest, frozen_csv)

    assert loaded_ids == manifest["drawing_ids"][:10]
    assert calls.index("hash") < calls.index("result")
```

Add separate tests that reject:

- a top package hash mismatch before result loading;
- altered frozen top best-hit/13/14/15 fields;
- a malformed, duplicate, short, over-budget, incomplete, or timed-out hybrid package;
- any manifest configuration other than bank 5000, stake 30, category 13;
- duplicate manifest IDs and non-divisible development counts.

- [ ] **Step 2: Write failing generation-reuse tests**

Monkeypatch `generate_candidate_coupons`, optimization `sample_scenarios`, and validation `sample_scenarios` with counters. Assert each is called once per drawing, while `select_hybrid_package` receives the same candidate and optimization scenario object identities for all three fractions and isolated output lists.

```python
assert candidate_calls == development_count
assert optimization_calls == development_count
assert validation_calls == development_count
assert observed_fractions == [0.50, 0.75, 0.90] * development_count
```

- [ ] **Step 3: Implement per-drawing generation before result access**

Use the existing frozen seeds exactly:

```python
candidate_seed = config.seed ^ drawing_id ^ 0xC3C3
optimization_seed = config.seed ^ drawing_id ^ 0xA5A5
validation_seed = config.seed ^ drawing_id ^ 0x5A5A
```

For each development drawing:

1. Load probabilities and analyses without `Event.result`.
2. Generate the exact top package of `config.max_coupons`.
3. Generate candidates and both scenario sets once.
4. Call `select_hybrid_package()` for each fixed fraction with the same input objects.
5. Validate exact package size, uniqueness, coupon shape, cost, timeout, and strategy names.
6. Verify `sha256(",".join(top_coupons).encode("utf-8"))` against the frozen top row.
7. Load the actual result.
8. Recompute and verify frozen top result fields.
9. Score top and hybrid packages and append four rows.

The runner must call `assign_chronological_folds()` before database access and must never construct a loader call for holdout IDs.

- [ ] **Step 4: Implement exact row metrics and decision invocation**

For every package, use:

```python
hits = best_coupon_hits(package.coupons, result_string)
structure = package_structure_metrics(package.coupons, probabilities)
overlap = package_overlap_metrics(top_coupons, package.coupons, probabilities)
```

Top's overlap is intersection `166`, Jaccard `1.0`. Hybrid rows contain their actual intersection/Jaccard values. After all rows are built:

```python
summary = summarize_hybrid_evaluation(rows)
decision = decide_hybrid_experiment(summary)
return HybridEvaluationResult(rows, summary, decision, manifest)
```

- [ ] **Step 5: Run fail-closed evaluator verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_hybrid_package.py tests/test_hybrid_evaluation.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

Expected: all tests pass with no changes to existing strategy tests.

- [ ] **Step 6: Update state and commit**

Record the runner and its holdout boundary in `memory-bank/CURRENT_STATE.md`, then commit:

```bash
git add src/toto_ai/optimizer/hybrid_evaluation.py tests/test_hybrid_evaluation.py memory-bank/CURRENT_STATE.md
git commit -m "Add development hybrid evaluation runner"
```

---

### Task 4: Add Atomic Reports and the `evaluate-hybrid` CLI

**Files:**
- Modify: `src/toto_ai/optimizer/hybrid_evaluation.py`
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_hybrid_evaluation.py`
- Modify: `.gitignore`
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`

**Interfaces:**
- Produces `write_hybrid_evaluation_reports(result, report_dir) -> tuple[Path, Path]`.
- Produces CLI command `evaluate-hybrid --db --manifest --backtest-csv --report-dir`.

- [ ] **Step 1: Write failing deterministic and atomic report tests**

```python
def test_reports_are_deterministic_and_include_decision(tmp_path):
    result = fixture_evaluation_result(status="STOP")
    first = write_hybrid_evaluation_reports(result, tmp_path)
    first_csv = first[0].read_bytes()
    first_md = first[1].read_bytes()
    second = write_hybrid_evaluation_reports(result, tmp_path)

    assert second[0].read_bytes() == first_csv
    assert second[1].read_bytes() == first_md
    assert first[0].name == "hybrid_evaluation_development_last_500_bank_5000.csv"
    assert "Decision: STOP" in first[1].read_text(encoding="utf-8")
    assert "development-only" in first[1].read_text(encoding="utf-8")


def test_report_failure_leaves_no_temporary_files(monkeypatch, tmp_path):
    monkeypatch.setattr(
        hybrid_module,
        "_render_hybrid_markdown",
        lambda *args: (_ for _ in ()).throw(OSError("render failed")),
    )

    with pytest.raises(OSError, match="render failed"):
        write_hybrid_evaluation_reports(fixture_evaluation_result(), tmp_path)

    assert list(tmp_path.iterdir()) == []
```

- [ ] **Step 2: Implement deterministic rendering and atomic replacement**

Serialize rows in manifest drawing order, then strategy order `top_probability`, `hybrid_0.50`, `hybrid_0.75`, `hybrid_0.90`. Write CSV and Markdown into same-directory temporary files with `tempfile.NamedTemporaryFile(delete=False, dir=report_dir)`. Render and close both temporary files before calling `Path.replace()` for either final path. On any error, unlink remaining temporary files and re-raise.

Markdown must include:

- frozen configuration and development count;
- total strategy table;
- five fold tables;
- average log probability, Hamming distance, intersection, and Jaccard;
- failure counts;
- every GO predicate by fraction;
- final `GO`/`STOP`, selected fraction or `none`, and reason;
- explicit development-only/no-profitability disclaimer.

- [ ] **Step 3: Write failing CLI tests**

Use `CliRunner` and a real temporary SQLite file. Monkeypatch `run_hybrid_evaluation()` and assert:

```python
result = runner.invoke(
    app,
    [
        "evaluate-hybrid",
        "--db", str(db_path),
        "--manifest", str(manifest_path),
        "--backtest-csv", str(frozen_csv),
        "--report-dir", str(tmp_path / "reports"),
    ],
)

assert result.exit_code == 0
assert "Hybrid Development Evaluation" in result.output
assert "Decision" in result.output
assert "Reports written to" in result.output
```

Also monkeypatch `init_db` to fail if called, execute `SELECT 1` through the provided session, and verify an attempted write raises SQLite `OperationalError` containing `readonly`.

- [ ] **Step 4: Register the fixed CLI command**

Add imports and this command shape to `cli.py`:

```python
@app.command("evaluate-hybrid")
def evaluate_hybrid(
    manifest: str = typer.Option(..., help="Frozen strategy experiment manifest."),
    backtest_csv: str = typer.Option(
        ..., "--backtest-csv", help="Frozen strategy backtest CSV."
    ),
    db: str = typer.Option("data/toto.db", help="SQLite database path."),
    report_dir: str = typer.Option("reports", help="Report output directory."),
) -> None:
    """Evaluate fixed hybrid packages on frozen development drawings only."""
```

Follow `diagnose_strategies()` for `open_readonly_db()`, `get_session_factory()`, Rich progress, `typer.BadParameter`, and report printing. Do not expose bank, stake, category, fractions, folds, seed, or timeout as options.

- [ ] **Step 5: Ignore generated reports and verify help**

Append:

```gitignore
reports/hybrid_evaluation_development_last_*.csv
reports/hybrid_evaluation_development_last_*.md
```

Run:

```bash
.venv/bin/python -m toto_ai.cli evaluate-hybrid --help
.venv/bin/python -m pytest tests/test_hybrid_evaluation.py -q
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

Expected: help shows only the four file/path options; all tests and Ruff pass.

- [ ] **Step 6: Update architecture/state and commit**

Document `hybrid_evaluation` and `evaluate-hybrid` in `memory-bank/ARCHITECTURE.md`; update `memory-bank/CURRENT_STATE.md`. Commit:

```bash
git add src/toto_ai/optimizer/hybrid_evaluation.py src/toto_ai/cli.py tests/test_hybrid_evaluation.py .gitignore memory-bank/ARCHITECTURE.md memory-bank/CURRENT_STATE.md
git commit -m "Add hybrid development evaluation command"
```

---

### Task 5: Run the Frozen Development Experiment and Apply GO/STOP

**Files:**
- Generated, ignored: `reports/hybrid_evaluation_development_last_500_bank_5000.csv`
- Generated, ignored: `reports/hybrid_evaluation_development_last_500_bank_5000.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `memory-bank/DECISIONS.md` only if the experiment changes project direction.

**Interfaces:**
- Consumes the frozen manifest and frozen strategy CSV already named in the design.
- Produces the first and only development selection decision for fractions 0.50/0.75/0.90.

- [ ] **Step 1: Establish a clean verified checkout**

Run:

```bash
git status --short
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

Expected: clean status, all tests pass, Ruff prints `All checks passed!`. Do not run the experiment from a dirty checkout.

- [ ] **Step 2: Run the fixed command exactly once**

```bash
.venv/bin/python -m toto_ai.cli evaluate-hybrid \
  --db data/toto.db \
  --manifest reports/strategy_experiment_manifest_last_500_exclude_10.json \
  --backtest-csv reports/strategy_backtest_last_500_bank_5000.csv
```

Expected: 350 development drawings, five folds of 70, no failures, and a deterministic `GO` or `STOP`. If the command fails closed, fix the implementation under a new TDD commit and rerun only after full verification; never relax the protocol.

- [ ] **Step 3: Independently inspect the report invariants**

Run:

```bash
python -c 'import csv; from collections import Counter; p="reports/hybrid_evaluation_development_last_500_bank_5000.csv"; rows=list(csv.DictReader(open(p, encoding="utf-8"))); print(len(rows)); print(Counter(r["strategy"] for r in rows)); print(Counter(r["fold"] for r in rows))'
```

Expected:

```text
1400
Counter({'top_probability': 350, 'hybrid_0.50': 350, 'hybrid_0.75': 350, 'hybrid_0.90': 350})
Counter({'1': 280, '2': 280, '3': 280, '4': 280, '5': 280})
```

Read only the generated development report. Do not run or inspect any command/report filtered to the old holdout.

- [ ] **Step 4: Record the decision without reinterpretation**

Update `memory-bank/CURRENT_STATE.md` with exact per-strategy totals, per-fold 13+ counts, average best hits, failures, and final decision.

If `GO`:

- record the selected fraction as eligible only for a new prospective or newly reserved untouched window;
- keep the old holdout closed;
- set the next roadmap task to freeze that new evaluation window.

If `STOP`:

- record that direct optimizer tuning is closed under the approved criterion;
- set the next roadmap task to external probability providers, starting with Pinnacle availability/data licensing and a provider-neutral probability interface;
- add the direction change to `memory-bank/DECISIONS.md`.

- [ ] **Step 5: Final verification and result commit**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
git diff --check
```

Commit only repository memory changes; generated reports remain ignored:

```bash
git add memory-bank/CURRENT_STATE.md memory-bank/ROADMAP.md memory-bank/DECISIONS.md
git commit -m "Record hybrid development experiment result"
```

If `DECISIONS.md` did not change for a `GO`, omit it from `git add`.

---

## Final Acceptance Checklist

- [ ] Existing top and weighted selector regression tests pass unchanged.
- [ ] Hybrid core sizes are exactly 83, 125, and 150 at the frozen protocol.
- [ ] All hybrid packages contain 166 unique valid coupons and cost 4980 RUB.
- [ ] Candidate and scenario generation occurs once per drawing.
- [ ] The old holdout never reaches input or result loaders.
- [ ] Top package hash validation occurs before actual result loading.
- [ ] Exactly 350 development drawings and five folds of 70 are reported.
- [ ] Reports are deterministic and written atomically.
- [ ] GO/STOP follows only the approved predicates and deterministic tie-break.
- [ ] Full pytest and Ruff checks pass.
- [ ] Project memory records the exact outcome and next direction without claiming profitability.
