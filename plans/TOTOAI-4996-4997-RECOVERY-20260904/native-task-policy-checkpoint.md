# Permission-only implementation handoff

Task TOTOAI-4996-4997-RECOVERY-20260904. Policy worker only; no commit/staging/push.
Owner quote is saved verbatim in native-task-owner-authorization-20260905.json:
«я владелец и я разрешаю тебе закоммитить разрешение на продолжение работы в дочерних ветках».
This authorizes policy edit/commit, not external models or remote publication.

## Done
- AGENTS.md and memory-bank/TOOLING_POLICY.md now have identical narrow exception.
- Parent019f7afa-72e2-7403-85cd-d05f408a4ef3 may resume/read/monitor ONLY:
  review01a06e1d-e0b9-7310-ba37-53a418668354 at ab34/toto-ai;
  models01a06e1d-f37f-7763-ac2a-86200d3318e3 at a7aa/toto-ai.
- Native local Codex send_message_to_thread/read_thread/wait_threads only;
  same-project minimal local data handoff, never credentials/unrelated data.
- Existing task-hosting model only; no override/nested/model-backed SUBAGENTS;
  no new tasks/worktrees/forks/setup recreation or workaround denied actions.
- External LLM/Claude/Anthropic/Eliza/proxy/Yandex prohibition paragraphs intact.
- Parent exclusive production4997; children own reports/explicitly assigned code,
  exact cwd/attested wrapper; no productionDB/jobs/consent/catalog/operator changes.
- Earlier temporary cancellation wording removed only where it contradicts this
  exact exception. Other dirty policy changes preserved, not bundled into patch.

## Verification
7 tests passed (existing2 tooling-policy +5 scoped invariants); Ruff scoped checks clean.
`project-git apply --cached --check` on permission-only.patch passed; CHECK ONLY,
no index changes. Before check the TWO policy paths had no staged changes.
No fullsuite, runtime/API/model calls, child writes or operational changes.

## Finalizer minimal commit route (NOT EXECUTED)
All commands cwd /Users/turshevr/toto-ai; use scripts/project-git.
1. Confirm HEAD still a17e0771e5ad1d3dc4990ce917b6135c8f7168f2 and no conflicting
   staged changes. If unrelated staged work exists, preserve it and stop to isolate
   safely; never reset/stage all or include somebody else's changes.
2. Re-run:
   scripts/project-git apply --cached --check plans/TOTOAI-4996-4997-RECOVERY-20260904/native-task-permission-only.patch
3. ONLY when finalization is authorized, stage this exact patch:
   scripts/project-git apply --cached plans/TOTOAI-4996-4997-RECOVERY-20260904/native-task-permission-only.patch
4. If retaining authorization provenance in the same permission-only commit:
   scripts/project-git add -- plans/TOTOAI-4996-4997-RECOVERY-20260904/native-task-owner-authorization-20260905.json
5. Inspect exact staged diff and run the focused checks before commit. DO NOT
   `add AGENTS.md memory-bank/TOOLING_POLICY.md` or `commit --only <policyfiles>`:
   those would absorb unrelated working-tree policy changes. No push permitted here.
The minimal patch adds ONLY the named native-task permission block to the two HEAD
policy files. It deliberately excludes earlier recovery/memory/watcher/wager edits.
Manifest stores before/after working hashes and expected minimal-index target hashes.
The separate working-delta.patch records just this worker's edits, not staged.

## Remaining conflicts / boundaries
- Permission commit pending separate finalizer. No resume/monitor attempt made here;
  no claim the host permission reviewer will accept the new policy automatically.
- ACTIVE/registry can contain older cancellation history; parent reconciles its
  current checkpoint separately. Their files not edited by this policy-only worker.
- Child worktrees retain old policy/wrapper/baseline; this edit does not install/copy
  files there or prove code-data readiness. Parent must convey committed scope and
  receive actual-ID/cwd acknowledgment before assigning work; filesystem/tool
  restrictions still apply and must not be bypassed.
- Main4997 remains operations owner's job; first14:30MSK,cutoff16:20 unchanged.
No owned process remains. Next step: finalizer review+minimal local policy commit,
then parent native continuation only if authorized/accepted; prioritize14:30operations.
