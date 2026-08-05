# Fresh Prospective Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `collect-external-odds` obtain a fresh, pinned, multi-pass prospective snapshot under API-Sports' ten-request minute limit.

**Architecture:** Split one-drawing target resolution from provider collection, then add a small provider-neutral orchestrator that reuses one fresh cache session across new provider clients. The CLI defaults to this fresh path and retains an explicit shared-cache diagnostic mode.

**Tech Stack:** Python 3.12, Typer, SQLAlchemy, pytest, Ruff, existing TotoBrief/API-Sports clients.

## Global Constraints

- External probabilities remain audit-only and cannot affect `PLAY`.
- Existing category, bank, probability, consensus, gate, and daily quota-reserve definitions do not change.
- Every pass is a complete immutable 15-disposition snapshot.
- The open TotoBrief drawing and target payload are resolved exactly once per invocation.
- Fresh mode defaults to three passes and a 65-second retry delay.
- Retry only quota, provider schedule, and provider odds failures.
- No API key may enter persistence, cache payloads, reports, or exception text.

---

## File Structure

- Create `src/toto_ai/external_odds/prospective.py`: fresh cache-session naming, retry classification, pass orchestration, and aggregate result.
- Create `tests/test_external_odds_prospective.py`: deterministic orchestrator tests with injected provider factory, clock, monotonic timer, and sleeper.
- Modify `src/toto_ai/external_odds/collection.py`: expose pinned-target resolution and collection helpers while preserving the existing wrapper.
- Modify `tests/test_external_odds_collection.py`: prove resolution occurs once and direct target collection persists one pass.
- Modify `src/toto_ai/cli.py`: add fresh/reuse options and orchestration summary.
- Modify `tests/test_external_odds_end_to_end.py`: exercise fresh CLI wiring and secret sanitization without real waits.
- Modify `memory-bank/ARCHITECTURE.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `ROADMAP.md`, and `DATA_NOTES.md`: record the completed protocol and live evidence.

### Task 1: Pin One TotoBrief Target

**Files:**
- Modify: `src/toto_ai/external_odds/collection.py`
- Test: `tests/test_external_odds_collection.py`

**Interfaces:**
- Produces: `resolve_open_target(totobrief_client, fetched_at) -> TargetDrawing`
- Produces: `collect_target_external_odds(target, provider, session_factory, aliases) -> ExternalCollectionSnapshot`
- Preserves: `collect_open_external_odds(...) -> ExternalCollectionSnapshot`

- [x] **Step 1: Write failing tests**

Add tests proving `resolve_open_target` calls open resolution and drawing-info once, rejects an ID mismatch, and `collect_target_external_odds` stores the supplied target without another TotoBrief call.

- [x] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_external_odds_collection.py -k "resolve_open_target or collect_target"
```

Expected: collection module has no exported helper names.

- [x] **Step 3: Implement the minimal split**

Refactor the current wrapper into:

```python
def resolve_open_target(client: Any, fetched_at: datetime) -> TargetDrawing:
    reference = resolve_open_drawing_from_api(client)
    payload = client.drawing_info(reference.drawing_id)
    target = parse_target_drawing(payload, fetched_at=fetched_at)
    if target.drawing_id != reference.drawing_id:
        raise ValueError("drawing-info id does not match resolved drawing")
    return target


def collect_target_external_odds(target, provider, session_factory, aliases):
    result = build_external_collection(target, provider, aliases)
    if len(result.events) != 15:
        raise ValueError("external collection must contain exactly 15 dispositions")
    save_collection(session_factory, result)
    return result
```

Keep `collect_open_external_odds` as a compatibility wrapper calling both.

- [x] **Step 4: Verify GREEN**

Run the focused collection tests and confirm they pass.

### Task 2: Fresh Multi-Pass Orchestrator

**Files:**
- Create: `src/toto_ai/external_odds/prospective.py`
- Create: `tests/test_external_odds_prospective.py`

**Interfaces:**
- Produces: `ProspectiveCollectionPass(snapshot, elapsed_seconds)`
- Produces: `ProspectiveCollectionResult(snapshot, passes, cache_dir, elapsed_seconds, stop_reason, total_requests, total_cache_hits)`
- Produces: `collect_fresh_open_external_odds(...) -> ProspectiveCollectionResult`

- [x] **Step 1: Write retry-classification tests**

Test exact retry behavior for:

