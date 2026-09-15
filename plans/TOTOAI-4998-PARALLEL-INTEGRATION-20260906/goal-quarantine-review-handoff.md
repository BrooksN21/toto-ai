# GOAL quarantine — handoff to independent review

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Implementation stopped; no owned process. Independent review is now parent-assigned to Leibniz; do not wait or start further work here.

- Exact patch: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/goal-quarantine-implementation.patch`; SHA256 `b463ced484c99b6ff12400329b876d3cdd1f0bb2a3e95d032dc7f621afad3b54`.
- Five paths: goal_api.py, schedule_source_collector.py, test_goal_api_fixture_quarantine.py, portable exact-raw fixture, one knowledge boundary document. Full absolute paths/before-after hashes in `goal-quarantine-implementation-receipt.json` beside this handoff.
- **84 PASS**, **28 new cases** (26 was the intermediate count before two exact saved-raw witness cases; corrected receipt), eight-file Ruff PASS.
- Default strict API and team-history behavior retained; only candidate collector opts into permanent per-fixture quarantine with provenance and continued pagination. Affected targets stay unbound; other candidates retain all existing review/timing/safety requirements.
- Saved seven-page replay: both conflicting fixtures quarantined; execution reached missing offset700. Original capture remains incomplete, not a validated complete feed; no4998 coverage recovery claimed.
- Verification limits: one existing DNS attempt denied; expanded DB test denied SQLite and not claimed passing. No actual network/DB writes or jobs/auth/seed/main-memory changes. No Git/publication.

## Next operational job — only after independent verdict and parent permission
Native fresh collection entrypoint confirmed from CLI source (not executed):

```sh
# cwd /Users/turshevr/toto-ai; precondition: revalidate this exact4998 queue/target.
NEW_OUTPUT="reports/sports-analytics/4998/goal-quarantine-refresh-$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$NEW_OUTPUT" && .venv/bin/python -m toto_ai.cli collect-goal-shadow-input \
  --drawing-id 12102 \
  --queue reports/sports-analytics/4998/goal-auto/captures/20260906T093419081148Z/goal-shadow-queue.json \
  --raw-cache-dir data/raw \
  --output-dir "$NEW_OUTPUT" \
  --env-file .env \
  --request-budget 120
```

This is a fresh standalone immutable capture, not `ensure_goal_probe_input` reuse. It needs actual live-source permission and existing secret handling; never print secrets or backdate capture timestamps. Do not overwrite old goal-auto/current.json or pinned seed. A complete new capture and sufficient team histories must be verified before generating a new sports seed. Current `parallel-sidecar-prepare` reuses the installed wrapper's bound seed: no supported in-place seed rebind established here. Cache refresh/rebinding is separately owned; no plan/consent/job changes authorized by this handoff.

Next checkpoint: parent receives independent verdict. No API refresh before it.
