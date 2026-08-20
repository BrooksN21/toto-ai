# TotoAI implementation context: paper package, post-draw review, sports analytics

## Scope and constraints

- Repository: `/Users/turshevr/toto-ai` only.
- This document is context handoff only. No code or other project files were changed for this task.
- Do not use Yandex/Arcadia/Gena/internal tools or services. Use local repository commands only unless a later task explicitly authorizes public research/API access.
- Do not push, create PRs, publish, place bets, or enable automatic wagering.
- `memory-bank/` is the durable project context. Current relevant memory is in `ARCHITECTURE.md`, `CURRENT_STATE.md`, `DECISIONS.md`, `ROADMAP.md`, and `TOOLING_POLICY.md`.
- Existing unrelated worktree changes and untracked historical plan/data directories must be preserved.

## Approved designs

Primary specs:

- `docs/superpowers/specs/2026-08-13-paper-package-and-post-draw-review-design.md`
- `docs/superpowers/specs/2026-08-13-sports-analytics-probability-design.md`

The designs are approved. The package/output format correction below is mandatory and supersedes any earlier informal format.

## Current product boundary

The system is a non-betting TotoAI research/operator-assistance project. It calculates packages, validates and archives them, and exposes a manual upload artifact only when the scheduler's strict current `PLAY` boundary permits it. It never places a wager automatically.

Current production probability input is the normalized TotoBrief BK matrix. TotoBrief pool is a crowd/payout/EV input, not a sports truth source. Existing API-Sports identity, schedule, form/goals/standings evidence is currently audit/eligibility evidence and does not change `EVInput` or coupon ranking. TotoBrief Pin fields may exist in stored quotes and are a benchmark supplied by TotoBrief, not direct Pinnacle access.

Quality-v2 is structurally evaluated but fail-closed `NO BET / TRAINING-PAPER`; no profitability is proven. Sports probability code is shadow-only and must remain `NOT_ACTIVATED` until the documented chronological gate passes and a separately approved activation change is made.

## Exact paper package contract

Every terminal scheduler calculation must expose one final package summary, including terminal `NO BET`.

There are two distinct artifacts:

1. Research/source package CSV: existing `rank,coupon,gross_ev,net_ev` evidence. It is not a BaltBet upload payload.
2. Paper display/download text artifact: exact BaltBet text-editor syntax.

The copyable paper payload must satisfy all of the following:

- one coupon per line;
- no header, Markdown, rank, EV columns, diagnostics, or warning text in the payload;
- each line is exactly:

  `<stake>; <outcome1>; <outcome2>; ...; <outcome15>`

  Example:

  `30; 1; X; 2; 1; 1; 2; X; 2; 1; X; 2; 2; 1; X; 2`

- delimiter is the literal `; `;
- first field is configured stake;
- exactly 15 outcome fields follow;
- each outcome is one of `1`, `X`, `2`;
- UTF-8, LF line endings, final newline, no CR/NUL;
- coupon order equals the validated source package order;
- all lines/coupons are unique;
- line count equals `selected_count`;
- implied cost equals `selected_count * stake`.

`PAPER / NO BET / DO NOT WAGER` and other warnings must be emitted in the surrounding CLI/status response (preferably stderr for a clean stdout mode), never inside the copyable payload. A paper artifact is non-actionable and must never be exposed through `.bet-ready` or `operator-export`.

The requested read-only command is `paper-package-show --plan ...`. It must validate all plan/package/hash/identity bindings, print the terminal summary and warning separately, and write only exact coupon lines to stdout or an explicit output file. It must not select or alter coupons and must reject expired/foreign/tampered/unbound artifacts.

A verified historical example already exists outside source code:

`reports/rehearsal/evening-4974-recovery-20260813T1330Z/paper-package-4974-baltbet-format.txt`

It contains 166 unique lines and an implied cost of 4,980. It is historical PAPER/NO BET evidence, not a current actionable package and must not be recommended for wagering.

## Scheduler implementation facts

Main scheduler module:

