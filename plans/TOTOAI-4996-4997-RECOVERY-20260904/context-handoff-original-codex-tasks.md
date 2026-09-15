# Original Codex tasks recovered - TOTOAI-4996-4997-RECOVERY-20260904

Completed: 2026-09-05T14:09:04.328535+03:00. Context worker 01a07102-7504-74d2-8ed2-147f9c2e3367.
All shell cwd /Users/turshevr/toto-ai. READ-ONLY DISCOVERY; no resume/control action.

## Result: both ORIGINAL tasks exist and are accessible through supported app tools
Empty active/archive listings were not proof of absence. Exact local cwd bindings
located both IDs; read_thread and wait_threads independently succeeded for each.
Both are idle, latest turn completed with error=null; neither is currently running.
SQLite archived=0 for both. No unarchive, replacement, fork or metadata repair needed.
The reason list views omitted them was not investigated; no list/config workaround.

### Review
- Verbatim app title: TotoAI — ревью и упрощение проекта
- Actual thread ID: `01a06e1d-e0b9-7310-ba37-53a418668354`; hostId `local`.
- Original/current app cwd: `/Users/turshevr/.codex/worktrees/ab34/toto-ai`.
- Created: 2026-09-04T23:30:46+03:00; latest turn 2026-09-04T23:30:47+03:00 to 2026-09-04T23:45:03+03:00.
- Last state: idle / completed. Saved review report exists; verdict then not ready
  for commit/push. No running review process inferred from historical work.
- Original report: `/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904-PRE_PUSH_REVIEW.md`.

### Models
- Verbatim app title (ellipsis is actually in stored/app title): TotoAI — спортивные модели и качество…
- Actual thread ID: `01a06e1d-f37f-7763-ac2a-86200d3318e3`; hostId `local`.
- Original/current app cwd: `/Users/turshevr/.codex/worktrees/a7aa/toto-ai`.
- Created: 2026-09-04T23:30:51+03:00; latest turn 2026-09-04T23:30:52+03:00 to 2026-09-04T23:38:07+03:00.
- Last state: idle / completed. Completion refers to the readiness report, NOT a
  model implementation. Last delivery tool failed, but the task itself completed.
- Original report: `/Users/turshevr/.codex/worktrees/a7aa/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/MODEL_READINESS_REPORT.md`.

## Evidence / identity limits
- `/Users/turshevr/.codex/state_5.sqlite`: mode=ro + query_only, exact cwd/ID queries,
  bounded 3-5s. Original source=vscode, thread_source=agent_created_thread, both
  baseline a17e0771e5ad1d3dc4990ce917b6135c8f7168f2 and no branch recorded.
- `/Users/turshevr/.codex/session_index.jsonl`: exact ID matches corroborate names.
- read_thread confirms both actual IDs/titles/cwds; wait_threads confirms idle,
  completed turns and snapshot cursors. No raw rollout/history files opened.
- Old client setup IDs 2b5bc4b5-884f-4de7-9d1a-2b6a3ba49535 and
  41007dcf-86d4-4e50-8d6d-44a4afaeb8cf are NOT actual IDs. No direct client-to-server
  mapping was verified or invented; exact worktree/path/date/app records identify
  originals without needing such a mapping.
- Main registry and older recovered handoff still say actual IDs unknown; this
  finding supersedes that identity uncertainty only. Parent owns central updates.

## Short Sept4 timeline - reuse saved reports, no repeated audit
- 23:30:46/23:30:51 MSK: original review/models tasks created at ab34/a7aa.
- Models observed 23:35:25; readiness report mtime23:36:30.451208; final turn
  completed23:38:07. Saved next incomplete work is F3/P1 read-only coverage auditor
  for4990-4995; baseline and predeclared minimum_prior_matches blocked execution.
- Review report mtime23:44:47.415751; final turn completed23:45:03. Four P1 plus
  preexisting P2 captured; no production edits or tests rerun by that review.
- Both historical send_message_to_thread deliveries to operations were rejected;
  report files survived. Their failure did not erase or invalidate task identity.
- Sept5 exact report copies already preserved under
  `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/recovered-reports/`.
  Source/copy hashes and detailed reusable scope remain in
  `/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/context-handoff-recovered-worktrees.md`
  and its `recovered-reports/provenance.json`; not recalculated/re-copied here.
- Current ACTIVE at14:01 records strict replay-reuse validation integrated,46tests;
  unsafe fresh/newest-result replay disabled. Do not rerun old noon repair or treat
  all historical review findings as unchanged. Exact-result-bound fresh producer,
  generic retry calendar, coherent baseline/backfill and F3/P1 gates remain open.

## Supported continuation and monitoring - parent actions, NOT executed here
1. To show either same original chat: navigate_to_codex_page(threadId=<actual ID>).
2. To continue that same task: send_message_to_thread(threadId=<actual ID>,
   hostId="local", prompt=<bounded current owner-authorized continuation>).
   Omit model/thinking to retain settings. This sends a new turn to an existing
   task; it neither creates a replacement nor copies/moves the worktree.
