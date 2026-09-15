# Worktree-aware Git inspection — implementation handoff

Task:TOTOAI-4996-4997-RECOVERY-20260904.
Executor01a07108-e153-7df2-8597-397cb71b3589, cwd/Users/turshevr/toto-ai.

## Done
- `scripts/project-git` adds explicit `--registered-worktree <absolutepath>`
  read-only inspection, anchored to the main wrapper's existing strict root check.
- Verifies canonical checkout/gitdir/common-dir, exact registration/backlink,
  direct registration under same main.git/worktrees, and independent Git output.
- Rejects symlink/copied Git-file/foreign/common-dir/root mismatch, HOME,
  generic repository/config overrides, gitlsfiles and cross-checkout writes.
- Read-only commands:rev-parse,status,restricted name/stat diff. GIT_OPTIONAL_LOCKS=0;
  fsmonitor disabled; no target wrapper install/copy. No new task/worktree/deletion.
- Existing main checkout/Python helper behavior unchanged; source helper not edited.
- Tests18 synthetic +34 existing guard =52passed8.72s; Ruffclean;shellsyntaxclean.
  Synthetic fixtures create only minimal Git metadata, not worktrees or bareGitcommands.

## Existing worktree findings,13:48MSK
1./Users/turshevr/.codex/worktrees/ab34/toto-ai
  gitdir /Users/turshevr/toto-ai/.git/worktrees/toto-ai;common main.git.
  status:?? plans/TOTOAI-4996-4997-RECOVERY-20260904-PRE_PUSH_REVIEW.md
2./Users/turshevr/.codex/worktrees/a7aa/toto-ai
  gitdir /Users/turshevr/toto-ai/.git/worktrees/toto-ai1;common main.git.
  status:?? plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/
Both attest/status exit0. No tracked modification reported by these snapshots.
No artifact contents/secret contents read. Worktrees/files preserved.
Normal -untracked-files=normal groups directories; this is not a recursive file inventory.

## Limits / exact supported next mechanism
Use the MAIN wrapper with --registered-worktree for scoped readonlyinspection.
Own worktree wrapper/Python Git helper remain old and are not assumed worktree-aware.
No outside-primary writes approved/performed. Fully enabling independent worktree
engineering would require explicitly approved scoped install and baseline review.
Git attestation success alone does NOT prove model-data/code readiness or create
an authorized child task. Native creation remains prohibited; do not retry/workaround.
Owner revoked split then stopped deletion; retain allthreeworkstreams in active task.

## Files/tests/processes
Changed:scripts/project-git;added tests/test_project_git_worktrees.py;
knowledge/project_git_worktrees.md;ACTIVE_PLAN/coordination checkpoint and this report.
Evidence:worktree-readonly-status-20260905.json; full listed filenames only.
No4997scheduler/model/datachange;authorizationreceipts preserved.
No pending shell/Python process; all tests and readonly inspections completed.
No commit/push/branch/PR. Parent owns integration/review.
Next operational checkpoint4997 14:30MSK;cutoff16:20MSK unchanged.

## Exact preserved paths for next separate context collection
- /Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904-PRE_PUSH_REVIEW.md
- /Users/turshevr/.codex/worktrees/a7aa/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/MODEL_READINESS_REPORT.md
Contents were NOT read/copied/rewritten. Prior materials exist; actual author/task identity remains unknown. No claim that previous children performed no work.
