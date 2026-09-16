# Sports v3: retrospective fit contract review / narrow plan amendment

Task **TOTOAI-RESUME-20260915**. Independent algorithm/protocol review; planning only, no new fit/data/API/source/DB/scheduler/Git mutation. Project-local algorithm-review skill applied. This file amends R2a→R3 in the existing plan, not a replacement project plan. The proposed research-domain change below is **NOT IMPLEMENTED / NOT LIVE APPROVED**.

## Resolution

**Legitimate retrospective learning is possible. A provider response fetched today is not inherently target/future leakage.** Historical fixtures need correct identity, results and temporal selection; their actual fetch time must remain truthful. Unknown historical availability/revisions lower the strength of claims, and can require a sensitivity-only experiment, but do not universally prohibit all numerical research fitting.

The current code combines an archived pre-draw evidence contract, feature eligibility and a specific F4 promotion experiment. It has no honest input domain for late-collected historical reconstruction. Do **not** relabel sources FROZEN_HISTORICAL_INPUT, backdate captures, set scope_verified by hand, or fabricate scheduler/consent fields. One small isolated research entry can separate these concerns while retaining the same residual learner and production guards.

## Exact code-backed blockers, separated by purpose

|Concern|Actual code / behavior|What it really blocks|
|---|---|---|
|History capture timestamp|`v3_probability_features.py:71–161`: `_history` rejects fetched_at > target.as_of; each accepted row gets available_at=capture. At most4 captures/side, each≤10rows.|The existing archived-input normalizer, not all historical feature studies. Late response can contain valid earlier match facts; do not fabricate earlier capture.|
|Bookmaker timestamp|`v3_probability.py:124–129` expects as_of≤bk_captured_at<kickoff; builder `v3_probability_features.py:269–270` requires final capture before deadline.|A late reconstructed market snapshot cannot be fed unchanged as a validated pre-draw feature row. Unknown quote-time arrays can support separately labeled scenario fitting, not establish historical prediction edge.|
|Training domain and label availability|`v3_probability.py:218–251`: only FROZEN_HISTORICAL_INPUT/SYNTHETIC_TEST_ONLY; earlier drawing and label.available_at before prediction cutoff. The manifest/inference validator repeats domain restrictions at470–550.|A genuine retrospective research domain is missing in both admission and serialized artifact validation. An imported label timestamp is not necessarily the original result publication time. Separate actual fetch and proven/unknown historical availability rather than falsifying either.|
|Canonical identity and team scope|Builder `v3_probability_features.py:293–325`: exact fixture/team/orientation + target and every history row's gender/age_group/squad_type equality; unknown scope→false. `reliability`148–152 in v3_probability.py returns0 on missing scope/exacttarget/rejection.|Wrong team/women/youth/reserve or mixed entity history is genuine contamination. Missing three literal taxonomy strings is a representation/evidence issue, not missing numeric statistics. Those strings are not numerical predictors. Exact IDs alone still do not prove their provider meaning/validity.|
|Real eligible training corpus|`train_v3`199–386: complete15-event earlier real drawing groups;≥3drawings/45total records; positive-weight eligible rows needed; otherwise COLD_START, no fitted weights.|2257cached unique matches are history facts, NOT2257V3 supervised examples. Every training target also needs its own earlier features, outcome, BK baseline and proven identity.21current feature rows include8provisional mappings and are not a full qualified corpus.|
|Missing features|`feature_disposition.py:23–72`; `train_v3:264–337`: A2/A3 require all37core features; A4/A5 use53-feature schema with train-fold imputation and missing indicators.|Missing venue/standings/margin does NOT automatically forbid an A5 numerical fit. It still requires eligible identity/scope/history and genuine BK. `_values` recalculates BK entropy/margin. Imputation is not observed coverage or proof.|
|Full F4 experiment|`v3_f4.py:37–117,277–326`: independent scope/fold receipts,15ordered slots,V2 and scheduler-shaped hashes,max7folds. `v3_f4_gate.py:170–173`: sevenfolds/105events,4990–4996,≥70% ALL53 coverage plus quality/stability predicates.|A specific comparative acceptance protocol, not a prerequisite to call the lower-level fitter. Do not make up historical scheduler plans or alter this gate to permit the first research fit.|
|Live/promotional claims|F4 report `v3_f4_gate.py:242–247` still says30prospective draws/450events and operator/activationfalse even after its calculations.|No historical fit, good retrospective score or higher modeledP13 independently grants live activation/PLAY. Current operator/consent/deadline constraints remain untouched.|

Important nuance: native minimum3draws/45rows counts the whole retained denominator, NOT45positive-weight examples; even one eligible row among45 can enter the fitting branch. Report eligible rows/effective weights and their independent fixture counts explicitly. TRAINED_EXPERIMENTAL is not a sample-quality certificate. Preserve the existing minimum for the first like-for-like V3 pilot; do not relax it merely to announce a fit.

## The 3/4 versus5 venue issue is not a universal data outage

