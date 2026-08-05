# Hybrid Package Program

Status: approved for staged implementation
Plan date: 2026-07-23
Main context: `plans/hybrid-package-program/context.md`

## 1. Goal

Build one auditable package-generation program that, for every eligible
BaltBet drawing, produces and compares three strategies under the same dynamic
bank:

1. **Cover** — prioritize an explicit brief and a conditional category
   guarantee verified by exact Hamming-distance coverage.
2. **EV** — retain the existing exact monetary-EV ranking as a separately
   labelled high-variance strategy.
3. **Hybrid** — combine calibrated outcome probabilities, category-hit
   probability, Cover/Hamming coverage, modeled EV, and explicit
   diversity/concentration constraints.

The goal is to maximize the probability of useful wins and expected value
under the operator's bank. The project does not promise profit, a payout, or an
unconditional category hit.

## 2. Non-negotiable definitions

- A drawing has exactly 15 ordered events and each coupon has exactly one
  `1/X/2` outcome per event.
- The coupon stake defaults to 30 RUB and remains configurable.
- A bank is any positive integer multiple of the stake. No production or
  research algorithm may hard-code 4980 RUB.
- Category 15 means exact match, category 14 means at most one Hamming error,
  and category 13 means at most two Hamming errors.
- A Cover guarantee is conditional on all 15 actual outcomes belonging to the
  selected brief. It is not a profit guarantee.
- Probability quality, brief containment, package coverage, modeled EV, and
  observed profit are separate measurements.
- `gross_ev` and `net_ev` remain modeled quantities until lawful actual payout
  data is available.
- Market probabilities remain the prior/fallback. Sports statistics may
  modify them only through a calibrated, time-valid, leakage-free model.
- Every missing source, stale source, unresolved event, failed result refresh,
  and unavailable payout must remain explicit.
- No automatic BaltBet account access or bet placement will be implemented.
  The operator uploads a published package manually.

## 3. Reusable TotoBrief ideas

The program will reuse the strongest general ideas behind TotoBrief without
pretending that an EV-ranked list is a Cover system:

- an explicit brief showing allowed outcomes for each event;
- an explicitly selected category target;
- a compact package rather than an unexplained list of rows;
- exact verification of the conditional Hamming guarantee;
- visible full-brief size, selected coupon count, cost, coverage rate, and
  worst minimum distance;
- a clear distinction between the brief and the generated coupon package;
- deterministic export that can be independently re-verified.

The project will additionally expose probabilities, concentration, modeled
category-hit probabilities, EV assumptions, provenance, and post-draw results.

## 4. Target architecture

```text
Morning synchronization and exact event preparation
        |
        +--> immutable market snapshot
        +--> immutable sports-statistics snapshot
        +--> provider/missing-data provenance
        |
        v
Calibrated event probability interface
  p_market prior + p_sports evidence -> p_final
        |
        +--> Cover strategy
        +--> EV strategy
        +--> Hybrid strategy
        |
        v
Common package audit and strategy comparison
  probability + EV + Hamming coverage + concentration + cost
        |
        v
Evening final revalidation and atomic publication
  manual upload only
        |
        v
Immutable prospective package ledger
        |
        v
Post-draw result/payout synchronization and settlement
        |
        v
Expected-vs-actual reports, backtests, and prospective gates
```

## 5. Common probability contract

Each event must have one immutable probability record before package
generation:

```text
EventProbabilitySnapshot
  schema_version
  drawing_id
  drawing_number
  drawing_fingerprint
  event_id
  event_order
  observed_at
  valid_as_of
  generated_at
  market_source
  market_probability_1/x/2
  sports_source
  sports_feature_snapshot_id | null
  sports_probability_1/x/2 | null
  blend_model_id
  blend_model_hash
  final_probability_1/x/2
  calibration_status
  fallback_reason | null
  provenance_hash
```

Rules:

- all triplets are finite, non-negative, normalized, and preserve TotoBrief
  home/away orientation;
- input timestamps must precede the drawing package cutoff;
- final probability is never silently copied or modified;
- a missing or ineligible sports model falls back explicitly to the market
  prior;
- changing source, model, timestamp, or calibration status creates a new
  snapshot;
- results are not accessible to probability generation.

