# Next drawing — bounded context, 15 September 2026

Task: TOTOAI-RESUME-20260915. Delegated context collection only; cwd `/Users/turshevr/toto-ai`.

## Confirmed discovery
- Successful public native `TotoBriefClient.drawings('baltbet-main', page=1)` at **2026-09-15 20:05:50.627235 MSK**. Endpoint: https://totobrief.com/api/v1/community/baltbet-main/drawings?page=1 . One request, 12-second transport timeout / 25-second wall bound, TLS verification enabled, no retries, no DB or shared rate-state writes.
- Returned newest drawing **5007 / API id 12127**, status `expected`; all other returned rows were `finished`. No active successor in this response. This is a snapshot, NOT a permanent assertion that BaltBet has no open drawing. Appearance after the check remains unchecked; **do not assume 5008 or invent its API id/deadline**.
- Raw 5007 `ended_at=2026-09-15T20:00:00.000000Z` means **15 September 20:00 MSK**, using the repository's native `parse_totobrief_timestamp` BaltBet wall-clock contract, not 23:00 MSK.
- Suggested next bounded discovery: **15 September 20:07 MSK**; not scheduled or performed by this context job. If that checkpoint has passed, perform one fresh check in the next authorized job, without indefinite polling.

## Existing runtime relevance
- Exact launchctl inspection: `com.totoai.production-scheduler.v9.84b0f69e06487848` is loaded, **not running**, and points to `/Users/turshevr/toto-ai/reports/rehearsal/evening-5007-20260915T170000Z/run-scheduler.sh`. It covers only expired 5007, not a successor.
- `com.totoai.morning-dispatcher.v1` is loaded, **not running**, and points to the v10 parallel-safe wrapper below. Recheck activity/ownership before operational execution to avoid duplicates; this snapshot is not a lock guarantee.
- Latest ACTIVE_PLAN records both 5007 releases expired at 19:50; no consent transfers to another drawing. This job did not reaudit 5007.

## Next existing preparation procedure — NOT executed
After successful current-open discovery, the operations owner can use the existing native wrapper, subject to no competing dispatcher and authorization for operational writes:

```sh
cd /Users/turshevr/toto-ai
/bin/sh /Users/turshevr/toto-ai/reports/rehearsal/morning-dispatcher-v10-parallel-safe/run-morning-preanalysis.sh
```

The inspected wrapper invokes existing `morning-dispatch`, not a new architecture. Its exact configured arguments are:

```sh
/Users/turshevr/toto-ai/.venv/bin/python -m toto_ai.cli morning-dispatch --bank 4980 --stake 30 --env-file /Users/turshevr/toto-ai/.env --project-root /Users/turshevr/toto-ai --state-root /Users/turshevr/toto-ai/data/scheduler/morning-dispatch --scheduler-root /Users/turshevr/toto-ai/reports/rehearsal --db /Users/turshevr/toto-ai/data/toto.db --aliases /Users/turshevr/toto-ai/data/external-odds/team-aliases.json --raw-cache-dir /Users/turshevr/toto-ai/data/raw --totobrief-rate-state /Users/turshevr/toto-ai/data/totobrief-cache/request-state.json --cache-root /Users/turshevr/toto-ai/data/external-cache/api-sports --activate --goal-shadow-auto --parallel-challenger-auto
```

The wrapper securely loads `.env`; no secret was read by this job. It requires API_SPORTS_KEY presence and exports optional TheSportsDB settings. Presence is not proof of API-Sports access; prior suspension is not rechecked here. The wrapper has up to two delayed retries for selected failures; do not launch it merely as a read-only discovery command.

Required subsequent inputs: fresh actual community/number/API-id/deadline and native identity fingerprint; 15 correctly identified fixtures and reviewed timing/source evidence; configured aliases/ledger/caches; provisional bank 4980/stake30. Resolve missing timing using existing reviewed-source flow without weakening identity/time/hash gates. Do not reuse 5007 expected-id/fingerprint flags from the earlier context.

Only after native preparation creates a valid successor plan: attest its actual plan path/id/deadline, source/catalog bindings, primary and four-model parallel jobs, and plan-bound Python watcher; use existing `scheduler-preflight-only --plan <actual successor plan>` in an explicitly authorized operational job. No successor plan or PLAY readiness is asserted here. Request fresh exact-plan consent before any experimental release. No heartbeat or automatic wagers.

## Owner report / scope
- Owner reports actually placing **5007 quality-v3 for 4980 RUB**. This is user-reported placement, not receipt verification or payout evidence and not a permanent future selection rule. Earlier memory saying choice unknown is superseded only by this report.
- Saved context only. No DB, jobs, scheduler, consent, package, code, Git or publication mutation. ACTIVE_PLAN/THREAD_COORDINATION read; no whole-project audit. No successor preparation or model job launched.
