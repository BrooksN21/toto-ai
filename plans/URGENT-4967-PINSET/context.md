# URGENT-4967-PINSET — context handoff

## Task and scope
Read-only local investigation of drawing **4967** (internal ID **12010**) failing with `prepare-drawing: conflicting immutable canonical pin set`. No source, scheduler, database, runtime, VCS, or PR state was changed. This handoff is the only project file written.

## Conclusion
**Primary cause: actual cross-layer code defect.** The scheduler plan and `prepare-drawing` command do not carry the reviewed schedule-evidence ledger. The persisted immutable set has 11 `api-sports` plus four reviewed `schedule-evidence` pins. Lacking the ledger, every scheduler attempt reconstructs those four unresolved events as `totobrief-baseline`; publishing that in-memory downgrade correctly trips the immutable guard.

This is a **baseline-vs-schedule-evidence downgrade attempt caused by a missing scheduler/CLI handoff**, not primarily stale runtime. Commit `3a08a30` added correct monotonic upgrade behavior, but only when the ledger is supplied. Reversed ordering at order 13 is real context but is represented correctly by the persisted pin and is not the trigger.

## Scheduler and stages
Dispatch: `/Users/turshevr/toto-ai/data/scheduler/morning-dispatch/drawing-12010-20260806T150000Z-68e76b821ab4f5aa.json`.

- `scheduled/ready`, activation `activated`; deadline `2026-08-06T15:00:00Z`.
- Fingerprint `68e76b821ab4f5aada592ca90888850e910b4604c4015d1a446d73c265304323`.
- Detail SHA `b93386fff1efa2ebde8ce4a0645b72578ceae2328dd59ba59e9462fb025251a9`.
- Ledger/catalog hash `f4a9191d5e07ddc41e5aaf15149fe8279623f50c6e3b62a77af70fa111515f64`.
- Observed `2026-08-06T08:23:29.714645Z`; ready, 15/15 covered, `baseline_event_orders=[]`.
- Plan ID `40e59c20dcfc3efc`; label `com.totoai.production-scheduler.v5.40e59c20dcfc3efc`.

Plan `/Users/turshevr/toto-ai/reports/rehearsal/evening-4967-20260806T150000Z/scheduler-plan.json` is schema v5. It binds the reviewed hash but has **no ledger path**. Deadlines: T-120 13:00Z, T-90 13:30Z, T-60 14:00Z, T-45 14:15Z, T-30 14:30Z, T-20 14:40Z, T-16 14:44Z, T-10 14:50Z, end 15:00Z.

State `/Users/turshevr/toto-ai/reports/rehearsal/evening-4967-20260806T150000Z/scheduler-state.json`: revision 10, updated `2026-08-06T14:31:31.778970Z`, `terminal=null`, final/publish pending.

| Stage | Started | Failed | Status/category |
|---|---|---|---|
| tls_preflight | `2026-08-06T13:00:10.070587Z` | `2026-08-06T13:01:04.558827Z` | retryable_failed/connect |
| api_preflight | `2026-08-06T13:30:09.326125Z` | `2026-08-06T13:31:07.328019Z` | retryable_failed/connect |
| freshness_preflight | `2026-08-06T14:00:04.994731Z` | `2026-08-06T14:01:08.479155Z` | retryable_failed/connect |
| warmup | `2026-08-06T14:15:07.206991Z` | `2026-08-06T14:17:02.353093Z` | retryable_failed/connect |
| refresh | `2026-08-06T14:30:22.552754Z` | `2026-08-06T14:31:31.778970Z` | retryable_failed/connect |

All have attempt count 1, `status_code=null`, chain `["SchedulerTransientError"]`, and the same immutable-conflict message. `connect` is misleading: this is deterministic integrity validation. Latest raw detail/meta was fetched `2026-08-06T14:30:23.302710+00:00`, SHA `d8c02e58c6eae5766ca91bcd6e45577c0a42364a7f4de78943be0c6502486e09`; event identities were unchanged, so it is not a one-off stale raw cache.

## Conflicting sets

### A — persisted ready canonical set
ID `pinset-f92d03f6275d0655cb236f77d0ff4aed6e7f91970d2c0a6f28ec04182e894cd5`; 11 API + 4 schedule; created `2026-08-06T08:23:29.702623+00:00`; same fingerprint and ledger hash. Orders are zero-based.