```python
"quota reserve reached"
"provider schedule failure: transport"
"provider odds failure: transport"
```

and non-retry behavior for missing, ambiguous, stale, semantic, and insufficient-bookmaker fallbacks.

- [x] **Step 2: Verify classification RED**

Run the new test file and confirm import failure.

- [x] **Step 3: Implement immutable result types and classifier**

Use frozen dataclasses and prefix-based classification limited to the three approved operational reasons.

- [x] **Step 4: Verify classification GREEN**

Run the classification tests and confirm pass.

- [x] **Step 5: Write orchestration tests**

Use injected fakes to prove:

- target resolution happens once;
- provider factory receives one identical cache path for every pass;
- first retryable snapshot sleeps once and a second clean snapshot stops;
- total requests/cache hits and elapsed time aggregate across passes;
- non-retryable fallback stops after one pass;
- retryable fallback on the last allowed pass returns `max_passes`;
- every pass is saved through `collect_target_external_odds`;
- fresh cache-session names differ for distinct invocation timestamps.

- [x] **Step 6: Verify orchestration RED**

Run:

```bash
.venv/bin/python -m pytest -q tests/test_external_odds_prospective.py
```

Expected: orchestration entry point is missing.

- [x] **Step 7: Implement orchestration**

Resolve one target, create a path shaped like
`<cache-root>/runs/<drawing>-<UTC timestamp>`, instantiate a new provider for
each pass with that same path, persist every pass, sleep only before an approved
retry, and return the last pass plus aggregate counters.

- [x] **Step 8: Verify orchestration GREEN**

Run the new test file and collection tests; confirm all pass without real sleep.

### Task 3: CLI Fresh Mode

**Files:**
- Modify: `src/toto_ai/cli.py`
- Modify: `tests/test_external_odds_end_to_end.py`

**Interfaces:**
- Adds: `--fresh/--reuse-cache`, `--max-passes`, `--retry-delay-seconds`, `--cache-root`
- Fresh default calls `collect_fresh_open_external_odds`.
- Reuse mode calls existing `collect_open_external_odds` once with `cache_root`.

- [x] **Step 1: Write failing CLI tests**

Assert help exposes all four options, fresh mode forwards validated values and
prints orchestration totals, reuse mode performs one pass, invalid values fail
before provider access, and API keys remain absent from output and recursive
exceptions.

- [x] **Step 2: Verify CLI RED**

Run the selected end-to-end CLI tests and confirm missing options/summary.

- [x] **Step 3: Implement CLI wiring**

Use Typer validation:

```python
fresh: bool = typer.Option(True, "--fresh/--reuse-cache")
max_passes: int = typer.Option(3, min=1)
retry_delay_seconds: float = typer.Option(65.0, min=0.0)
cache_root: str = typer.Option("data/external-cache/api-sports")
```

Keep existing sanitized exception handling. Extend the output table only when
an orchestration result is available.

- [x] **Step 4: Verify CLI GREEN**

Run focused CLI/end-to-end tests and `collect-external-odds --help`.

### Task 4: Documentation and Full Verification

**Files:**
- Modify: `memory-bank/ARCHITECTURE.md`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/DECISIONS.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `memory-bank/DATA_NOTES.md`

**Interfaces:**
- Documents the exact T-15 operator protocol and unchanged audit-only boundary.

- [x] **Step 1: Update project memory**

Record fresh-by-default cache sessions, pinned target, approved retry reasons,
three-pass/65-second defaults, the 71-second live dry run, and that scheduling
itself remains a later production task.

- [x] **Step 2: Run focused verification**

```bash
.venv/bin/python -m pytest -q tests/test_external_odds_collection.py tests/test_external_odds_prospective.py tests/test_external_odds_end_to_end.py
```

- [x] **Step 3: Run full verification**

```bash
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q
git diff --check
```

- [x] **Step 4: Run one fresh live collection when the drawing remains open**

Use the keychain-provided API key, default fresh mode, and normal database. Do
not print the key. Confirm two-pass completion or retain explicit fallback
evidence if the provider fails.

- [x] **Step 5: Commit**

```bash
git add src/toto_ai/external_odds/collection.py \
  src/toto_ai/external_odds/prospective.py src/toto_ai/cli.py \
  tests/test_external_odds_collection.py tests/test_external_odds_prospective.py \
  tests/test_external_odds_end_to_end.py memory-bank
git commit -m "Add fresh prospective odds collection"
```