- `src/toto_ai/runner/scheduler.py`

Important existing functions and boundaries:

- `_persist_last_known_good(...)` validates source `package.csv`, renders existing BaltBet text with `_render_baltbet_upload`, writes immutable checkpoint files under `last-known-good/checkpoints/`, and writes `last-known-good/current.json`.
- `_write_operator_result(...)` writes a validated LKG result with `decision=NO BET`, `actionable=false` for degraded/research states.
- `_write_operator_no_bet(...)` writes coupon-free `operator-result.json` for a package-free NO BET.
- `_publish_actionable_operator_result(...)` creates the actionable `baltbet-upload.txt` and hash-bound `operator-result.json` only for verified PLAY before the publication cutoff.
- `_remove_actionable_publication_artifacts(...)` removes `package.csv`, `package-archive.json`, and `baltbet-upload.txt` from the actionable run surface at/after T-10 and removes an actionable operator result. Paper artifact must survive this cleanup.
- `_validate_baltbet_upload(...)` already enforces UTF-8/LF, `stake; <15 outcomes>`, outcome alphabet, count, uniqueness, cost, and exact coupon order.
- `_render_baltbet_upload(...)` already emits the required line shape: `f"{stake}; " + "; ".join(coupon)` plus a final newline.
- `_validate_no_bet_manifest(...)` accepts `paper_coupons` for a structurally valid NO BET runner manifest, but current terminal publication does not yet expose a stable paper-facing pointer/text artifact as specified.
- Runner manifest validation can return `SchedulerPhaseResult.candidate_package(...)` for a structurally valid paper candidate even though top-level decision remains NO BET. This is the source to preserve as paper evidence.
- Scheduler plan/schema is v6 with publication lead T-10 and strict provenance/ledger/schedule bindings. Do not weaken these gates or turn paper into PLAY.

Expected paper additions, guided by the approved spec:

- durable `paper-package-result.json` binding drawing id/number, plan id, decision, reason, `actionable=false`, source CSV path/hash when present, paper text path/hash, coupon count, stake, selected cost, probability-input hash, provenance, and completion time;
- durable exact-format paper text generated only from the validated source package;
- package-free NO BET result when no valid package was computed;
- persistence must be atomic, hash-bound, identity-bound, and safe against symlinks/tampering;
- T-10 cleanup must remove only actionable operator surfaces, not paper text/result or audit source evidence.

Relevant scheduler tests:

- `tests/test_scheduler_atomic_final_end_to_end.py`
- `tests/test_scheduler_last_known_good.py`
- `tests/test_scheduler_operational_artifacts.py`
- other `tests/test_scheduler_*.py`

Existing tests already cover operator PLAY/NO BET boundaries, LKG fallback, T-10 expiration, package validation, marker publication, and source/hash integrity. New tests must add paper visibility for computed and package-free NO BET, exact text syntax/stdout, T-10 preservation, and tamper rejection without changing existing actionable behavior.

## Finished-drawing lifecycle implementation facts

Main module:

- `src/toto_ai/operations/finished_draw.py`

Data classes:

- `ResultSync`: immutable result snapshot metadata, actual string, VOID orders, completeness.
- `PackageArchive`: immutable archived package identity/hash/cost/provenance.
- `Settlement`: settlement hash, actual result, VOID orders, hit distribution, best hits/ranks, category counts, misses, payout/ROI status.
- `PostDrawRetryConfig`: bounded retry/backoff parameters.
- `PostDrawState`: current schema-1 state with `pending|complete|failed`, drawing/package/result/settlement hashes, attempts, reason, and state hash.

Important functions:

- `sync_finished_drawing(...)`: fetches one exact `/drawing-info/{id}`, normalizes 15 events, preserves RAW/result snapshots, accepts explicit reviewed VOID only under existing lifecycle contract, and writes an immutable result snapshot.
- `archive_package(...)` / related archive helpers: establish immutable package archive and identity.
- `settle_archived_package(...)`: requires a complete 15-event snapshot and exact package identity, then computes hits/misses/VOID handling and payout/ROI status idempotently.
- `_compute_settlement(...)`: counts a VOID event as a hit for every coupon, excludes VOID from fixed/zero-exposure misses, and records `return_status=unknown_until_payouts` if official payments are absent.
- `run_post_draw(...)` / `_run_post_draw_locked(...)`: lock-protected bounded retry loop that reuses `sync_finished_drawing` and `settle_archived_package`; it currently expects a package file and writes `PostDrawState`.
- `prepare_post_draw_scheduler_artifacts(...)`: currently generates one launchd wrapper/plist whose first run is `ended_at + 1 second`, not the approved next-calendar-day 12:00 plus 3-hour cadence.

Current post-draw gaps to implement without a second settlement algorithm:

- automatically create a post-draw plan for every terminal scheduler decision, bound to final paper/actionable package identity/hash (or package-free NO BET identity);
- first attempt at 12:00 Europe/Moscow on the next calendar day after the drawing deadline;
- retries at 15:00, 18:00, 21:00, 00:00 and then every three hours until bounded expiry;
- incomplete results persist `PENDING_RESULTS`; postponed events remain pending unless authoritative VOID status is present and accepted;
- transport failures persist typed error and retry without mutating prior snapshots;
- identity/hash/terminal conflicts fail closed as `REVIEW_BLOCKED_INTEGRITY`;
- idempotency must remain intact;
- notification failure is advisory and must not alter settlement/retry.

Review request required after settlement reaches 15/15:

`review-request.json` must contain drawing/package identity, settlement hash, best coupon hits, category 13/14/15 counts, fixed misses, zero-exposure misses, VOID orders, known return/ROI status when available, `status=AWAITING_USER_REVIEW`, and `requested_at`.

User transitions are explicit:

- accept: `REVIEW_REQUESTED`;
- decline: `REVIEW_SKIPPED`;
- completed immutable Markdown postmortem: `REVIEW_COMPLETE` plus path/hash.

No state may be silently marked reviewed. On the next project interaction, status checks must surface unacknowledged requests and ask: `Разбираем пакет тиража N?`

Postmortem must compare actual result/VOID, best coupon/hit distribution, event exposure, BK/pool/Pin/sports-shadow/selected probabilities, fixed and zero-exposure misses, estimated EV versus official payout, and concrete errors without claiming causal certainty from one drawing.

Relevant lifecycle tests:

- `tests/test_finished_lifecycle.py`
- `tests/test_collector_lifecycle_v1.py`
- `tests/test_offline_repair_classification_idempotency_v1.py`

Existing tests include complete/partial result retries, reviewed VOID settlement, exact identity, API failure, idempotency, tamper rejection, concurrent settlement, and launchd artifact generation. New tests should target the approved cadence and review-request state transitions.

## CLI facts

Main CLI:

- `src/toto_ai/cli.py`

Existing relevant commands:

- `sync-finished-results`
- `settle-drawing`
- `archive-package`
- `post-draw-run`
- `post-draw-plan`
- `scheduler-plan`
- `scheduler-execute`
- `operator-export`
- `run-drawing`
- `morning-dispatch`
- `sports-probability-shadow`
- `evaluate-sports-probability-shadow`
- sports collection/audit commands around `collect-sports-stats` and external odds.

The new paper command should be read-only and should not reuse `operator-export` because that command is intentionally actionable-only and rejects NO BET/research/LKG/expired artifacts. The post-draw user-review acknowledgement/status interface needs to be explicit and machine-readable; avoid implicit “reviewed” state.

## Sports analytics implementation facts

Relevant source areas:

- `src/toto_ai/sports_stats/` for current sports feature/probability/evaluation code;
- `src/toto_ai/external_odds/` for external odds/coverage/preparation;
- `src/toto_ai/cli.py` for sports commands;
- `memory-bank/ARCHITECTURE.md` for the current shadow provider and activation gate.

Current sports-shadow behavior:

