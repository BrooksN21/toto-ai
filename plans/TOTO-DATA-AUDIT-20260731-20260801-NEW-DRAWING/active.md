# TOTO-DATA-AUDIT-20260731-20260801-NEW-DRAWING

Read-only audit completed 2026-08-04. No DB/code/service changes were made.

## Target identified

The date-scoped new `baltbet-main` drawing for 2026-07-31/2026-08-01 is:

- visible number: **4962**
- internal DB id: **11995**
- DB status: `finished` (the later current open drawing in the same DB is 4965/id 12004)
- deadline: **2026-08-01T15:00:00Z / 2026-08-01 18:00 MSK**
- pool_sum: 9,121,850; jackpot: 19,403,081

## Completeness and presence

- DB `drawings`: present (`id=11995`, `number=4962`, `name=baltbet-main`).
- DB `events`: **15/15**.
- DB `quotes`: **15/15**; pool triple incomplete rows: **0**; BK triple incomplete rows: **0**.
- RAW: present at `data/raw/drawing_11995.json`; sidecar present at `data/raw/drawing_11995.meta.json`.
- RAW payload: **15 events**, pool triple missing: **0**, BK triple missing: **0**.
- RAW `start_at`: **15/15 null**. DB drawing `started_at` is also null; the event table has no `start_at` column.
- RAW metadata: fetched `2026-08-01T11:01:44.029439+00:00`, source `collector-network`, schema 1.
- Canonical RAW archive also exists under `data/raw/archive/drawing_11995/` (5 payload/sidecar pairs observed).

## Scheduler records

- Morning-dispatch record exists:
  `data/scheduler/morning-dispatch/drawing-11995-20260801T150000Z-5e3e39ea59d500a9.json`.
- It records identity 11995/4962 and `activation_status=not_requested`.
- It has `plan_id=null`, `plan_path=null`, and `launch_agent_path=null`: **no evening scheduler plan/LaunchAgent record was created**.
- Passive preflight retry record exists at:
  `data/scheduler/morning-dispatch/preflight/drawing-11995-20260801T150000Z-5e3e39ea59d500a9/retry-plan.json`.
  It is `passive=true`, `activate_evening=false`, with four planned retry attempts and hard stop `2026-08-01T14:00:00Z`.
- The SQLite schema has no `scheduler_states`, `scheduler_runs`, or `morning_dispatch_states` tables (queries against those names returned no table); scheduler evidence is file-based here.
- Dispatch preparation was `unresolved`, with `mapped_count=10` and no event pin/pin-set rows; DB `drawing_preparations` count is 1, `drawing_event_pins`/`drawing_pin_sets`/`drawing_pin_set_items` counts are 0.

## Evidence/commands

Read `AGENTS.md` and all files under `memory-bank/`. Inspected `data/toto.db` through SQLite URI `mode=ro`, `data/raw/drawing_11995.json` and its sidecar/archive, `toto-ai --help`, and the 11995 morning-dispatch/preflight artifacts. No network, mutation, scheduler execution, pytest, or ruff was run.
