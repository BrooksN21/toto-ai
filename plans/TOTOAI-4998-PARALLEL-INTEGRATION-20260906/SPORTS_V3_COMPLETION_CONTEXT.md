# Sports Analytics v3: context for the separate implementation task

Task: TOTOAI-4998-PARALLEL-INTEGRATION-20260906. CONTEXT ONLY.
Saved: 2026-09-06T17:00:20.353769+03:00. Main: /Users/turshevr/toto-ai.
Read ACTIVE_PLAN first, then exact coordination/contract/readiness references below.
Owner now prioritizes an actual V3 probability forecaster, not G1 or evidence-only
substitution. This supersedes the old task-role next-action text for this context job.
No tests, API/history collection, fitting, runtime/DB/authority edits or publication ran.
Only this handoff was written. No new implementation plan or backlog was selected.

## 1. Exact promised behavior, not a new model proposal

Authoritative mathematical contract:
`/Users/turshevr/toto-ai/plans/TOTOAI-4996-4997-RECOVERY-20260904/plan.md`, sections3–7.
V3 is an L2-regularized, sum-to-zero multinomial **BK residual**:
`q_raw=softmax(centered(log(p_bk))+w_reliability*r_theta(x))`, then projection
with L1 distance from BK <=0.20 (TV<=0.10). Reliability in [0,0.20], pre-match
coverage/counts only. Finite positive normalized outputs; cap/integrity failure
returns exact BK. No team/league one-hot or draw oversampling on the small corpus.

Features promised: symmetric rolling PPG/goals/GD; independently evidenced opponent
strength/form; exponential recency; venue splits; rest and 7/14-day congestion;
properly time-bound league/season/team standings; pre-match BK margin/entropy;
missingness/reliability indicators. Lineups/injuries require a separate verified
source contract and are not prerequisites to invent or fake for core V3.

Training is whole-drawing chronological expanding-window: labels/results must have
been available before target prediction_as_of. Imputer/scaler/model/calibrator
and nested hyperparameter selection use earlier folds ONLY. Cold start below
3 complete prior training drawings /45events => exact BK, not fabricated theta.
Partial features use train-fold medians+indicators with reduced reliability;
missing exact target or both histories/source rejection => exact BK (1e-15/hash).
Venue absence is not substituted with aggregate evidence. Bounded draw-vs-nondraw
calibration is fitted on earlier labels, never actual target DRAW.

V2 is different: `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/v2.py`:
`build_sports_v2_shadow_artifact`, `project_event_v2`, `SportsV2Config`;
smoothed independent-Poisson + venue WDL, prior_matches=3, default maximum blend0.20;
model id `sports-analytics-v2-poisson-venue-shrunk-v1`. It is untrained.
V1 Jeffreys venue WDL (`probabilities.py`) is not V2, and neither is V3.
G1 refines coupons against supplied probability arrays; it does not forecast them.

## 2. Implemented/accepted foundations, not a fitted V3

Under `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/`:
- `v3_attribution.py:build_v3_attribution_aggregate`: settled descriptive attribution,
  not predictor training; target outcomes here must never enter inference features.
- `v3_features.py:build_sports_v3_feature_table`: deterministic 28-column pre-kickoff
  rolling/venue/rest/congestion/opponent-feature table and semantic hash. Parameters
  rolling_window/minimum_prior_matches explicit. This API itself is not a complete
  raw-capture timestamp/authority validator or learned residual forecaster.
- `v3_coverage_audit.py`: accepted F3/P1 read-only identity/chronology/provenance
  adapter/auditor, thresholds1/3/5/10; evidence/source completeness vs feature
  non-null/strict-scope eligibility remain separate.
- `v3_family_evidence.py:assess_family_evidence`: accepted O1 family annotations,
  event-local independently reviewed references and independent opponent histories.
  Descriptive only; cannot promote legacy eligibility or fit/change probabilities.
- `goal_probe_research.py:load_goal_probe_shadow` / `_load_history_snapshot`:
  current GOAL identity/binding/raw imports and verified regulation-90 score rules.
  AET/PEN require valid FtScore; missing/malformed => explicit exclusion/fallback.
  A V3 adapter must actually reuse/prove equivalent normalization; do not assume
  every existing v3 raw parser automatically inherited that fix.

