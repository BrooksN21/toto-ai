# Operator Export and Timing Escalation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed operator export gateway, recoverable missing-time morning escalation, and frozen 4973 regression evidence.

**Architecture:** The scheduler remains the sole package authority. A small export boundary validates the scheduler plan, operator result, LKG chain, deadline, and exact bytes before an atomic copy. Morning dispatch represents missing schedule time as explicit unresolved evidence without conflating it with identity mapping.

**Tech Stack:** Python 3.12, Typer, dataclasses, SQLite/SQLAlchemy, pytest, Ruff.

## Global Constraints

- No automatic BaltBet submission.
- No package synthesis from research or expired artifacts.
- No probability, category, cover, stake, or bank definition changes.
- No weakening of quality-v2 paper-only or existing safety gates.
- Work only inside this repository and do not use external agents.

---

### Task 1: Fail-closed operator export

**Files:**
- Modify: `src/toto_ai/runner/scheduler.py`
- Modify: `src/toto_ai/cli.py`
- Test: `tests/test_scheduler_operator_export.py`

**Interfaces:**
- Produces: `export_operator_package(plan, destination, observed_at) -> Path`
- Produces: `operator-export --plan ... --output ...`

- [ ] Write tests proving `NO BET`, research files, expired results, identity/hash drift, and paths outside canonical LKG are rejected without writing output.
- [ ] Run the focused tests and confirm RED for the missing interface.
- [ ] Implement strict validation by reusing `_load_last_known_good`, then write validated bytes atomically.
- [ ] Add the CLI command and confirm focused tests pass.

### Task 2: Missing-time preflight escalation

**Files:**
- Modify: `src/toto_ai/runner/morning_dispatch.py`
- Modify: `src/toto_ai/cli.py`
- Test: `tests/test_preflight_escalation_v1.py`
- Test: `tests/test_morning_dispatch.py`

**Interfaces:**
- `MorningUnresolvedEvent(resolution_status="timing_unknown")`
- Ready mapping may carry only timing unresolved items while eligibility is unknown.

- [ ] Write a failing test for `READY 15/15`, baseline-only orders, unknown timing, attention/retry/review queue creation, and no evening plan.
- [ ] Write a failing test that a later playable retry resolves attention and may activate the exact evening scheduler.
- [ ] Implement timing unresolved construction and strict dataclass invariants.
- [ ] Update escalation resolution, evidence type, retry activation, and reporting.
- [ ] Run focused tests and confirm GREEN.

### Task 3: Frozen 4973 regression and project memory

**Files:**
- Create: `research/drawing_4973_unbound_package_postmortem.md`
- Create: `tests/fixtures/postmortem/drawing_4973_unbound_package.json`
- Test: `tests/test_package_postmortem_regressions.py`
- Modify: `memory-bank/CURRENT_STATE.md`
- Modify: `memory-bank/DECISIONS.md`
- Modify: `memory-bank/ROADMAP.md`
- Modify: `README.md`

**Interfaces:**
- Frozen fixture stores only package hash, actual result, distribution, cost,
  and provenance classification; no operator coupon export.

- [ ] Write a failing regression test for package hash, best 7/15, zero 10+ and zero 13+.
- [ ] Add the frozen evidence and make the test pass.
- [ ] Document the operator-export command and timing escalation behavior.
- [ ] Update project memory with the defect, fix, and remaining quality status.

### Task 4: Verification

- [ ] Run focused scheduler, morning, and postmortem tests.
- [ ] Run `.venv/bin/python -m pytest -q`.
- [ ] Run `.venv/bin/python -m ruff check .`.
- [ ] Run `git diff --check` and inspect the final diff.
- [ ] Commit the verified implementation; do not push without explicit approval.

