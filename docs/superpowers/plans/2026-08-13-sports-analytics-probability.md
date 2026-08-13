# Sports Analytics Probability Implementation Plan

> Implementation plan only. All sports outputs remain shadow-only and
> `NOT_ACTIVATED`; this plan does not authorize production integration,
> wagering, remote publication, or external service access.

This plan implements the approved
`docs/superpowers/specs/2026-08-13-sports-analytics-probability-design.md` and
the current shadow-provider/activation constraints in project memory.

## Goal and non-negotiable boundary

Build an auditable provider-neutral sports evidence layer, market baselines,
leakage-safe features, a residual model, and chronological evaluation while
keeping normalized TotoBrief BK as the production control. The candidate may
produce `PASS_REVIEW_REQUIRED`, never `PLAY` or an actionable package, even if
all metrics pass.

- No scraping, unofficial credentials, guessed fixture/team matches, or
  silent provider substitution.
- Every observation stores provider/API identity, source URL or endpoint,
  retrieval time, `as_of`, request fingerprint, payload hash, target/event
  identity, orientation, and coverage/fallback reason.
- TotoBrief BK is the control; TotoBrief Pin is an optional TotoBrief-supplied
  benchmark, not direct Pinnacle access; TotoBrief pool is a crowd/payout
  model, not sports truth.
- Missing features use flags and shrinkage toward BK, never zero-filled fake
  evidence. Aggregate form cannot masquerade as venue evidence.
- Existing package selection, dynamic-bank inputs, settlement, and actionable
  scheduler behavior are unchanged until a separately approved activation.
- No profitability claim is made without the required out-of-sample and
  package-level evidence.

## Existing code to extend

- `src/toto_ai/sports_stats/domain.py`: `SourceEvidence`,
  `FootballEventFeatureSnapshot`, `SportsStatsRunSnapshot`, canonical JSON and
  SHA-256 helpers.
- `src/toto_ai/sports_stats/provider.py`, `api_sports.py`, `collection.py`,
  `operation.py`, and `storage.py`: provider protocol, API-Sports adapter,
  collection/persistence, and `collect_and_store_sports_stats()`.
- `src/toto_ai/sports_stats/features.py`: current `build_team_window()` and
  venue/history feature construction.
- `src/toto_ai/sports_stats/probabilities.py`: current
  `build_shadow_probability_artifact()`,
  `build_shadow_probability_artifact_from_snapshot()`,
  `load_shadow_probability_artifact()`, and
  `write_shadow_probability_artifact()`.
- `src/toto_ai/sports_stats/evaluation.py`: `evaluate_shadow_records()` and
  `write_shadow_evaluation_reports()`; retain hard minimums and fail-closed
  authority validation.
- `src/toto_ai/sports_stats/shadow_operation.py`: current stored-artifact
  orchestration and immutable BK snapshot loading.
- `src/toto_ai/external_odds/`: target/event identity, schedule evidence,
  API-Sports data, coverage, and preparation pins; reuse its identity and
  provenance rules instead of creating a second matcher.
- `src/toto_ai/cli.py`: existing `collect-sports-stats`,
  `sports-probability-shadow`, and `evaluate-sports-probability-shadow`.
- Tests to extend: `tests/test_sports_probability_shadow.py`,
  `tests/test_sports_probability_evaluation.py`,
  `tests/test_sports_stats_domain.py`, `tests/test_sports_stats_collection.py`,
  `tests/test_sports_stats_operation.py`, `tests/test_sports_stats_storage.py`,
  `tests/test_external_event_matching.py`, and the external coverage tests.

Recommended new modules/interfaces:

