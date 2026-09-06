# Safe inspection of existing linked worktrees

The owner stopped worktree deletion on 2026-09-05. Preserve existing changes;
inspection does not authorize new tasks, worktrees, writes or experiments.

The main wrapper supports an explicit read-only mode:

```sh
scripts/project-git --registered-worktree /absolute/canonical/checkout \
  status --short --untracked-files=normal
scripts/project-git --registered-worktree /absolute/canonical/checkout \
  rev-parse --path-format=absolute --show-toplevel --git-dir --git-common-dir
```

Run from `/Users/turshevr/toto-ai`. The main wrapper attests its own root first,
then requires the target's ordinary absolute Git-file route to a direct child
of this repository's `.git/worktrees/`, the registration's exact backlink,
matching canonical common-dir, and independent Git attestation of all three
paths. Symlinks, copied Git-files, foreign repositories and `$HOME` fail closed.
No target registration name or two specific Codex paths is hardcoded.

Allowed cross-checkout commands: `rev-parse`, `status`, and restricted
name/stat-only `diff`. Writes, aliases, arbitrary diff drivers/output files,
`ls-files`, generic `-C`/Git-dir/config overrides remain forbidden. Optional
Git locks and filesystem-monitor hooks are disabled in this read-only mode.
Normal main-checkout behavior and routing-environment sanitation are retained.

This is NOT a replacement for the older wrapper/Python Git helper inside a
linked checkout. Those copies remain unchanged and may still reject linked
worktrees. Installing/updating them needs separately approved filesystem scope
and review. The new main-wrapper mode can inspect without copying those files.
Relative Git-file/backlink layouts are deliberately not supported; fail closed
instead of guessing. Normal Git-created absolute registrations are supported.

Evidence: `plans/TOTOAI-4996-4997-RECOVERY-20260904/worktree-readonly-status-20260905.json`.
Both preserved Codex worktrees pass. `ab34` has an untracked pre-push review file;
`a7aa` has an untracked Sports-v3 readiness directory. Tracked modifications were
not reported. Contents/baseline readiness were not audited by this slice.

Tests: `tests/test_project_git_worktrees.py` constructs minimal synthetic Git
metadata without worktree creation/deletion or fixture Git setup commands.
Run together with `tests/test_project_git_guard.py`; 52 passed on 2026-09-05.