3. Before useful work, the parent follow-up must convey current scope and saved
   checkpoint paths: old worktree policy/memory/baseline remain historical.
   Existing reports are context, not permission to write production/worktrees,
   copy dirty code, rerun completed4996 work, or run models with an unreviewed baseline.
4. Monitor through bounded wait_threads(targets=[{threadId,hostId:"local",afterCursor},
   ...],timeoutMs=120000), using returned cursors and updating after each change.
   It returns on the first completed/attention target; a multi-target request may
   return only that target. This diagnosis therefore obtained a separate compact
   snapshot for models after review woke the initial two-target call.
   Current cursors:
   - 01a06e1d-e0b9-7310-ba37-53a418668354: `9223d22e-dbee-4332-87ed-9501fe62d18a:1`.
   - 01a06e1d-f37f-7763-ac2a-86200d3318e3: `cef31e76-dda7-4081-a2cd-13bdf8247c1f:1`.
5. read_thread is for targeted details when needed, not repeated full-history polls.
   No heartbeat or unattended idle-chat wakeup. The plan-bound local Python watcher
   remains the separate canonical4997 operational observer.

## Permission and operational boundary
Read/status access is now VERIFIED; a new follow-up has NOT been sent or acceptance-
tested. Prior rejected cross-task delivery/creation is not permission to bypass
anything. If an app control call is rejected, stop and report its exact result;
do not edit app SQLite/config, change policies, use CLI resume as a workaround,
create/fork replacements or keep retrying. Task existence is not blanket write or
experiment authorization. The caller requested only discovery from this worker.
No code/DB/scheduler/auth/publication/worktree mutations; no tasks created/resumed.
4997 first checkpoint14:30 MSK and cutoff16:20 unchanged; main operations owns them.
Discovery finished before14:16. Next exact step: parent may use the supported
same-task follow-up route above within the currently authorized scope, then wait_threads.

Machine-readable identity/status/evidence/monitor cursors:
`/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/original-task-id-findings.json`.

## Registry persistence and policy-version conflict - 2026-09-05T14:11:08.456456+03:00

The context worker was explicitly assigned registry ownership for this update.
Actual IDs, exact app titles, original cwds, observed idle/completed states,
monitor cursors and preserved-worktree mappings are now saved in
`/Users/turshevr/toto-ai/memory-bank/THREAD_COORDINATION.json`. Prior null-ID/setup
records remain in coordination_history; client IDs are not asserted direct mappings.
ACTIVE_PLAN has a short overriding identity checkpoint; no production state changed.

- /Users/turshevr/toto-ai/AGENTS.md; mtime 2026-09-05T13:38:27.708319+03:00; SHA256 7cb5bebe2218bfe31f438f507bef60991fb687dad665a4e37f6f1487d1712591.
- /Users/turshevr/toto-ai/memory-bank/TOOLING_POLICY.md; mtime 2026-09-05T13:38:27.843734+03:00; SHA256 2495aa1539d5ca3e9bd639d51ed61ba4aa87f8e398ad97566ba58f318e2b9486.
- /Users/turshevr/.codex/worktrees/ab34/toto-ai/AGENTS.md; mtime 2026-09-04T23:30:45.174068+03:00; SHA256 a0c5e78239a24048554f2ee9829dc36eb9ef509acbeddba5237cd13ec0e02951.
- /Users/turshevr/.codex/worktrees/ab34/toto-ai/memory-bank/TOOLING_POLICY.md; mtime 2026-09-04T23:30:45.447004+03:00; SHA256 0cf4564e3b60d7eb3b651afadd78cfca0683ae163e41b57e7a6c5e6336eadd51.
- /Users/turshevr/.codex/worktrees/a7aa/toto-ai/AGENTS.md; mtime 2026-09-04T23:30:50.679741+03:00; SHA256 a0c5e78239a24048554f2ee9829dc36eb9ef509acbeddba5237cd13ec0e02951.
- /Users/turshevr/.codex/worktrees/a7aa/toto-ai/memory-bank/TOOLING_POLICY.md; mtime 2026-09-04T23:30:50.876995+03:00; SHA256 0cf4564e3b60d7eb3b651afadd78cfca0683ae163e41b57e7a6c5e6336eadd51.

Main policies (13:38 Sept5) still specify single-task execution/cancelled split;
original task files are older Sept4 copies and retain external-model/nested-agent
prohibitions. Latest owner direction is native continuation of the originals, not
new task creation. This is an explicit policy/scope compatibility issue for the
parent follow-up, NOT permission to edit policy or circumvent a refusal. The prior
failed cross-task delivery is not a current permission test. No new message sent.
Main remains operations owner; original chats must accept current same-scoped
boundaries and reviewed baseline before work. No production writes, nested agents,
outside-root edits or model experiments are authorized by this metadata update.