```python
# src/toto_ai/sports_stats/sources.py
class SportsEvidenceProvider(Protocol): ...
def collect_provider_evidence(..., as_of: datetime) -> SportsStatsRunSnapshot: ...

# src/toto_ai/sports_stats/baselines.py
def build_market_baseline_rows(...): ...
def evaluate_market_baselines(...): ...

# src/toto_ai/sports_stats/model.py
def fit_residual_model(rows, *, train_until: datetime, config): ...
def predict_residual_model(model, row, *, as_of: datetime): ...

# src/toto_ai/sports_stats/walk_forward.py
def evaluate_walk_forward(...): ...
def write_walk_forward_reports(...): ...

# src/toto_ai/sports_stats/package_replay.py
def replay_unchanged_dynamic_bank_packages(...): ...
```

## Stage 0 — Contract fixtures and control preservation

**TDD:** add fixtures and failing contract tests before adding providers or
model code.

1. Create deterministic in-memory 15-event drawing fixtures with frozen
   deadline, target/team orientation, BK triplets, optional Pin triplets,
   pool probabilities, source timestamps, and actual results. Include missing,
   duplicate, reversed, sparse/new-team, future-timestamp, and hash-mutated
   cases.
2. Add tests proving current normalized BK rows are unchanged byte-for-byte
   when sports evidence is absent or shadow mode is enabled. Prove
   `EVInput`/coupon ranking/selection receives no sports probability.
3. Run the new fixture tests and existing sports tests to establish RED for
   each new interface, then implement only domain validators and fixtures.
4. Preserve current `SportsShadowArtifact` schema compatibility or introduce a
   versioned schema with explicit migration rejection; every artifact must
   remain `NOT_ACTIVATED` and content-hash-bound.

## Stage 1 — BK control and free-source coverage audit

**Files:** extend `sports_stats/domain.py`, `provider.py`, `collection.py`,
`operation.py`, `storage.py`; add `sources.py` and tests such as
`tests/test_sports_source_coverage.py`.

1. Write RED tests for provider success, timeout/rate limit, malformed payload,
   unsupported competition, incomplete source, duplicate fixture, ambiguous
   fixture, reversed orientation, and provider fallback. Every one of 15
   events must have an explicit disposition; no event may disappear.
2. Keep API-Sports as the primary supported source. Add provider-neutral
   adapters/evaluators in this order: TheSportsDB free API, football-data.org
   free registered plan, football-data.co.uk historical CSV, and StatsBomb
   Open Data research-only selected competitions. The plan must not require
   live network calls in tests.
3. Use existing target and schedule-evidence identity rules. A fuzzy match can
   be diagnostic only; it cannot authorize a feature row. Reversed fixtures
   retain explicit orientation and cannot provide team/odds/stat identity.
4. Persist source URL/endpoint identity, retrieval timestamp, source `as_of`,
   request fingerprint, payload hash, target fingerprint, provider event ID,
   orientation, feature coverage, and fallback reason. Make storage append-only
   and idempotent for identical canonical input; conflicting bytes fail closed.
5. Add a read-only coverage audit/report CLI (or extend the existing audit
   command) showing coverage by source/sport/competition/drawing and each
   fallback reason. It must never change predictions or package selection.
6. Verify with:

```bash
PYTHONPATH=src .venv/bin/python -m pytest \
  tests/test_sports_source_coverage.py tests/test_sports_stats_collection.py \
  tests/test_external_event_matching.py -q
```

## Stage 2 — Leakage-safe football features

**Files:** extend `src/toto_ai/sports_stats/features.py` and
`domain.py`; add `tests/test_sports_features_leakage.py` and deterministic
feature fixtures.

1. Add RED tests that future results, future standings, post-kickoff injuries,
   changed team identity, reversed orientation, and mutated source hashes are
   rejected or fall back to BK. Test that data exactly at the cutoff follows
   the documented inclusive/exclusive rule consistently.
2. Implement deterministic time-decayed Elo with home advantage and
   competition-strength shrinkage. Define and test initialization, update
   order, decay, sparse history, promoted/new-team flags, and serialization.
3. Implement home/away W-D-L and goals-for/goals-against windows, recent form,
   rest days, pre-kickoff standings/table strength, congestion, and sparse/new
   team flags. Use only source observations strictly before the frozen `as_of`.
