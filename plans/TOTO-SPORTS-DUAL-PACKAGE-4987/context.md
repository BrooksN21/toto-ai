# TOTO-SPORTS-DUAL-PACKAGE-4987 — context handoff

## Scope and repository state

- Context collection only; no implementation, VCS publication, or external services were used.
- Read `/Users/turshevr/toto-ai/AGENTS.md` and every file in `/Users/turshevr/toto-ai/memory-bank/` (`ARCHITECTURE.md`, `CURRENT_STATE.md`, `DATA_NOTES.md`, `DECISIONS.md`, `PROJECT_OVERVIEW.md`, `PROJECT_PHILOSOPHY.md`, `ROADMAP.md`, `TOOLING_POLICY.md`).
- Initial bounded status check, `git status --short --untracked-files=no`, showed no tracked worktree changes.
- Durable project rule: production package probabilities remain TotoBrief BK 15x3. Sports evidence and sports-derived probabilities are audit/shadow inputs only and have no scheduler/operator authority. TotoBrief pool shares are crowd/EV inputs, not sports-performance evidence.

## Drawing 4987 evidence

### Existing API-Sports audit snapshot

`reports/sports-stats/4987/4987/sports_stats_4987_2ec71b54485c.json` is an `AUDIT ONLY` / `package_influence: NONE` / `fallback: MARKET ONLY` artifact for drawing id `12068`, number `4987`, fingerprint `94a3e769330d4c7779fd22f2fe1ad95d4e676a3a33fb592de22ffc49fd26e063`.

- Captured/as-of: `2026-08-26T09:48:11Z`; TotoBrief deadline: `2026-08-26T18:45:00Z`; requested history: 10.
- Status `failed`: 0 complete, 0 partial, 15 missing, 0 unsupported, 0 provider requests/cache hits.
- Every event is missing with `preparation_not_ready`; no provider fixture/team ids or source evidence were attached. This snapshot therefore cannot supply sports probabilities.

### GOAL canary and full probe

`reports/sports-analytics/4987/goal-canary/` shows that GOAL fixture, team-statistics, team-results, and H2H-statistics endpoints returned HTTP 200 for the sampled event. Predictions and odds returned HTTP 403 `PLAN_CAPABILITY_DENIED` (`canAccessPredictions` / `canAccessOdds`); standings returned HTTP 404 `STANDINGS_NOT_FOUND`.

`reports/sports-analytics/4987/goal-full-probe/coverage-summary.json` is schema 1, `PAPER_ONLY_COVERAGE_PROBE`, captured `2026-08-26T10:00:06.011724Z`:

- 15/15 events are marked `sports_eligible`; `package_influence: NONE`; `automatic_wagering: false`.
- There are 30 successful HTTP-200 team-results snapshots, two per event. Summary totals: 295 eligible completed rows and 140 venue-matched rows; 25 windows contain 10 rows and five contain 9; venue counts range 2–7. Quota remaining decreases from 622 to 593.
- All returned history kickoffs precede their target event kickoff.
- Raw snapshots contain 295 `FINISHED`, three `AFTER_PEN`, and two `AFTER_ET` rows. The probe summary excludes the latter five, whereas the current API-Sports feature builder accepts FT/AET/PEN terminal statuses. This is an artifact-specific status/eligibility mismatch to resolve before treating GOAL data as equivalent to the current provider contract.
- The probe points to `reports/canary/goal-api-4987/output-v3/schedule-source-candidates.json`. That source report is schema 2, `CANDIDATES_ONLY_NOT_LEDGER_ELIGIBLE`, captured `2026-08-25T16:09:17Z`: GOAL matched 15 events but produced only 3 candidates and 12 timing conflicts; `ledger_mutated: false`. It is evidence/probe output, not scheduler ledger authority.
- No current source module references the `goal-canary` or `goal-full-probe` artifacts, and they are not persisted as a `SportsStatsRunSnapshot`. The current shadow loader therefore cannot consume them.

## Current sports/shadow code paths

- `src/toto_ai/sports_stats/collection.py`: requires exactly 15 ordered preparation pins bound to the target fingerprint. A pin is provider-available only with matching provider name and fixture/home/away provider ids. Missing pins fail closed to `preparation_not_ready`. Collection validates fixture identity/orientation/start, chronology, and per-team windows.
- `src/toto_ai/sports_stats/api_sports.py`, `operation.py`: the only implemented collection adapter/CLI provider is `api-sports`; prospective collection may use API-Sports, while historical mode is local-cache-only. `collect-sports-stats` explicitly rejects any other provider.
- `src/toto_ai/sports_stats/features.py`: builds newest completed pre-cutoff team windows; API-Sports terminal statuses FT/AET/PEN are accepted. It computes overall and home/away W-D-L, goals, PPG, last-five points, and rest.
- `src/toto_ai/sports_stats/storage.py`: stores immutable content-hashed run/event snapshots. `load_latest_eligible_snapshot` defaults to provider `api-sports` and requires exact drawing/fingerprint and pre-as-of chronology.
- `src/toto_ai/sports_stats/probabilities.py`: shadow status is always `NOT_ACTIVATED`. Invalid/missing evidence falls back exactly to BK. The sports row uses Jeffreys-smoothed venue-only W-D-L from the home team's home split and away team's away split; aggregate form/goals/standings remain diagnostics. Blend weight is matched venue sample count divided by matched count plus twice requested history size.
- `src/toto_ai/sports_stats/shadow_operation.py`: builds from an immutable raw TotoBrief detail plus the latest eligible stored API-Sports snapshot; it has no GOAL probe import path.
- `src/toto_ai/sports_stats/evaluation.py`: chronological OOS gate requires at least 30 drawings/450 events, at least 70% sports coverage, strict blend improvement over BK in both log loss and Brier, ECE no worse than BK plus tolerance (maximum 0.02), and zero validation/fingerprint/leakage failures. Even a pass is review-required; output remains `NOT_ACTIVATED` and production activation requires an architecture change.
- CLI commands in `src/toto_ai/cli.py`: `collect-sports-stats`, `sports-probability-shadow`, `compare-preliminary-packages`, and `evaluate-sports-probability-shadow` preserve audit/shadow-only status.