`v3_features.py:335–349` first takes the last10 overall matches, THEN filters same venue within that window. With3home/4away observations and minimum5, four venue rates are legitimately missing; appending older matches outside the last10 cannot cure that by itself. The pilot passes minimum5 (`sports_history_reconstruction.py` native feature call), while `build_v3_predictors` defaults to3 and accepts explicit1..10. These are **different pinned policies**, not proof all Sports v3 requires5.

Do not silently reduce5→3 or change the definition to “last10 at this venue.” First like-for-like fit keeps the declared feature policy and uses A5's existing train-only missing-value handling. A separate earlier-data ablation may later compare venue shrinkage/windows/minimums, with definition/version and uncertainty disclosed. No requirement for28/28base features is equivalent to37/37core or53/53full: verified dimensions are28,37,53 respectively.

## Completion of past games: evidence, not invented duration

Keep the reviewed generic exclusion for a game beginning before cutoff but finishing afterward. Valid support is:
1. a source's explicit, internally consistent finish timestamp before cutoff;
2. an actual terminal-state observation before cutoff (completed_by upper bound, finished_at remains unknown);
3. in a new reviewed reconstruction adapter, an attributable dated terminal match report/settlement whose established publication interval ends before cutoff. A timezone-resolved whole-day upper bound is permissible ONLY if that publication date really is supported; never invent00:00 or kickoff+90minutes.

Today's terminal status, kickoff and updatedAt alone do not prove completion by the historical decision time. A late capture with an explicit old finish is still usable, and source revision uncertainty remains separate. Existing strictcode rejects unsupported cases rather than asserting they were definitely unfinished.

For ordinary older historical results without this strict proof, a separately registered **sensitivity assumption** can be studied: the terminal fixture completed on its recorded match date, with no unrecorded multi-day suspension/resumption. It must be an explicit unverified assumption (not a new finished_at or available_at), exclude near-cutoff and any known delayed/resumed/ambiguous cases, preserve the strict-evidence cohort separately, and show results with/without these rows. A date-only snapshot cannot make that assumption proven. Do not automatically introduce this assumption into the current strict collector or live feature gates. First pilot should prefer the already found terminal-before-cutoff cached evidence; it needs no assumption waiver.

## ONE isolated implementation proposal: R3 retrospective A5 entry

Proposed module `src/toto_ai/research/sports_v3_retrospective_fit.py` + focused tests. No new framework, default sampler, package generator or production model registration.

1. **Explicit research DTO/domain.** Preserve target decision cutoff, source fetched_at, fixture kickoff, completion evidence/interval, source revision, label fetch/publication evidence and market quote-time grade separately. Use `RETROSPECTIVE_SPORTS_V3_RESEARCH_V1`, with subcohorts STRICT_RECONSTRUCTED vs UNVERIFIED_ASOF_SENSITIVITY. All operator/activation/profitability flags false. Unknown values stay null; no FROZEN or SYNTHETIC disguise, no fake final/scheduler hashes. Bind research manifest hashes instead.
2. **Entity safety, not fake class.** Reuse the existing proposed canonical-ID+validity+independent-evidence binding. For like-for-like native admission, satisfy real common entity/taxonomy evidence. If ordinary records lack literal class labels, an explicitly reviewed research-only alternative may admit exact provider/canonical entity lineage over the whole period with unknown taxonomy retained and a separate unknown-class stratum. This requires real independently checked identity separation (including reserve/youth/women IDs); similar names, mere ID strings or self-asserted boolean are insufficient. Do not set native scope_verified=true or redefine its meaning. Missing/contradictory lineage remains excluded.
3. **Same mathematical learner.** Reuse A5's BK-centered regularized residual, train-only transforms, sum-zero weights and0.2weight/L1caps. If the current validation shell prevents reuse, factor only its pure numerical fit kernel into a shared helper and demonstrate unchanged legacy results; the new typed research wrapper owns its own evidence eligibility/reliability metadata. Do not clone/diverge the optimizer or replace BK with uniform probabilities. Any changed research eligibility rule must be versioned and explicitly reviewed; legacy cold-start/minimums remain for first pilot.
4. **Genuine BK offsets required.** Existing unknown-asof finished market can support an honestly labeled scenario fit using the same residual math; it cannot yield a validated historical real-money edge. If a historical training fixture has no BK triple, it is not an eligible V3 residual example. A sports-only model is a different experiment, not a shortcut labeled deployed Sports v3. Later standings or target-informed market revisions are never silently called historical features.
5. **Chronological fit/inference isolation.** Freeze training roster, feature policy, eligibility, code and fixed hyperparameters BEFORE fitting/scoring. Training rows' feature windows exclude their own results and all future games. Training target outcomes must be completed before the validation decision cutoff; actual late retrieval stays recorded. Fit transforms/calibration only on training data. Produce serialized model+manifest and hash-bound predictions, then load validation labels. Research inference validates this distinct model kind/domain and can never route to native live inference by accident.

## Minimum actual next fit step (not another whole audit)