4. Preserve venue semantics: home team home history and away team away history
   are separate; aggregate form is diagnostic only. Missing values are
   explicit flags plus sample counts/shrinkage metadata, never zeros that look
   observed.
5. Hash canonical feature payload, normalization statistics, source IDs,
   cutoff, target fingerprint, and feature configuration. Ensure repeated runs
   with the same bytes produce identical features and hashes.
6. Run focused leakage, determinism, orientation, sparse-team, and normalization
   tests before integrating with probability artifacts.

## Stage 3 — Market baselines, including TotoBrief Pin

**Files:** add `src/toto_ai/sports_stats/baselines.py`; extend domain/storage,
`shadow_operation.py`, `evaluation.py`, and CLI; add
`tests/test_sports_market_baselines.py`.

1. Write RED tests for normalized BK control, optional Pin presence, missing
   Pin, invalid Pin, and pool probabilities. Assert Pin is reported as a
   benchmark only and never silently replaces BK; assert pool is labelled
   crowd/payout and never used as sports truth.
2. Parse and preserve the existing TotoBrief Pin fields from the frozen quote
   snapshot. Bind the exact quote/content hash, event order, orientation, and
   `as_of`; do not read mutable current `Quote` rows for OOS predictions.
3. Produce chronological baseline metrics by sport, competition family,
   probability/confidence band, and season for BK, Pin where present, and
   calibrated BK. Use multiclass log loss, Brier, confidence ECE, coverage,
   fallback counts, and validation counts. Calibration is a report artifact,
   not a production change.
4. Add deterministic report JSON/CSV/Markdown with source hashes, row counts,
   missing-Pin counts, calibration configuration, and explicit control labels.
   Mutated or unbound snapshots are blocking, not silently dropped.

## Stage 4 — Leakage-safe residual model in shadow mode

**Files:** add `src/toto_ai/sports_stats/model.py`; extend
`probabilities.py`/`shadow_operation.py`; add
`tests/test_sports_residual_model.py`.

1. Write RED tests for deterministic train/test separation by drawing deadline,
   feature normalization fitted on train only, regularization, missing-feature
   flags, normalization to a valid probability triplet, and artifact hash
   stability. Include a test that a future row cannot enter the training set.
2. Fit the first candidate as regularized multinomial residual correction:

```text
candidate_logits = log(BK probabilities) + fitted sports residuals
```

   Use the project NumPy stack, deterministic solver/seed/config, and no
   standalone sports prior. Near-zero or missing evidence must shrink toward
   BK. Persist coefficients, normalization statistics, training IDs/cutoff,
   feature schema/config, input hashes, and model hash.
3. Extend the shadow artifact to carry BK, Pin/pool benchmark references,
   current venue shadow, candidate residual, conservative ensemble, coverage,
   fallback reason, and `NOT_ACTIVATED`. Keep the existing per-event BK
   fallback for missing identity, timing, provenance, as-of, orientation, pin,
   or chronology.
4. Add CLI support for deterministic training/artifact paths without allowing
   a flag to lower hard data requirements or switch production inputs. A model
   artifact may be written only to the shadow/report area.

## Stage 5 — Walk-forward evaluator and hard activation gate

**Files:** add `walk_forward.py`; extend `evaluation.py`,
`shadow_operation.py`, and CLI; add
`tests/test_sports_probability_walk_forward.py`.

1. Write RED tests proving chronological splits by drawing deadline, no target
   or source leakage, immutable BK snapshot use, exact row/event counts,
   blocking fingerprint/orientation failures, and ordinary sports-history
   missingness falling back to BK with reduced coverage.
2. Evaluate BK control, Pin benchmark where available, calibrated BK, current
   Jeffreys venue shadow, residual model, and conservative BK+sports ensemble.
   Report multiclass log loss, Brier, confidence ECE, sports coverage, fallback
   rate, and validation counts by drawing/sport/competition/confidence band.