## 6. Strategy contracts

### 6.1 Cover

Inputs:

- final event probabilities;
- dynamic bank/stake;
- target category;
- brief-building policy and its version.

Behavior:

1. Construct one or more probability-aware brief candidates.
2. Generate compact packages through the existing Cover Engine.
3. Run the independent exact streaming distance audit.
4. Reject any package whose claimed guarantee does not verify.
5. Rank feasible packages by the approved Cover objective while retaining
   brief-containment probability and cost.

Required output:

- explicit brief;
- full brief variants;
- target category;
- selected coupons and cost;
- exact coverage rate;
- worst minimum Hamming distance;
- conditional guarantee pass/fail;
- modeled probability that all actual outcomes lie inside the brief.

### 6.2 EV

The existing exact full-space EV strategy remains available and separately
labelled.

Required additions:

- strategy metadata;
- common concentration and coverage audit;
- no implication that a derived union brief is a Cover guarantee;
- explicit warning when one or more low-probability outcomes are fixed or
  nearly fixed across the package.

### 6.3 Hybrid

The Hybrid objective is multi-component. It must combine:

- joint probability mass under calibrated final probabilities;
- modeled probability of at least 9, 13, 14, and 15 hits;
- exact or sampled scenario coverage with Hamming-distance evidence;
- modeled monetary EV;
- diversity and concentration constraints;
- package cost under the dynamic bank.

Initial concentration metrics:

- outcome frequency per event;
- maximum event/outcome share;
- number of fixed events;
- number of near-fixed events at configurable thresholds;
- event-level entropy/effective outcome count;
- minimum, median, and mean pairwise Hamming distance;
- unique-coupon count;
- union-brief size;
- exact conditional Cover results for categories 13/14/15.

Initial hard safety constraints must be configuration-driven and validated
before use. They may include:

- no duplicate coupon;
- no unreported fixed event;
- a maximum number of fixed/near-fixed events;
- a probability floor for an outcome fixed across all coupons;
- a minimum package diversity;
- no false category-guarantee label.

Weights and limits are hypotheses, not truths. They must be selected on a
development window, frozen, then tested on untouched/prospective drawings.
They must not be tuned on the old sealed BK-only holdout.

## 7. Sports-statistics layer

### 7.1 Provider boundary

Add a provider-neutral interface for lawful, official, or reputable
pre-match statistics. Provider-specific transport must remain behind that
interface.

Minimum provider capabilities:

- teams, competition, season, and fixture identity;
- completed match results available before the target event;
- standings and home/away splits when supplied;
- team form and rest/calendar inputs derivable without future data;
- lineups, injuries, suspensions, xG, shots, or other advanced fields only
  when the provider lawfully and reliably supplies them.

Football and hockey require separate schemas and models. Unsupported sports
fall back to market probabilities.

### 7.2 Collection lifecycle

- Morning collection freezes the available feature snapshot and provider
  provenance.
- Historical backfill uses the same canonical records and as-of rules.
- Evening generation may refresh allowed data, but it must not depend on a
  last-minute provider request to remain operable.
- A morning cache miss may be retried before the deadline; an evening failure
  uses the last eligible frozen snapshot or explicit market-only fallback.
- Stale, conflicting, ambiguous, or future-dated data cannot enter a PLAY
  package.

### 7.3 Model and calibration

The sports model must be evaluated against the market prior with chronological
splits and no future leakage.

Required metrics:

- multiclass log loss;
- Brier score;
- expected calibration error and reliability tables;
- per-sport and material per-league sample sizes;
- coverage/fallback rate;
- comparison with unmodified market probabilities.

The initial blend is conceptually:

```text
p_final = calibrated_blend(p_market, p_sports, availability, model_version)
```

The exact blend is not approved until backtests show that it is at least
calibrated and does not materially degrade the market baseline. A failed or
insufficient gate keeps sports evidence audit-only.

## 8. Prospective package and settlement data model

Use additive, migration-safe schemas. Historical tables must not be rewritten.

### 8.1 Package archive

