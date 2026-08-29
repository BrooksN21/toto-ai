# TOTO-MORNING-TRAINING-20260820 — factual context

Evidence cutoff: 2026-08-20 19:50 MSK. This is context collection only; no implementation files were changed and no tests were run.

## Current drawing

- The database contains open BaltBet drawing **4982** (`id=12054`) with deadline `2026-08-21T16:00:00Z` / **19:00 MSK**.
- A READY/PLAYABLE 15/15 morning-dispatch record exists at `data/scheduler/morning-dispatch/drawing-12054-20260821T160000Z-581cdbbee88e7552.json`. It was recorded at `2026-08-20T16:21:30Z` / **19:21:30 MSK** and activated plan `453829753fa55b5f`.

## 1. Why automatic morning discovery did not run for 4982

- The installed LaunchAgent `com.totoai.morning-dispatcher.v1` is loaded. `launchctl` reports `runs=38`, `last exit code=0`, and `state=not running` between calendar triggers.
- Its repository-generated plist, `reports/rehearsal/morning-dispatcher-v2/totoai-morning-preanalysis.plist`, has only these daily MSK triggers: **08:00, 10:30, 12:00, 17:05, 17:12, 17:20**.
- The previous drawing 4981 closed at **18:00 MSK**. At the final automatic trigger, 17:20, 4981 was therefore still the current playable drawing. The next drawing could only be discovered after the recurring schedule had ended.
- The morning stdout log stopped at `2026-08-20T17:21:06+0300`; its final records all reference drawing 4981 and plan `5caf88df9bdfe566`. It contains no automatic 4982 record.
- The 4982 record was created at 19:21:30 MSK, which is not one of the installed calendar times. Therefore it came from a later direct/immediate dispatch path, not the automatic morning LaunchAgent.
- Factual gap: the generic discovery agent uses fixed wall-clock times and has no recurring post-close polling mechanism that follows variable prior-drawing deadlines. The drawing-bound preflight retry scheduler cannot discover a new drawing; it retries an already identified drawing.
- Existing schedule tests assert caller-supplied static times and passive behavior. No inspected test models a new drawing becoming available after the day's final generic discovery trigger.

## 2. Scheduler-owned non-actionable training package

**No scheduler-owned training/paper package currently exists for drawing 4982.**

- Exact scheduler directory: `reports/rehearsal/evening-4982-20260821T160000Z/`.
- Its `scheduler-state.json` is revision 0: every phase is `pending`, there are no transitions, and `terminal` is null.
- Its first evening trigger is **2026-08-21 17:00 MSK**; the later triggers end at T-10, **18:50 MSK**.
- The directory has no `paper-package-result.json`, `paper-package/`, `operator-result.json`, `.bet-ready`, or `.no-bet`.
- `reports/package_4982.csv` does exist with 22 unique coupons (660 RUB at stake 30), together with `reports/brief_4982.csv`. These are legacy `build-brief` report exports (`index,coupon`) and are not bound to plan `453829753fa55b5f`, a scheduler run, terminal status, or immutable paper-package checkpoint. They are not the requested scheduler-owned training package.
- The morning-dispatch path prepares the current drawing and creates/activates the evening plan. Paper artifacts are persisted only from scheduler terminal/package handling; `paper-package-show` only loads and revalidates an already persisted scheduler-owned paper package.

## 3. Governing implementation files

### Morning discovery and scheduling

- `src/toto_ai/runner/scheduler.py`
  - `_render_morning_preanalysis_wrapper`
  - `_render_morning_launch_agent`
  - `prepare_morning_preanalysis_artifacts`
- `src/toto_ai/runner/morning_dispatch.py`
  - `MorningDispatchConfig`
  - `dispatch_morning`
  - drawing-bound record/reuse/activation logic
  - `load_morning_dispatch_record`
- `src/toto_ai/runner/preflight_retry_scheduler.py`
  - passive retries for an already identified drawing
- `src/toto_ai/runner/preflight_status.py`
  - read-only morning/evening status surface
- `src/toto_ai/cli.py`
  - `morning-preanalysis-plan`
  - `morning-dispatch`
  - `preflight-retry-run`
  - `preflight-status`

### Scheduler-owned paper/training packages

- `src/toto_ai/runner/scheduler.py`
  - `render_paper_package`
  - `validate_paper_package`
  - `persist_paper_package_artifacts`
  - `load_paper_package`
  - `export_paper_package`
  - terminal scheduler call sites that persist PLAY/NO BET paper results
- `src/toto_ai/cli.py`
  - `paper-package-show`
- `src/toto_ai/ev/drawing.py`
  - training/paper mode normalization
- `src/toto_ai/ev/models.py`
- `src/toto_ai/ev/package.py`
- `src/toto_ai/optimizer/brief.py`
  - legacy `brief_<drawing>.csv` and `package_<drawing>.csv` exports; separate from scheduler ownership

## Governing tests

### Morning schedule/dispatch

- `tests/test_scheduler_operational_artifacts.py`
- `tests/test_morning_dispatch.py`
- `tests/test_preflight_escalation_v1.py`
- `tests/test_deadline_tz_and_tminus10_v1.py`
- `tests/test_preflight_retry_scheduler.py`
- `tests/test_preflight_status_v1.py`

### Paper/training package generation and safety

- `tests/test_scheduler_paper_package.py`
- `tests/test_paper_package_cli.py`
- `tests/test_scheduler_last_known_good.py`
- `tests/test_runner_scheduler.py`
- `tests/test_scheduler_atomic_final_end_to_end.py`
- `tests/test_runner_reports.py`
- `tests/test_runner_orchestration.py`
- `tests/test_ev_package.py`
- `tests/test_ev_package_quality.py`
- `tests/test_ev_reports.py`
- `tests/test_runner_end_to_end.py`

## Relevant live artifacts

- `reports/rehearsal/morning-dispatcher-v2/run-morning-preanalysis.sh`
- `reports/rehearsal/morning-dispatcher-v2/totoai-morning-preanalysis.plist`
- `reports/rehearsal/morning-dispatcher-v2/logs/morning.stdout.log`
- `reports/rehearsal/morning-dispatcher-v2/logs/morning.stderr.log`
- `data/scheduler/morning-dispatch/drawing-12054-20260821T160000Z-581cdbbee88e7552.json`
- `reports/rehearsal/evening-4982-20260821T160000Z/scheduler-plan.json`
- `reports/rehearsal/evening-4982-20260821T160000Z/scheduler-state.json`
- `reports/rehearsal/evening-4982-20260821T160000Z/totoai-scheduler.plist`
- `reports/brief_4982.csv`
- `reports/package_4982.csv`