## Package-comparison paths

- `src/toto_ai/sports_stats/preliminary_comparison.py` compares equal-budget BK-control and sports-shadow candidate packages from one cached TotoBrief detail and one validated shadow artifact. It computes overlap, exposure differences, same-model and cross-model quality diagnostics. Output is `PAPER_ONLY_NOT_ACTIVATED`, `real_money_actionable: false`, and `automatic_wagering: false`. It is not bound to a scheduler plan or operational cutoff.
- `src/toto_ai/optimizer/strategy_comparison.py` defines a separate immutable `FrozenStrategyInput` for equal-input research over the same pre-deadline BK/crowd rows, bank, and stake. Its four adapters are current EV/crowd, BK-probability-only, TotoBrief-style Cover-13, and Cover-14; it does not include a sports-shadow adapter.
- `src/toto_ai/optimizer/strategy_execution.py` binds that four-way comparison to a validated scheduler `final-input.json`, schema-v7 scheduler plan, and selection provenance. `strategy_reports.py` labels every output `RESEARCH/PAPER`, `actionable: false`, `automatic_wagering: false`. CLI command: `compare-package-strategies`.
- Therefore the two existing comparison surfaces are complementary but distinct: the sports dual comparison is not scheduler-bound, while the scheduler-bound equal-input comparison has no sports candidate.

## Scheduler/operator boundary for drawing 4987

`reports/rehearsal/evening-4987-20260826T184500Z/scheduler-plan.json` is schema 7, plan `f28e5483bcea337a`, bank/stake `4980/30` (166-coupon capacity), with quality-v2 release protocol `quality-v2-paper-only-v1`.

- TotoBrief identity deadline is `2026-08-26T18:45:00Z`; independently confirmed earliest kickoff/operational cutoff is `2026-08-26T15:45:00Z`; hard T-10 is `2026-08-26T15:35:00Z`. `reports/canary/goal-api-4987/conservative-cutoff.json` binds the tightened cutoff to event order 10 (event 11) and the GOAL source report.
- At inspection, the plan output contained the plan/launch files, an experimental manual-release authorization, and training-package artifacts only. It had no scheduler state, final `operator-result.json`, `.bet-ready`, `.no-bet`, `.failed`, or `paper-package-result.json`.
- The training result is non-actionable (`TRAINING ONLY / DO NOT WAGER`, `actionable: false`, `operator_export: false`, `automatic_wagering: false`) despite a structurally selected 166-coupon/4980-cost candidate. Coupon payloads were not inspected or reproduced.
- The authorization is bound to this exact plan, expires at T-10, records risk acknowledged while `profitability_proven: false` and `automatic_wagering: false`; it does not itself create an operator package. In code it can permit only a final-phase, pinned-revalidated, structurally and safety-approved fresh candidate to become PLAY.
- `src/toto_ai/runner/scheduler.py` keeps paper/LKG artifacts non-actionable. `_publish_actionable_operator_result` and `_validated_actionable_operator_upload` require a scheduler-owned `FINAL_FRESH` PLAY, matching run status, `.bet-ready` marker, package/archive hashes, plan identity, bank/stake/count, durable DB archive, and pre-T-10 chronology. `export_operator_package` revalidates all bindings before and after writing; T-10 expiration removes the upload surface and rewrites operator state to NO BET while retaining audit evidence. Automatic wagering remains false.
- CLI boundaries: `operator-export` exposes only that validated current operator surface; `paper-package-show`/paper export are explicitly `PAPER / NO BET / DO NOT WAGER` and are not substitutes.

## Downstream constraints

1. Do not treat 15/15 GOAL probe coverage as an activated probability source: there is no adapter, canonical persisted sports snapshot, or shadow-artifact binding for it.
2. Any GOAL integration must define provider/status semantics and reproduce the existing identity, chronology, venue-window, content-hash, fallback, and leakage checks; the current `FINISHED` versus AFTER_ET/AFTER_PEN mismatch is concrete evidence that direct reuse is unsafe.
3. A sports/BK dual comparison must use immutable equal inputs and remain research-only. It must not write scheduler state, operator artifacts, betting markers, or an upload package.
4. Scheduler package identity uses the operational cutoff, not merely TotoBrief `ended_at`. Existing sports collection/preliminary comparison checks are based on the drawing deadline/as-of and do not by themselves satisfy the scheduler/operator boundary.
5. Do not claim profitability or activation without the defined historical OOS gate and explicit architecture decision.