Current source adoption/publication is complete (source b28647c, metadata c43fa70).
Old readiness/worktree-baseline/O1 pending-integration language is historical.
No reviewed fitted residual/calibrator/model serialization or V3 probability
adapter was evidenced by these scoped contracts/modules. O1/G1 acceptance is not
acceptance of a probability model or a successful real P1/F4 gate.

## 3. Precise missing pieces and data

1. **V3 inference input adapter:** exact current target/provider/team orientation,
   raw capture<=as_of<kickoff/deadline, clean 90min histories, reviewed league/season/
   team scope, deduplicated independent opponent history, feature masks, immutable
   frozen BK identity. Carry rejection reasons through; no unverified O1 promotion.
2. **Remaining feature transformations:** opponent-adjusted strength/recency and
   reviewed standings/BK-margin/entropy/reliability design must be materialized
   according to the saved contract; existing 28 columns are not the whole promise.
3. **Fit artifact + inference:** learned theta, training IDs/as_of/available-label
   evidence, train-only transforms/imputer, regularization/selected hyperparameters,
   optional accepted draw calibrator, feature schema/version/hash and deterministic
   residual projection/fallback. No accepted trained weights are supplied here.
4. **F4/P2 validation harness:** predeclared A0 untouched BK; A1 frozen V2; A2 core
   strict V3; A3 core+draw; A4 full+draw+missing; A5 full without draw. Preserve rejected
   and missing rows in denominators, cold starts and paired frozen authority.
5. **Version-aware comparison integration:** accept the new immutable model/feature
   artifact and recompute its bounded residual against the exact final BK input.
   Current V2 rebasing is not evidence that an already-computed V3 residual can be
   blindly mixed again. Require explicit model version, hashes, elapsed/fallback
   status and candidate metrics. Preserve current primary and authority; do not
   silently redefine an authorized model/strategy under an old identifier.

Historical inputs named by readiness: exact manifest
`/Users/turshevr/toto-ai/plans/TOTOAI-SPORTS-HISTORY-PERSISTENCE-20260904/backfill-4990-4995-manifest.json`,
frozen final BK inputs, pre-target histories and timestamped settled label snapshots;
4996 adds a separately bound15event extension. Known first real P1 receipt (historical,
not a newly checked current audit):90rows;4990 deadline rejection,4991 ASOF_AFTER_FINAL_INPUT;
52complete/8missing/30rejected; full-current counts52/48/17/0 at thresholds1/3/5/10,
strict-scoped full count0. Later classifier fixes are code corrections, not proof
that missing pre-draw evidence appeared. No new audit was run here; do not claim this
old receipt is the latest complete corpus or that 70% strict coverage now passes.

## 4. Can honest nontrivial V3 run for4998 now?

Saved current adopter receipt has a valid fresh data carrier:28histories/280observations,
14/15V2-covered events and1BKfallback; corrected seed artifact ac04ea9b30359094…,
file2d5003c79378fb0b5f425ddf8cfdc0902327e727c0c0f3bb43843b43f2139e78.
These are available pre-draw features for a bounded experiment, NOT labeled training
examples sufficient to invent theta, independently verified opponent networks or
proof of V3 full-feature coverage. Event9 stays fallback absent exact binding.

Engineering can implement/test a deterministic residual pipeline now. Honest
nonzero inference is conditional on a genuinely fitted, hash-bound artifact from
eligible earlier labeled draws and the unchanged gates. None is established here.
Without it, only explicitly labeled cold-start/unfitted exact-BK inference is honest;
that is not completion of a useful V3 predictor. Hand-chosen weights, zero weights
advertised as trained, a renamed V2 seed, or G1 gains are not acceptable substitutes.
The latest request does not silently waive the pre-existing F3/F4 safety gates.

Impossible to manufacture now: missing historical pre-as_of captures, an untouched
holdout after its outcomes were used for design, or30prospective paired draws in one
afternoon. The4990–4995 replay is design-informed;4996 is holdout only with demonstrable
pre-result candidate fixation. Prospective gate remains30drawings/450events,>=70%
coverage, leakage-free metrics and package non-degradation. No guaranteed predictive
improvement follows from completing software or from one successful comparison.