| Order/visible | Event ID; target | Evidence ID; kickoff; orientation | Evidence hash / source-identity | Pin hash | Record/review times |
|---|---|---|---|---|---|
| 1/2 | 179254; Ягеллония—Рейнджерс | `uefa-2049126`; `2026-08-06T16:00:00Z`; same | `1465eabc023e11f843ffd30f9fb1555009987a486db10a9d7f404aa6024419b7` / `ed7267a21e4dd973009d7310833b1fdbdca0acbc834a6aab9109d42d1192283a` | `064fb8e9222e5dad5b65bcceb9597d358ff6afcc86e6c41d446cfc9808697267` | set `2026-08-06T08:23:29.702623Z`; reviewed `2026-08-05T17:04:04Z` |
| 8/9 | 179261; Ракув—Хаммарбю | `uefa-2049165`; `2026-08-06T18:00:00Z`; same | `92de7ba11c262544344c4c0740ded66d95374b470a6935bcfad732d4f1572877` / `c55e7327f4ce223218b416fc71a7c422a60b24e1e7d1aec29dd8682235e3d30a` | `b0c342a7c66b577ee6318e73c2e2ec21d8413bd6affa154f503d62debf2b1b34` | same |
| 13/14 | 179266; Крус Асуль—Филадельфия | `philadelphia-union-cruz-azul-leagues-cup-20260806`; `2026-08-07T00:00:00Z`; **reversed** | `cf25a4be3efb1a49c581db7bd27515cfd3d7705c4aef15221907eaf96e8c04e9` / `f52a78285159d8bdb963c60d005090d0a424edd4eae159eca724a1fcd4631d26` | `b8c4e6d39e52b749211d647a0a7698ee857d03d909516818e5280ef02035c2ea` | same |
| 14/15 | 179267; Остин—Тихуана | `austin-fc-club-tijuana-leagues-cup-20260806`; `2026-08-07T01:00:00Z`; same | `b2a97a1e28aeb377fd2b5f61ae9772f7ffbdd0c8644135e52953a18c0dbdb670` / `b8a46e738fb7ef2b4a90b111f5ecec2f0f3006fef9886026679606b07d8ed6a4` | `401a377dd8cb21c347501fc1ddeff3641257b9952e399c73345f5515f4be4bef` | same |

Ledger `/Users/turshevr/toto-ai/data/schedule-evidence/ledger.json`: schema 1, generated `2026-08-03T18:00Z`, mtime `2026-08-05T20:05:28+0300`. Reviews under `data/schedule-evidence/reviews/`: mtime `2026-08-05T20:04:25+0300`, reviewed `2026-08-05T17:04:04Z`.

### B — scheduler proposal (**uncommitted/in-memory**)
**Never committed: hash and record timestamp are unavailable because publication aborts/rolls back.** Provenance is the stage attempt times above. Same expected 11 API rows plus:

| Order/visible | Event ID | Proposed source | Resolver evidence |
|---|---:|---|---|
| 1/2 | 179254 | totobrief-baseline | fixture 1598830, score .584, margin .124, insufficient |
| 8/9 | 179261 | totobrief-baseline | fixture 1607594, score .581, margin .189, insufficient |
| 13/14 | 179266 | totobrief-baseline | fixture 1530121, score .734519, margin .322, insufficient |
| 14/15 | 179267 | totobrief-baseline | fixture 1530119, score .792208, margin .246, insufficient |

API cache `data/external-cache/api-sports/d331d492...json` (fetched `2026-08-06T06:04:01.148912Z`) has fixture 1530121 as Cruz Azul home/Philadelphia away and 1530119 as Austin home/Tijuana away. Official review lists Philadelphia—Cruz Azul; canonical provenance records reversed orientation without provider IDs. This is expected.

SQLite free-page evidence shows a former baseline state at orders [1,8,13,14], including order 8 created `2026-08-05T16:48:31.897403Z`, pin `0b621046894d7d39c140d0bb57ab3b4f4ec51803f3b1c2efbb6e61d3f9954cab`. It is forensic, not active; an old set ID from free pages is non-authoritative.