Cicero hands over ONE bounded manifest, not all cache contents: earliest complete prospective-like target draw in the requested roster with useful verified sports inputs; preceding eligible real drawing groups and each group's15trueevent/outcome slots; target and train BK mappings; positive-weight feature counts; exact excluded/provisional counts. Prefer training draws before4999 for a4999validation fold if present. Do not pretend arbitrary2257history fixtures are bookmaker-labelled targets.

**Execute one A5 fit** on at least3earlier real drawing groups/45total rows after research-domain/identity review, only if there are genuine eligible rows from the corpus (report how many; no manufactured45eligible claim). Keep original fixed l2=0.1,steps240 and10s fit allowance; no hyperparameter search. Freeze one later holdout prediction, compare its BK baseline on logloss/Brier and coverage, not only package maxhits. No coupon generation required to prove a real trained artifact exists. Artifact must contain nonempty learned weights, eligibletraincount, exact input/label hashes, transform, modelstatus and independent repeatability/leakage checks; COLD_START/FIT_BUDGET_EXHAUSTED is not completed training.

If the bounded handoff cannot find3eligible earlier groups or genuine BK offsets, return the exact missing join/field/row counts immediately. The next action is filling those precise inputs, not waiting for all120targets/53features/F4PASS or starting another framework. Do not lower minimums or fabricate class/time to satisfy a deadline. A separate tiny mechanical-fitting smoke is possible only as an explicitly different small-sample experiment, not counted as the requested nativeV3fit.

Freeze the already chosen4999–5003development /5004–5006no-further-tuning confirmation boundary. Their outcomes have been viewed, so they are design-informed historical diagnostics, not pristine holdout evidence. For the frozenconfirmation do not train/impute/calibrate on5004–5006labels. Establish genuinely untouched future evaluation for any promotion claim. If this corpus cannot support that split, report unsupported folds without replacing them with convenient winners.

## Acceptance checklist for the small patch

- Late fetch + supported earlier completion admitted as research; actual fetched_at preserved. Known post-cutoff completion and target/future score injection excluded before feature extraction; date+90 never used. Assumption-only rows cannot enter strict cohort.
- Wrong/ambiguous canonical ID, side, women/youth/reserve collision, expired binding, conflicting or fabricated scope rejected; unknown taxonomy never becomes a false approved native boolean.
- Source/hash/target/label mapping and feature schema pinned; 28-base versus37core/53full not conflated. One source repeated for severaltargets is not an independent training observation count.
- Missing venue/standings/margin retained with A5 train-only imputation/indicators; test heldout/future-label changes cannot affect fitted coefficients/transforms or earlier predictions.
- All train groups precede validation; future/unavailable training labels fail strict cohort and are separately graded in sensitivity cohort. No heldout training or targetfeature leakage; unknown-time quote sensitivity never claims causalbacktest.
- Real BK offsets/no uniform replacements, normalized finite3-way predictions, unchanged residual/caps/fixedseed/default sampler and legacy parity. Zeroeligible/coldstart/timeout must be explicit.
- Distinct researchmodel cannot satisfy nativeF4/liveoperator validation, consent or release; no forged plan/archive. Model and predictions are frozen before validation scoring.
- Independent review accepts this named protocol and eligibility rule before actual realfit. First run reports actual row/weight/feature counts, logloss/Brier/calibration limits and ≤10s fit receipt; no promised lift from8known draws.

## Verification performed here

Static inspection of only named contracts and current plan; project-local skill applied. Verified exact feature dimensions by import. No real fitting, full suite, generation, database, provider call or oldF4re-audit. An initial introspection used a nonexistent `v3_features.FEATURE_NAMES` export; corrected to the already imported `PREDICTOR_FEATURE_NAMES` symbol in v3_probability. This was a review-command typo, not a project test failure.

Observed 2026-09-15T21:18:14.687766+03:00; source SHA256 pins:

- `src/toto_ai/sports_stats/v3_probability.py`: `b9e91b89ec08e2d87d6a1d676857f2e48c6c7500558558dac8d8295ba7f43b26`
- `src/toto_ai/sports_stats/v3_probability_features.py`: `9723dc218a56a0fca8545b8f9b1f08e2d9470ad7300c4c2f32018639cc00e4d5`
- `src/toto_ai/sports_stats/v3_feature_disposition.py`: `fc3e9df4f4a1730cc9547ae26b1af06fdbf734e54bd9380be36cd8b04b3dbf96`
- `src/toto_ai/sports_stats/v3_f4.py`: `d556803b7ef9df09986c785cd5ffcb3266d09c80df240d46cb2b0464ebb1e3f4`
- `src/toto_ai/sports_stats/v3_f4_gate.py`: `334f4bf5407d946ef1665efe23b4a622c38be5bb5891d8e827951769320c72fd`
- `src/toto_ai/sports_stats/v3_features.py`: `90e6172afb5a0c982dd98be5015abac5f4f54a588eb8943798b75dc99bd96970`
- `src/toto_ai/research/sports_history_reconstruction.py`: `f6be8613b598d8b7cb1bac2228dedecc117026dd593fe669d6169988549a2206`
