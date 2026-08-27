# TOTO-4989 operator delivery and automatic preparation plan

## Goal

Make the next-drawing lifecycle autonomous and give the operator enough time
to upload a verified package manually. Automatic wagering remains prohibited.

## P0 sequence

1. Restore a green scheduler regression suite. Reproduce and fix the atomic
   final preparation-refresh failure without weakening the immutable
   probability-input guard.
2. Prepare drawing 4989 through the existing automatic morning/retry path.
   Require exact identity plus reviewed kickoff evidence for all 15 events
   before generating an evening plan.
3. Move the primary final start from T-20 to T-25. Target normal publication
   before T-20 while retaining the fail-closed T-10 revocation boundary.
4. Add a stable operator-delivery record written immediately after a verified
   pre-T-10 `PLAY`. It must expose the current upload path, count, cost, hash,
   publication time and expiry time without changing coupon selection.
5. Preserve the exact package archive after expiry for explicitly requested,
   hash-verified analysis, while keeping every wagering surface revoked.

## Automatic next-drawing lifecycle

The installed 15-minute `com.totoai.morning-dispatcher.v1` remains the sole
generic discovery loop. It must always run `morning-dispatch --activate`, so a
new drawing is synchronized and either:

- becomes READY and installs its evening scheduler; or
- becomes deferred and installs an identity-bound passive retry LaunchAgent.

Do not create a second polling daemon. Add contract/status checks that prove
the installed wrapper contains `--activate`, the current drawing record is
fresh, and a deferred drawing has a loaded retry job.

## Verification

- Focused regression for atomic final refresh.
- Delivery timing and expiry tests around T-25/T-20/T-10.
- Morning dispatcher/retry contract tests.
- Package hash/count/cost invariants unchanged.
- Full default pytest, Ruff and `scripts/project-git diff --check`.
- One package-free live preflight for drawing 4989 before evening activation.

## Release

Update `memory-bank/CURRENT_STATE.md`, `DECISIONS.md`, `ROADMAP.md` and
`ARCHITECTURE.md` as applicable. Commit in logical units, push `main`, and
verify `main...origin/main` is `0/0`.