3. Enforce non-configurable hard floors of at least 30 complete drawings and
   450 events plus at least 70% sports coverage. A CLI/config value may be
   stricter but never weaker. Require zero leakage/identity/orientation/
   fingerprint failures, strictly lower log loss and Brier than BK, and ECE
   no worse than BK by more than 0.02.
4. Emit `PASS_REVIEW_REQUIRED` only when every predicate passes; otherwise
   emit a typed `PENDING`/`STOP` result. Every artifact remains
   `NOT_ACTIVATED`; no command may write the result into `EVInput`.

## Stage 6 — Unchanged dynamic-bank package replay

**Files:** add `src/toto_ai/sports_stats/package_replay.py`; extend existing EV
backtest/report code only through a read-only adapter; add
`tests/test_sports_probability_package_replay.py`.

1. Write RED tests that replay a frozen drawing set against the existing
   selector with the exact same bank sizes, stakes, package-safety settings,
   candidate universe, probability snapshot/provenance, and deterministic
   streams. Assert BK replay reproduces known package hashes and dynamic-bank
   results.
2. Replay candidate probabilities through the unchanged package selector and
   settlement path. Record P(13+), P(14+), P(15), actual category counts,
   diversity, cost, best hits, payout/ROI when official payouts exist, and
   paper/NO BET outcomes. Do not manually build coupons from reports or expired
   artifacts.
3. Add assertions that sports shadow/residual artifacts cannot alter a
   production scheduler plan or actionable package while `NOT_ACTIVATED`, and
   that selecting the control with the same inputs yields identical coupon
   order/hash.
4. Keep package-level comparison secondary to event metrics and label it
   research evidence; a single drawing cannot establish profitability or
   causality.

## Stage 7 — Prospective shadow operation and review handoff

**Files:** extend `src/toto_ai/sports_stats/operation.py`,
`shadow_operation.py`, `cli.py`, reports, and tests; update memory only after
implementation milestones.

1. Add a prospective command/workflow that captures every new drawing's
   frozen pre-deadline sports evidence and BK/Pin snapshots, writes immutable
   `NOT_ACTIVATED` artifacts, and never mutates the production scheduler.
2. Add restart/idempotency, late-source, provider outage, duplicate, and hash
   conflict tests. Late/future data is rejected or BK fallback; it cannot
   retroactively improve an OOS score.
3. Produce one evaluation manifest binding source/model/feature/config hashes,
   cutoff, drawing IDs, package replay settings, metrics, gate predicates, and
   review status. An independent user-review result is required before any
   future activation proposal.
4. If the full gate passes, the only output is `PASS_REVIEW_REQUIRED` plus a
   separately documented activation proposal with rollback-to-BK. Do not wire
   sports probabilities into `EVInput`, `scheduler.py`, `PLAY`, `.bet-ready`,
   or operator export in this plan.

## Verification and commands

After each stage, run the focused tests and Ruff. At the end run:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
PYTHONPATH=src .venv/bin/python -m ruff check .
PYTHONPATH=src .venv/bin/python -m toto_ai.cli collect-sports-stats --help
PYTHONPATH=src .venv/bin/python -m toto_ai.cli sports-probability-shadow --help
PYTHONPATH=src .venv/bin/python -m toto_ai.cli evaluate-sports-probability-shadow --help
git diff --check
git status --short
```

Acceptance must include provider fallback, exact orientation, ambiguous and
duplicate identity, timestamp leakage, sparse/new teams, deterministic Elo and
training, probability normalization, chronological split, artifact hashes,
BK fallback, Pin benchmark handling, dynamic-bank replay, and unchanged
package selection while not activated. Update `memory-bank/ARCHITECTURE.md`,
`CURRENT_STATE.md`, `DECISIONS.md`, and `ROADMAP.md` only in the later
implementation, after the relevant feature is verified. No source, tests,
specs, memory, push, PR, external transmission, or production activation is
part of this planning task.