```text
package_runs
  package_run_id
  schema_version
  drawing_id / drawing_number / drawing_fingerprint
  phase: morning | fallback | final | manual_research
  strategy: cover | ev | hybrid | top_probability
  recommendation_status: candidate | recommended | no_bet
  target_category | null
  requested_bank / effective_bank / used_bank / stake
  probability_snapshot_hash
  pool_snapshot_hash
  sports_snapshot_hash | null
  algorithm_version / config_hash / code_version
  generated_at / cutoff_at
  package_hash
  coupon_count
  publication_status
  failure_reason | null
```

```text
package_coupons
  package_run_id
  coupon_order
  coupon
  modeled_probability
  gross_ev | null
  net_ev | null
```

```text
package_audits
  package_run_id
  union_brief
  union_brief_variant_count
  event_frequency_json
  fixed_event_count
  near_fixed_event_count
  hamming_metrics_json
  category_coverage_json
  category_probability_json
  concentration_warnings_json
  audit_hash
```

Uniqueness/idempotency:

- `package_run_id` is content/provenance bound;
- identical retries are idempotent;
- changed inputs/configuration produce a new run;
- coupon order and package hash are canonical;
- archived rows are append-only.

### 8.2 Result and settlement records

```text
drawing_result_snapshots
  result_snapshot_id
  drawing_id / drawing_fingerprint
  fetched_at
  completion_status
  actual_result_15 | null
  result_source_hash
  payout_source
  payout_payload_hash | null
  missing_fields_json
```

```text
package_settlements
  settlement_id
  package_run_id
  result_snapshot_id
  settled_at
  best_hits
  category_9_count ... category_15_count
  winning_coupon_orders_json
  package_cost
  actual_payout | null
  net_profit | null
  observed_roi | null
  expected_metrics_snapshot_json
  settlement_status
  unavailable_reason | null
  settlement_hash
```

Rules:

- every archived package is settled after an authoritative complete result;
- cost and hit counts are always computed when the 15 outcomes exist;
- payout/profit/ROI stay null unless lawful actual payouts are available or
  explicitly entered and validated by the operator;
- settlement is immutable and idempotent;
- a corrected official result creates a new result snapshot and a superseding
  settlement record, never an overwrite;
- missing data and repeated refresh failures are visible in reports and
  scheduler status.

## 9. CLI and report contracts

Planned commands:

```text
package-audit
  --drawing-id/--open
  --package
  --strategy
  --bank
  --stake
  [--target-category]
```

Produces deterministic JSON/CSV/Markdown with strategy metadata, event outcome
frequencies, union brief, Hamming/coverage audit, concentration warnings, cost,
and modeled category probabilities when inputs are available.

```text
generate-strategies --open --bank N --stake 30
  [--cover-category 13|14]
  [--recommendation-policy VERSION]
```

Produces Cover, EV, and Hybrid candidate packages plus one comparison report.
It never submits a bet.

```text
collect-sports-stats --drawing-id/--open
backfill-sports-stats --from ... --to ...
build-probabilities --drawing-id/--open --as-of ...
```

All outputs bind source timestamps, model/config hashes, and fallback reasons.

```text
settle-drawing --drawing-id/--drawing-number
  [--actual-payout-file OPERATOR_FILE]
  [--force-result-refresh]
```

Settles every archived package for the drawing and reports incomplete data
without fabricating ROI.

```text
post-draw-plan --drawing-number N
  --poll-interval ...
  --max-wait ...
```

Generates a scheduler candidate only. It waits for completion, refreshes
results/payout evidence, settles packages, and cannot create `.bet-ready`.

Common comparison report:

- exact input/provenance hashes;
- bank/stake and used/unused amount;
- coupon count and package overlap/Jaccard;
- event frequencies and concentration;
- full/union brief and exact conditional Cover verification;
- modeled probability of 9+/13+/14+/15;
- modeled gross/net EV with assumption warnings;
- runtime and any timeout/fallback;
- recommendation and reason;
- later, actual hit/category/payout/ROI settlement.

## 10. Operational lifecycle

### Morning

1. Synchronize the expected open drawing.
2. Resolve and pin all 15 events.
3. Validate normal playable timing; multi-day/unknown remains non-playable.
4. Collect and freeze market and sports-statistics snapshots.
5. Build a research/preanalysis comparison for Cover, EV, and Hybrid.
6. Archive all candidate metadata and packages as non-actionable.
7. Surface unresolved identities, missing statistics, and provider quota
   problems early.