## Code path
1. `src/toto_ai/runner/scheduler.py:2215-2249`, `build_prepare_drawing_command`: no ledger forwarding.
2. `src/toto_ai/cli.py:3533-3725`: no `--schedule-evidence-ledger`; call near 3716 cannot pass it.
3. `src/toto_ai/external_odds/preparation.py:185-276`: without ledger uses legacy `load_ready_drawing_pins`, not canonical `load_ready_pin_set`.
4. `preparation.py:313-337`: schedule evidence/upgrade orders require ledger.
5. `preparation.py:480-570`: unresolved events become baseline.
6. `preparation.py:740-780`: publisher enrichment flag is false.
7. `src/toto_ai/storage/team_registry.py:957-1061`: differing ready same-fingerprint set; line 1061 raises conflict.
8. `scheduler.py:2378-2423`: subprocess failure becomes transient/retryable.

`team_registry.py:1137-1167` correctly permits baseline→schedule only, never schedule→baseline.

## Why 3a08a30 did not prevent it
Commit `3a08a306acb378aaa6fec1dbd081bf3a7c30d7f9`, `Thu Aug 6 11:27:13 2026 +0300`, “Harden TotoBrief TLS handling and prepare drawing 4967” added monotonic upgrade helpers, a narrow safe transition, and hash validation. They work only when `prepare_drawing(... schedule_evidence_ledger=...)` receives the ledger. Scheduler plan/command/CLI omit it, so upgrade orders are empty and a downgrade is reconstructed.

Tests cover registry/partial-enrichment logic at `tests/test_team_registry.py:737,788,826,880` and `tests/test_partial_enrichment.py:300,381`. Gap: no schema-v5 scheduler ledger-propagation or already-upgraded scheduler-idempotency regression.

## Root-cause classification
| Candidate | Result |
|---|---|
| Missing plan→command→CLI ledger handoff | **Primary code defect** |
| Baseline vs schedule evidence | **Immediate manifestation** |
| Stale runtime | **Not primary** |
| Old baseline DB material | **Contributing/forensic only** |
| Reversed order 13 | **Nuance, not root** |
| Retry/connect classification | **Secondary defect** |

## Minimal fix and regression matrix
Fix: bind a contained ledger path plus semantic hash into SchedulerPlan identity/reload; add/forward `--schedule-evidence-ledger`; prefer canonical loader when canonical state exists and fail closed on missing/mismatched ledger before baseline construction; keep downgrade rejection; classify immutable integrity errors as terminal.

Regressions: exact plan/command/CLI ledger pass-through and path/hash tamper rejection; idempotent reuse of existing 11+4 schedule set; missing ledger produces terminal zero-mutation failure; initial 11+4 baseline upgrades only orders 1,8,13,14; fresh provider metadata cannot mutate upgraded pins; reversed order 13 preserves target probabilities/provenance/no provider IDs; ledger hash/kickoff/orientation drift rejects atomically; pool-only refresh remains allowed but identity/BK drift fails; API-only legacy drawings remain compatible; immutable conflict is not retried through all stages.

## Uncertainties/gaps
- Normal `sqlite3` read was blocked; DB evidence came from read-only binary `rg -a` on `/Users/turshevr/toto-ai/data/toto.db`. Active-set evidence is consistent; free-page history is non-authoritative.
- Set B is **uncommitted/in-memory**, with no hash/timestamp. Logs truncate inner output; four differences are reconstructed from code path, diagnostics, identities, and conflict.
- State may have evolved after revision 10 at `2026-08-06T14:31:31.778970Z`; then terminal was null.
- No network or state-mutating commands were used.

## Inspected paths and useful commands
Inspected: `/Users/turshevr/toto-ai/AGENTS.md`, `/Users/turshevr/toto-ai/memory-bank/`, dispatch/plan/state/logs/attempt paths above, `/Users/turshevr/toto-ai/data/toto.db`, raw drawing/meta, ledger/reviews, API cache, the four source files and two tests above, and local commit `3a08a30`.

Read-only commands used: `cat`, targeted `sed -n`, targeted `rg`/`rg -a`, and `git show --format=fuller 3a08a30 -- <targeted paths>`.