F4 saved screen:7folds/105events including fallback; A4–BK logloss<=-0.0015,
Brier<=-0.0010,ECE<=0; top-correct no worse by>1; per-fold degradation bounded
(+0.020logloss/+0.010Brier), drawing-cluster bootstrap, draw/missing ablations and
all normalization/hash/cap checks. Even PASS permits research/paper tracking,
not a statement of prospective profit. Actual4998 comparison/finalPLAY not checked
in this context job; saved V2/G1 opt-in is not V3 activation.

## 5. Exact entry points and bounded regression handoff

- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/final_hybrid_comparison.py`:
  `execute_final_hybrid_comparison`, `_validate_sports_artifact_identity`,
  `_rebase_sports_probabilities`, `_parallel_candidate`, `_best_single_coupon_payload`.
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/final_hybrid_sidecar.py`:
  `run_final_hybrid_sidecar`, `prepare_parallel_sidecar_artifacts`, `_execute`,
  `_validate_parallel_authorization`; primary publication must precede detached
  comparison; timeout/error/unknown model preserves control. No changes made here.
- `/Users/turshevr/toto-ai/src/toto_ai/sports_stats/evaluation.py`: existing metrics/
  frozen BK evidence gate to reuse, not a substitute for train-fold-only F4.
- `/Users/turshevr/toto-ai/src/toto_ai/cli.py`: existing GOAL/research and final-sidecar
  commands are integration surfaces only; no present V3 training command established.

Existing exact relevant test paths (not executed in this job):
- `/Users/turshevr/toto-ai/tests/test_final_hybrid_g1_integration.py`
- `/Users/turshevr/toto-ai/tests/test_final_hybrid_settlement.py`
- `/Users/turshevr/toto-ai/tests/test_final_hybrid_sidecar.py`
- `/Users/turshevr/toto-ai/tests/test_g1_wrapper_reuse.py`
- `/Users/turshevr/toto-ai/tests/test_goal_probe_collection.py`
- `/Users/turshevr/toto-ai/tests/test_goal_probe_research.py`
- `/Users/turshevr/toto-ai/tests/test_sports_probability_evaluation.py`
- `/Users/turshevr/toto-ai/tests/test_sports_probability_shadow.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v2.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_attribution.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_coverage_audit.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_family_evidence.py`
- `/Users/turshevr/toto-ai/tests/test_sports_v3_feature_table.py`

Missing V3-specific regression obligations: train/target separation and label
availability; transform/calibrator fitted only on train; cold-start exact-BK/hash;
missing/rejected source distinction; wrong identity/late capture/duplicate/90minFT;
independent opponent evidence; finite normalized logits and L1 cap; model/feature/
training/config hashes; deterministic fit/infer; A0–A5 denominators/draw ablations;
final-BK-bound version-aware inference (no V2 relabel/double blend); unchanged primary,
budget/authority/nondegradation, primary-first publication, timeout fallback and
independently computed highest-P13 coupon. Write these in the separate implementation
job; no model/test files were created here and no acceptance is claimed.

## Source pointers / status boundary

Read only task-relevant saved contracts/modules above plus
`/Users/turshevr/.codex/worktrees/a7aa/toto-ai/plans/TOTOAI-SPORTS-V3-MODEL-READINESS-20260904/MODEL_READINESS_REPORT.md`,
`P1_FIRST_REAL_RUN_RECEIPT.json`, `P1_CHRONOLOGY_CLASSIFIER_FIX_REPORT.md`,
`ALL_MODELS_NEXT_SLICE_PLAN_20260906.md` in that same directory.
Historical context.md's0/15old seed and NOT_ACTIVATED O1/G1 text are superseded by
current ACTIVE_PLAN/publication handoff; neither historical text nor current14/15V2
proves V3 readiness. Exact mathematical changes/gate relaxations require separate
explicit decisions, not inference from urgency. NEXT:owner routes this bounded
context to the separate implementation task; this worker stops, no publication.