### Evening

1. Preserve T-45 preflight, T-30 fallback, T-15 final, and T-10 freeze.
2. Revalidate the exact drawing and all 15 provider pins.
3. Refresh allowed inputs and bind one final probability snapshot.
4. Generate all three strategies under the requested dynamic bank.
5. Compare them under the frozen recommendation policy.
6. Publish only one explicitly recommended package when every safety gate
   passes; archive all compared packages.
7. Emit `.bet-ready`, `.no-bet`, or `.failed` atomically.
8. Leave package upload to the operator.

### Post-draw

1. Begin only after the drawing should be complete; poll with bounded retries.
2. Force-refresh the exact finished drawing detail even when its structural
   rows are already complete.
3. Require 15 authoritative results before hit settlement.
4. Acquire payout evidence separately; do not block hit settlement if it is
   unavailable.
5. Settle morning, fallback, final, recommended, and manually recorded placed
   packages.
6. Append the immutable prospective ledger and expected-vs-actual report.
7. Mark missing/failed/partial data prominently and retry later.
8. Never interfere with the next drawing's morning or evening jobs.

## 11. Failure handling

- Unknown/multi-day timing, target mutation, incomplete pins, stale provider
  data, invalid probability triplets, package hash mismatch, failed exact Cover
  verification, or missed publication deadline must fail closed.
- A sports-provider failure must not become a hidden zero or a dropped event.
  Use a time-valid market-only fallback when policy allows it.
- A Cover package with failed verification cannot be published as Cover.
- A Hybrid package that violates a frozen concentration constraint cannot be
  published.
- Timeout handling may retain a previously verified candidate only when the
  policy explicitly allows it and its input freshness/deadline remains valid.
- No optimization may silently reduce the search space merely for speed.
  Approximation requires benchmarked quality impact and explicit metadata.
- Result refresh and settlement failures are operationally non-actionable but
  visible; they never mutate the already archived package.

## 12. Evaluation protocol and gates

### Historical

Use chronological train/development/test boundaries.

Compare at the same bank and stake:

- top-probability baseline;
- current direct EV;
- true Cover;
- Hybrid.

Report:

- average/binned best hits;
- hit rates 9+/13+/14+/15;
- package probability mass;
- exact conditional Cover and brief-containment probability;
- concentration/diversity;
- modeled EV;
- used bank;
- runtime/failure rate.

Historical payout/ROI is reported only where actual payout evidence exists.

### Prospective

- Freeze strategy/model/config before the drawing.
- Archive packages before results.
- Do not tune on the prospective ledger.
- Require a predeclared minimum number of drawings/events before a GO decision.
- Compare paired drawings and report uncertainty, not only point estimates.
- Sports blending remains audit-only until its coverage, calibration, and
  no-degradation gates pass.
- Hybrid remains research-only until it beats or materially improves the
  approved baseline according to predeclared category-hit/concentration
  criteria without an unacceptable EV or failure-rate regression.
- Profitability remains unproven until observed prospective payouts support it.

## 13. Ordered vertical milestones

### Milestone 1 — Package strategy metadata and audit foundation

Deliver one end-to-end audit path without changing package selection.

Scope:

- common strategy/package metadata types;
- `package-audit` CLI;
- deterministic package manifest and audit JSON/CSV/Markdown;
- event frequency, concentration, union brief, exact Hamming/coverage, cost,
  and category-probability metrics;
- dynamic bank/stake validation;
- archive-ready schema contract, but no scheduler behavior change.

Acceptance:

- auditing drawing 4952's 166-coupon EV package reproduces:
  - fixed events 1, 5, 8, 14, and 15;
  - event 12 frequencies `163/2/1`;
  - union brief size 5184;
  - no category 13/14/15 guarantee;
  - worst minimum Hamming distance 6;
- the report labels the package `EV`, not `Cover`;
- changing a coupon changes the canonical package/audit hashes;
- duplicate or malformed coupons fail closed;
- banks such as 4980, 6000, and 9960 validate when divisible by stake;
- focused tests, full pytest, Ruff, and deterministic report fixtures pass.