- experimental Jeffreys-smoothed venue-only W-D-L estimate;
- home team's home record plus away team's away record only;
- aggregate W-D-L is diagnostic and never substituted for venue evidence;
- event-level BK fallback when identity, timing, provenance, as-of, orientation, pin, or source chronology cannot be proven;
- outputs content-bound `NOT_ACTIVATED` artifact;
- sports-shadow is not connected to EV/package selection.

Approved source hierarchy:

1. existing API-Sports for supported identity/result/venue form/goals/rest/standings;
2. TheSportsDB free API as evaluated fallback, with incomplete/rate-limited coverage explicit;
3. football-data.org free registered plan where competition coverage exists;
4. football-data.co.uk public CSV historical backfill;
5. StatsBomb Open Data research-only selected competitions.

For every external observation, preserve source URL/API identity, retrieval time, as-of boundary, request fingerprint, payload hash, and coverage. No scraping, unofficial credentials, guessed fixture/team matching, or silent provider substitution.

Market baselines:

- normalized TotoBrief BK = production control;
- TotoBrief Pin = optional benchmark when present, never silently substituted;
- TotoBrief pool = crowd/payout model, not sports truth.

Approved leakage-safe football features:

- time-decayed Elo with home advantage/competition shrinkage;
- home/away W-D-L and goals windows;
- recent form/rest;
- pre-kickoff table strength;
- congestion;
- promoted/new-team/sparse-history flags;
- timestamped public/licensed injuries/lineups only when identity matched.

Missing features must be represented by flags/shrinkage to BK, never zero-filled as real evidence. First trained candidate is regularized multinomial residual correction:

`candidate_logits = log(BK probabilities) + fitted sports residuals`

Training must be deterministic, hash-bound, and time-split. Evaluate walk-forward by drawing deadline against BK control, Pin benchmark where present, calibrated BK, current venue shadow, residual model, and conservative ensemble using log loss, Brier, confidence ECE, coverage/fallback, plus unchanged dynamic-bank package and settlement outcomes.

Activation gate: at least 30 complete drawings/450 events, >=70% sports coverage, zero leakage/identity/orientation/fingerprint failures, strictly lower log loss and Brier than BK, ECE no worse than BK by >0.02, no material package-category degradation at registered dynamic banks, and independent user review. A pass is only `PASS_REVIEW_REQUIRED`; production remains `NOT_ACTIVATED` until separately approved.

Existing sports tests and commands must be extended rather than bypassed. Important required tests: provider fallback, ambiguous/duplicate fixture identity, orientation, timestamp leakage, sparse/new teams, deterministic Elo/training, normalization, walk-forward separation, artifact hashes, BK fallback, dynamic banks, and unchanged package selection while not activated.

## Required implementation order and safety notes

1. Implement paper artifact rendering/validation and scheduler persistence first. Keep source CSV and exact BaltBet text separate; test pure renderer before wiring it into scheduler.
2. Implement post-draw schedule/state/review request using existing synchronization/archive/settlement functions. Do not duplicate settlement logic.
3. Add lifecycle/status integration that surfaces unacknowledged review requests.
4. Only then implement sports source coverage/baselines/features. Keep all sports outputs shadow-only until the activation gate.
5. After each feature update the relevant memory-bank file before considering the feature complete; run focused tests and Ruff, then the full suite as practical.
6. Never manually synthesize an operator package from a research report or expired artifact. Operator-facing coupons may only come from the current scheduler-owned `operator-result.json` before its bound T-10 deadline. Paper/NO BET artifacts are for inspection and learning only.

## Current repository state and outstanding changes

At context-collection time, local Git status includes pre-existing modifications:

- modified `docs/superpowers/specs/2026-08-13-paper-package-and-post-draw-review-design.md` (package-format correction is present);
- modified `memory-bank/CURRENT_STATE.md`;
- modified `memory-bank/DECISIONS.md`;
- unrelated untracked historical/runtime directories under `data/reviewed-schedule/4964/` and `plans/`.

Do not reset, clean, stage, commit, or otherwise alter those files during context-only work. This context file is the only file created by this task.
