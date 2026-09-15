# TOTOAI-4992 / TOTOAI-4993 context

## Repository state

- `main` HEAD `192e837936bce0fe9f59e84f49e0da164caad82d` equals `origin/main` (0 ahead, 0 behind).
- No staged changes.
- Dirty runtime state:
  - tracked: `data/schedule-evidence/ledger.json`;
  - untracked: `reviews/snapshots`;
  - untracked source: `src/toto_ai/operations/post_draw_attribution.py`;
  - untracked test: `tests/test_post_draw_attribution.py`.

## TOTOAI-4992

- Internal drawing `12083`, plan `1d837ebf02c14788`.
- All production scheduler phases completed.
- Final package: `166/4980`, created before T-10 and then correctly expired.
- Production LaunchAgent is unloaded.
- Post-draw LaunchAgent `com.toto-ai.post-draw-12083` is loaded; first run: `2026-09-01 12:00 MSK`.
- Database currently has `0/15` results and a stale active status.

## TOTOAI-4993

- Internal drawing `12086` is active with 15 events.
- Deadline: `2026-09-01 17:00 UTC` / `20:00 MSK`.
- Automated retry currently has `1/15` verified and 14 unresolved events; there is no plan or scheduler.
- Authoritative public timing evidence has been collected for all 15 events, but reviewed records were not applied.

## Gaps and implementation state

- `quality-v3` is research-only and is not connected to operator publication.
- The paired prospective `quality-v2`/`quality-v3` workflow is absent.
- Automatic post-draw handling of VOID/postponed events is incomplete.
- `memory-bank` is stale.
- The `post_draw_attribution` source feature has 23 focused passing tests and is Ruff-clean, but has no CLI, documentation, memory updates, full-suite verification, or commit.