### Milestone 2 — True Cover strategy and common comparison

Scope:

- probability-aware brief candidates;
- Cover package generation within dynamic bank;
- exact verification;
- side-by-side EV/Cover comparison;
- explicit conditional-guarantee language.

Acceptance:

- false guarantees cannot be serialized;
- reported cost equals coupon count times stake;
- comparison uses one probability/pool snapshot;
- complete package exports are suitable for manual BaltBet batch upload.

### Milestone 3 — Prospective archive and post-draw settlement

Scope:

- additive package/result/settlement migrations;
- archive every generated strategy package before results;
- forced finished-result refresh;
- `settle-drawing`;
- immutable expected-vs-actual ledger.

Acceptance:

- repeated generation/settlement is idempotent;
- all archived packages receive hit/category settlement once 15 results exist;
- payout absence is explicit and does not fabricate ROI;
- corrected results append rather than overwrite;
- morning/fallback/final packages can be compared against the same result.

### Milestone 4 — Sports-statistics acquisition and feature store

Scope:

- provider-neutral interface;
- lawful provider adapter(s);
- morning cache and historical backfill;
- football and hockey canonical feature snapshots;
- freshness, missingness, provenance, and quota reporting.

Acceptance:

- no feature uses information published after its as-of time;
- provider failure has an explicit fallback;
- evening generation can complete without a last-minute network call;
- backfill and live collection produce the same canonical schema.

### Milestone 5 — Calibrated probability blend

Scope:

- sport-specific feature builders/models;
- chronological evaluation;
- calibration;
- immutable probability snapshots;
- market-only fallback and audit-only rollout.

Acceptance:

- no leakage tests pass;
- probability triplets are normalized and reproducible;
- reports compare sports, market, and blended log loss/Brier/ECE;
- blend activation requires frozen no-degradation and coverage gates.

### Milestone 6 — Hybrid optimizer

Scope:

- candidate generation from EV, probability, and Cover seeds;
- frozen multi-objective scoring;
- concentration/diversity constraints;
- dynamic-bank selection;
- exact audit of the final package.

Acceptance:

- no duplicate coupons or false guarantee;
- fixed/near-fixed positions are bounded and reported;
- category probabilities and concentration are reproducible;
- search approximations are labelled and quality-benchmarked;
- historical development chooses configuration, untouched/prospective data
  decides GO/STOP.

### Milestone 7 — Three-strategy production integration

Scope:

- morning three-strategy preanalysis;
- evening three-strategy final comparison and one recommendation;
- atomic archive/publication;
- scheduler manifest migration;
- manual-upload export.

Acceptance:

- dynamic bank flows through every phase without a 4980 constant;
- T-10 publishes only an audited final package;
- old scheduler manifests fail closed or migrate explicitly;
- no bet-placement network code exists.

### Milestone 8 — Post-draw scheduler and continuous review

Scope:

- bounded post-draw polling scheduler;
- result/payout refresh;
- automatic settlement and prospective report;
- operational alerting for missing data;
- regular strategy review from immutable evidence.

Acceptance:

- a completed drawing is settled without manual package reconstruction;
- incomplete results remain pending and retry safely;
- the job cannot publish betting markers;
- every prospective recommendation has an eventual visible settlement state.

## 14. Recommended first implementation slice

Implement **Milestone 1 only**:

> Package strategy metadata, canonical package manifest, and deterministic
> concentration/Hamming/coverage audit.

This is the smallest end-to-end useful slice because it immediately prevents
the central drawing-4952 misunderstanding: an EV package cannot be mistaken
for a category-14 Cover system. It also creates one common measurement contract
that Cover and Hybrid can reuse later, without changing live package selection
or scheduler behavior in the same change.

No sports model, new optimizer weights, database migration, or scheduler
publication change belongs in this first slice.

## 15. Documentation and delivery discipline

For every milestone:

1. Update project-local memory and architecture.
2. Add deterministic unit, integration, and failure-path tests.
3. Run focused tests, full pytest, Ruff, and `git diff --check`.
4. Produce one reproducible report or CLI acceptance example.
5. Keep hypothesis changes separate from operational refactors.
6. Do not claim profit, guaranteed payout, or superiority without the declared
   historical and prospective evidence.
