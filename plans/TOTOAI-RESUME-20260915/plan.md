# TOTOAI-RESUME-20260915 — executable bounded model plan

Created 2026-09-15T14:07:31.908300+00:00. **PLANNING ONLY: no implementation/training/replay has run in this job.**

## Completed R1 / current R2a checkpoint
R1a/R1b COMPLETE:8draws×3actualnative arms,24packages/scored,4980/30/166; unknownasofSCENARIO only. R2genericcompletion/targetbindingfixes independentlyPASS;21eventfeatures13direct8provisional, nofit. Current nextaction is R2a in [model-improvements-next.md](model-improvements-next.md), NOT another R1run or planning pass. R3fit/R4fullfivearms/R5live integration remain conditional. Earlier instructions below describe the initial design and completed work; this checkpoint and machinechecklist govern resumption.

## Original revision-v2 first increment (now completed)
**Revision v2: A is COMPLETE; B completed bounded5000 early780/26 and4999 parity. Start R1 NOW: isolated finished-market scenario adapter → small tests/independent review → actual8draw×3native-arm runs at4980/30 (target166).** Sports reconstruction R2 proceeds independently; a trained fifth arm awaits data/fit, not another rename ofBK. Missing original captures prevent faithful predraw replay, not explicitly graded scenario computation.

Authoritative revision and first executable handoff: [retrospective-reconstruction-protocol.md](retrospective-reconstruction-protocol.md). Fresh data: [retrospective-reconstruction-context.md](retrospective-reconstruction-context.md) and adjacentJSON. This revision updates planning only; no new model runs/fit/activation have happened. Existing stage completion receipts remain history; the addendum governs next actions and evidence domains. Machine checklist: [machinechecklist.json](machinechecklist.json).

## Protected5007 and resource ownership
Parent alone retains production operations. Saved—not rechecked here—plan84b0f69e06487848:18:00firstprimary,19:30final,19:50cutoff,20:00closeMSK. No child/source task changes jobs, DB, catalogs, consent, operator files or shared live imports/CLI/config. A is additive library-only and must leave runtime import graph unchanged; F is after5007. Before CPU-heavy tests/replay, parent checks runway to next operational checkpoint and grants one bounded job; do not run competing model sweeps beside primary. First5000pilot records wall/CPU/RSS, candidate counts and progress, with reviewed declared runtime allowance; timeout means PARTIAL, not exact completed comparison. Do not shorten algorithms/search space to manufacture performance. No new heartbeat or unattended-chat promise.

## Shared experiment contract
Schema/proposed fields (new, NOT claimed to exist): research_manifest_version, evidence_domain, drawing_number, source_payload_sha256, metadata_sha256, observed_at, information_available_at, prediction_as_of, target_deadline, identity/scope_receipt_sha256, code/config/seed hashes, predictor_id/version, optimizer_id/version, probability_input_sha256, requested_bank/effective_bank/stake/pool, candidate/frozen_output hashes, label_availability/hash, missing_reason. Fields map only to source-verified native values; a missing field remains missing. All source/fold/denominator rules must be frozen before fitting/scoring. No fabricated scheduler-plan, operator-final-input or pre-draw archive.
Keep genuine frozen pre-draw capture, evidenced reconstructed historical research, UNKNOWN-ASOF post-event market scenarios, prospective data and synthetic tests separate. UNKNOWN-ASOF is diagnostic-only, not eligible causal training/backtest evidence; see revision-v2 protocol. A late fetch timestamp is retained, never rewritten as early capture. Retrospective data influenced by prior analysis cannot become a blind test. Successful retrospective diagnostics do not bypass the established30drawings/450events,≥70%coverage prospective gate.
Predictors are BK/SportsV2/SportsV3. quality-v2/quality-v3/robust are optimizers. Five requested report arms are not five independent probability models. Proposed SportsV3 arm fixes the quality-v2 optimizer to isolate predictor effect; cross-optimizer SportsV3 experiments only later as separately recorded ablations. Existing sports-shadow optimizer/config is taken from verified bound artifacts, not assumed from its name.

## Stages

### A. Adopt accepted SportsV3/F4 as an inert production library
**State:** READY_FOR_SCOPED_IMPLEMENTATION. **Links:** C2, C3. **Owner:** implementation worker; independent reviewer; parent integrates. **Depends:** none.
**Inputs:**
- model-context.md/json
- isolated F4 snapshot04 manifest plus actual review06 accepted delta/receipt
- current production source dependency hashes
**Changed modules / tests (proposed scope, not changes already made):**
- src/toto_ai/sports_stats/v3_probability.py
- src/toto_ai/sports_stats/v3_draw_calibration.py
- src/toto_ai/sports_stats/v3_probability_features.py
- src/toto_ai/sports_stats/v3_feature_disposition.py
- src/toto_ai/sports_stats/v3_f4.py
- src/toto_ai/sports_stats/v3_f4_gate.py
- src/toto_ai/sports_stats/v3_f4_metrics.py
- src/toto_ai/sports_stats/v3_generation.py
- src/toto_ai/sports_stats/v3_research_safety.py
- Tests: tests/test_sports_v3_probability.py; tests/test_sports_v3_probability_features.py; tests/test_sports_v3_f4.py; tests/test_sports_v3_f4_metrics.py; tests/test_sports_v3_generation.py; tests/test_sports_v3_research_safety.py; tests/test_sports_v3_library_isolation.py (new)
**Exit criteria:**
- exact accepted review06 source/dependency mapping, no blind application of obsolete snapshot04
- focused tests and Ruff pass against parent dependencies
- import does not register CLI, start process/network/DB/job, or alter final comparison imports
- reviewed library-only change; no model training/rollout claim
**Why blocked / what is executable now:** Real training data does not block inert library/test adoption. Unknown exact review06 file hash map must be verified before applying, not invented.
**Outputs, under task directory unless model module:** A-library-adoption.json, A-verification.log

### B. Research RAW5000 adapter and three-family early-pool replay
**State:** READY_FOR_SCOPED_IMPLEMENTATION. **Links:** C1, C4. **Owner:** research adapter solver; independent algorithm reviewer. **Depends:** none.
**Inputs:**
- replay5000/replay-status.json
- model-validation.json exact RAW/meta hashes
- existing native budget/generation/safety function contracts
- separate label file read only after frozen output
**Changed modules / tests (proposed scope, not changes already made):**
- src/toto_ai/research/raw_package_replay.py (new proposed standalone module)
- src/toto_ai/research/replay_contract.py (new only if needed to isolate schema)
- tests/test_raw_package_replay.py (new)
- Tests: real RAW metadata chronology and hash fixture; native effective budget780 and count26; all three candidate families identical input/seed/evaluation scenarios/budget; outcome and sports/artifact leakage rejection; no production scheduler object fabrication and no operator export; duplicate/fallback/timeout accounting; deterministic output and no overwrite; control generator equivalence at same budget
**Exit criteria:**
- research schema/version/code/config/RAW metadata/probability hash frozen, operator_compatible=false and automatic_wagering=false
- qv2/qv3/robust generated through native algorithm functions and separately scored after freeze
- sports-shadow and SportsV3 explicitly SKIPPED_MISSING_SPORTS, no substitution
- report requested4980 versus effective780; pool78748; common26 cap; actual count may be lower on native feasibility
- no claim equivalent to full4980 or final-window performance
**Why blocked / what is executable now:** Executable adapter absent; available early RAW sufficient for implementation plus narrow three-family replay. Exact generator call signatures must be bound from local source in solver, not guessed by planner.
**Outputs, under task directory unless model module:** replay5000-v1/research-manifest.json, replay5000-v1/frozen-generations.json, replay5000-v1/metrics.json, replay5000-v1/report.md

### C. Point-in-time sports and market availability table for4999–5006
**State:** PARTIAL_INPUTS_EXTERNAL_SOURCE_UNCONFIRMED. **Links:** C1, C2. **Owner:** data-evidence worker, independent provenance reviewer. **Depends:** none.
**Inputs:**
- existing model-validation availability ledger; no repeated archive audit
- canonical completed results4999–5006 already imported
- existing verified sports-match history where available
- public official historical match/league archive only after bounded provider feasibility check
**Changed modules / tests (proposed scope, not changes already made):**
- src/toto_ai/research/historical_feature_corpus.py (new proposed offline builder)
- src/toto_ai/sports_stats/history_backfill.py only if separate reviewed retrospective adapter is justified; preserve existing contract
- tests/test_historical_feature_corpus.py (new)
- Tests: women/youth/reserve exact identity non-substitution; regulation90 versus extra-time/penalty handling; same-day timezone/order and strict availability before as_of; future/target match injection rejected; season/cross-competition scope rules; today standings or revised future knowledge rejected; captured_at remains real fetch time; missing/ambiguous/source failure rows retained; match-history deduplication and immutable source revisions
**Exit criteria:**
- one per-event/family availability ledger with exact identity/source/time/row hashes and evidence-domain
- All8 finished market/pool values exist, with5001–5006quote as-of UNKNOWN; preserve domain grade. Football-history reconstruction does not establish historical quote availability
- two separate corpus domains: original frozen captures and explicitly reconstructed historical research
- accepted independent source/scope receipt or explicit missing status for every required field
- no changes to original chronology rejected rows, denominator, DB or operational ledger
**Why blocked / what is executable now:** No verified public provider proving all needed historical data/time-version access yet. Capture-time gate rejects new late fetch as old capture; reconstruction needs separate reviewed availability contract. Current DB outcomes alone are labels.
**Outputs, under task directory unless model module:** corpus4999-5006/availability.json, corpus4999-5006/features.json, corpus4999-5006/labels.json, corpus4999-5006/source-review.json, corpus4999-5006/missing-inputs.md

### D. Versioned chronological fit/freeze/evaluate with valid fold scaling
**State:** CODE_READY_DATA_BLOCKED. **Links:** C2, C3. **Owner:** SportsV3 fit solver; independent leakage/statistics reviewer. **Depends:** A, C.
**Inputs:**
- accepted eligible corpus/source receipts
- independent BK/V2/probability/fold bindings
- frozen chronological experiment protocol; earlier label availability
- existing A0–A5 controls and accepted probability tolerances
**Changed modules / tests (proposed scope, not changes already made):**
- src/toto_ai/sports_stats/v3_f4.py
- src/toto_ai/sports_stats/v3_f4_gate.py
- src/toto_ai/sports_stats/v3_f4_metrics.py
- src/toto_ai/research/sports_v3_walkforward.py (new proposed entry point)
- tests/test_sports_v3_walkforward_protocol.py (new)
- Tests: legacy1–7-fold results retained under legacy protocol; version2 full requested eight-draw roster retained including missing/insufficient-train cases; unsorted/duplicate/incomplete fold roster rejected; labels unavailable at fold cutoff excluded from fit; train-only transforms/imputation/calibration; predictions persisted/readback before target labels; future-label and target-feature mutation invariant tests; same seed, bounded resources/progress and deterministic semantic hashes; synthetic input can never produce historical/production PASS; 67/105 old corpus remains below74/105; missing features not silently dropped
**Exit criteria:**
- explicit versioned roster-driven fold-count admission rather than deleting max7 guard
- resource estimate/bound and entire roster checked; any unsupported size reported, not split into cherry-picked passing batches
- for every fit, train only earlier complete eligible draws whose labels were available at prediction_as_of
- new4999–5006 evaluation called retrospective/design-informed, not blind prospective holdout
- real model/inference/evaluation artifacts produced where admissible; otherwise exact missing/insufficient-training disposition
- probability gate recomputed independently; unchanged coverage/prospective gates, PASS_RESEARCH_ONLY not operator eligibility
**Why blocked / what is executable now:** Real training lacks eligible corpus/fold/market/V2 evidence. Code, schema and synthetic leakage tests can proceed independently. Old67/105 ceiling is not recalculated as a new-batch metric.
**Outputs, under task directory unless model module:** walkforward-v2/protocol.json, walkforward-v2/fold-roster.json, walkforward-v2/models/, walkforward-v2/predictions/, walkforward-v2/probability-evaluation.json, walkforward-v2/independent-gate.json

### E. Five labelled arms, common comparisons, complete missingness reporting
**State:** PARTIAL_4999_DONE_REMAINDER_BLOCKED. **Links:** C1, C4, C5. **Owner:** offline evaluation solver; independent algorithm reviewer. **Depends:** B, D.
**Inputs:**
- exact frozen predictor manifests, corpus/market/probability hashes
- same bank/stake/pool/config/seeds and evaluation stream per comparison
- existing frozen4999 results report reused
- official verified payout coefficients/receipts only if supplied
**Changed modules / tests (proposed scope, not changes already made):**
- src/toto_ai/research/model_comparison.py (new proposed offline orchestrator)
- tests/test_research_five_arm_comparison.py (new)
- existing probability/coverage/settlement helpers reused without production policy edits
- Tests: candidate and common evaluation probability matrices cannot be confused; missing SportsV3 not replaced by SportsV2; duplicate robust/qv2 outputs recorded with hash and fallback reason; 15-event union13/14/15 semantics preserved; no summing dependent coupon chances; score after freeze only; category counts differ from drawing hit rate; poolcap and same-input assertions; unknown payout produces nullROI, never zero profit/loss assumption
**Exit criteria:**
- predeclared fifth arm SportsV3 predictor + quality-v2 optimizer, not renamed SportsV2; all arms typed predictor×optimizer
- BK-qualityv2, BK-qualityv3, BK-robust, V2-qualityv2/saved sports-shadow configuration, V3-qualityv2; actual sports-shadow optimizer pinned from artifact, not assumed
- predictor logloss/multiclass sumBrier/draw-class reliability/calibration scored once per distinct predictor
- packages exact unionP13+/P14+/P15 under SAME frozen reference measure plus separate self-model estimates; actual hits9–15 and unique/exposure/time metrics
- all8 drawings and5arms retained even if NOT_EVALUABLE; paired quality comparisons on same eligible subset with coverage and fallback slices
- ROI only if payout evidence verified; no lift/profit claim fromn1 or posthoc model choice
**Why blocked / what is executable now:** Genuine5000early780/26 remains separate; all8 finished snapshots support a new4980/166 scenario comparison afterR1. Sports inputs for5000–5006 requireR2, actualV3fit requiresR3. Report all missing arms without treating absent predraw captures as a ban on reconstruction.
**Outputs, under task directory unless model module:** evaluation4999-5006/arm-matrix.json, evaluation4999-5006/report.md, evaluation4999-5006/category-metrics.csv, evaluation4999-5006/probability-metrics.json, evaluation4999-5006/roi-evidence.json

### F. Manifest-controlled prospective integration after5007
**State:** BLOCKED_BY_RESEARCH_AND_INDEPENDENT_ACCEPTANCE. **Links:** C3, C4. **Owner:** parent operations after implementation/review handoff. **Depends:** A, D, E.
**Inputs:**
- accepted source and independent probability/evaluation receipt
- versioned model/training/feature/corpus/fold/calibration/probability/financial manifests
- separately approved eligible future drawing integration scope
**Changed modules / tests (proposed scope, not changes already made):**
- src/toto_ai/sports_stats/v3_parallel.py (adopt accepted module separately)
- src/toto_ai/sports_stats/final_hybrid_comparison.py (future reviewed optional seam only)
- tests/test_sports_v3_parallel.py
- tests/test_sports_v3_comparison_connection.py
- tests/test_sports_v3_deployment_manifest.py (new)
- Tests: default-off/invalidmanifest/expired/version mismatch fallback preserves primary bytes; no outcome/payout input during inference; hard resource and deadline cancellation cleans owned workers only; current source/final inputs/model hashes checked before reuse and publication; no automatic operator release or strategy selection by realized hits; main existing four-way selector compatibility; extra research arm not silently added to operator IDs
**Exit criteria:**
- versioned candidate is integrated and demonstrably invoked in isolated prospective research stream
- protected5007 control/jobs/consent unchanged; not rolled out intraday merely because retrospective hits improve
- production qualification and exact future plan-bound owner consent separately satisfied before actionable use
- fallback/provenance/freshness/operator deadlines remain enforced; actual trained versus fallback lineage visible
**Why blocked / what is executable now:** No approved fitted real V3/evaluation manifest yet; full operator rollout is not implied by research adoption or code tests.
**Outputs, under task directory unless model module:** deployment/v3-manifest.json, deployment/acceptance.json, deployment/rollback-test.json

## Concrete validation commands and API entry points
All shell cwd: `/Users/turshevr/toto-ai`. Commands below are **future execution instructions, not commands run by this planner**. Use only `.venv` and verified native interfaces. Before writing anything, the solver binds the accepted review06 delta and its dependencies; no broad Git inventory and no applying the whole child patch over the current checkout.
### A: existing tool commands, executable only after exact modules/tests are adopted
```sh
.venv/bin/python -m pytest -q tests/test_sports_v3_probability.py tests/test_sports_v3_probability_features.py tests/test_sports_v3_f4.py tests/test_sports_v3_f4_metrics.py tests/test_sports_v3_generation.py tests/test_sports_v3_research_safety.py tests/test_sports_v3_library_isolation.py
.venv/bin/python -m ruff check src/toto_ai/sports_stats/v3_probability.py src/toto_ai/sports_stats/v3_draw_calibration.py src/toto_ai/sports_stats/v3_probability_features.py src/toto_ai/sports_stats/v3_feature_disposition.py src/toto_ai/sports_stats/v3_f4.py src/toto_ai/sports_stats/v3_f4_gate.py src/toto_ai/sports_stats/v3_f4_metrics.py src/toto_ai/sports_stats/v3_generation.py src/toto_ai/sports_stats/v3_research_safety.py tests/test_sports_v3_probability.py tests/test_sports_v3_probability_features.py tests/test_sports_v3_f4.py tests/test_sports_v3_f4_metrics.py tests/test_sports_v3_generation.py tests/test_sports_v3_research_safety.py tests/test_sports_v3_library_isolation.py
```
Tests/package names may be split only after dependency mapping; missing listed tests/modules is an actionable implementation gap, not instruction to silently skip them. Repeat imports with network/SQLite/process creation guarded; no full suite merely to show activity. The separate publication worker handles commits after required checks.
### B: proposed new interface; does NOT exist yet
```sh
.venv/bin/python -m pytest -q tests/test_raw_package_replay.py
.venv/bin/python -m ruff check src/toto_ai/research/raw_package_replay.py tests/test_raw_package_replay.py
.venv/bin/python -m toto_ai.research.raw_package_replay generate --manifest plans/TOTOAI-RESUME-20260915/replay5000-v1/research-manifest.json --output plans/TOTOAI-RESUME-20260915/replay5000-v1/generated
.venv/bin/python -m toto_ai.research.raw_package_replay score --frozen-generation plans/TOTOAI-RESUME-20260915/replay5000-v1/generated/frozen-generations.json --labels plans/TOTOAI-RESUME-20260915/replay5000-v1/labels.json --output plans/TOTOAI-RESUME-20260915/replay5000-v1/scored
```
Define/test these exact generate/score interfaces as standalone research module, not live CLI registration. Generate process receives no DB/labels/payout input. Score can only read immutable completed generation. Source parser and budget functions reuse native semantics. New labels.json is an explicit readonly export of known results, kept away from generation. If native optimizer requires a scheduler object rather than pure probabilities/config, extract/reuse a minimal pure shared call with byte-equivalence proof; do not forge a historical plan. Such extraction touching live imports waits until5007finishes.
### C: already existing native help, not an assurance of compatible retrospective input
```sh
.venv/bin/python -m toto_ai.cli backfill-sports-history --help
.venv/bin/python -m toto_ai.cli evaluate-sports-probability-shadow --help
```
The strict existing backfill contract rejects capture after as_of/deadline. Do not pass today fetched evidence as old captures. New offline corpus builder is a proposed module, not an existing native command; public official provider/endpoint and historical availability are explicitly NOT CONFIRMED. A bounded first source probe should output accepted/missing reasons on a small predetermined sample, not promiscuous scraping or a promise of complete coverage. No protected secrets or model services.
### D: existing isolated Python APIs to adopt and validate
`train_v3(records, target_drawing=..., prediction_as_of=..., training_domain=...)`; `validate_model(model)`; `load_model(text)`; `infer_v3(model,row,...)`; `run_f4(folds, output_dir=..., load_labels=..., training_domain=..., scope_receipt=..., expected_scope_receipt_sha256=...)`; `build_f4_gate(report)`; `validate_f4_gate(gate, expected_report_sha256)`. Native signatures come from model-context. Independent expected hashes must come from the actual review receipt, not be derived from the unreviewed object. Existing domain enum does not authorize reconstructed data: any new domain requires explicit versioned verifier semantics and tests, never relabeling as FROZEN_HISTORICAL_INPUT.
Current max7folds constraint is verified. The v2 proposal freezes the full requested drawing roster plus train prefix; fold_count derives from validated unique chronological roster, resource bounds declared before run. Eight targets remain eight rows even if some are unavailable/cannot fit; do not partition to discard failures. Validate train-admission thresholds from accepted native code; do not invent a lower minimum. Existing≤7fixtures retain prior computed numbers and legacy hashes under legacy version. New version necessarily has a distinct manifest. Statistical bootstrap stays drawing-clustered; eight clusters/120events do not establish rare13+/15profitability.
### E: existing commands that must NOT be misused for missing inputs
```sh
.venv/bin/python -m toto_ai.cli replay-quality-v2-v3 --help
.venv/bin/python -m toto_ai.cli replay-quality-sports-v2-robust --help
```
Those commands require historical plan/final-input/baseline (and sports). The proposed research comparison module has a separate contract. No fake flags/paths are given to existing replay commands. `.venv/bin/python -m pytest -q tests/test_research_five_arm_comparison.py` validates the future wrapper; `generate_v3_candidate(...)` remains gated research only. Final F wiring requires focused existing parallel/selector regressions plus new manifest tests, not a checkbox based on a successful import.

## Metrics and evidence decisions fixed before execution
- Predictor diagnostics: multiclass logloss, sum-Brier, draw-class Brier/reliability, non-draw losses, calibration/ECE under fixed bins; train-only calibration, separate coverage/missing/fallback slices. No duplicate predictor evaluations counted as independent just because optimizer names differ.
- Package diagnostics: exact unionP13+/P14+/P15 on one common frozen probability matrix, with event-independence assumption explicit; separate self-model estimates so Sports probabilities cannot make its own package appear automatically superior. No independence assumption between overlapping coupons. Category13=distance≤2,14≤1,15=exact. Actual max/mean hits and counts9–15 after freeze; drawing hit-rate numerator/denominator separate from coupon counts.
- Paired effect/uncertainty at drawing cluster level; model tuning only earlier/inner folds, fresh untouched prospective evaluation for promotion. Existing proposed C3 upper95%Δlogloss criterion needs protocol confirmation before run and cannot replace stricter current gates. If sampling/CI insufficient, INCONCLUSIVE. No zero-filling unavailable models, no best-model selection using target outcomes.
- EconomicROI only verified official coefficients/receipt→exactcouponhash mapping and native rounding/refund/tax policy; UNKNOWN when absent. No outcome-based or expected-value proxy as realized money. Larger nominal bank not evaluated by pretending earlypool allows it.

## Which improvements are justified by4999 numbers?
No measured lift supports changing all five algorithms from this n=1 result. All four reached11/15; sports-shadow31 versusqv3 24 versusqv2/robust9 coupons9+ is descriptive. Immediate justified engineering work is complete provenance/evaluation and actual model adoption, not tuning to these outcomes.
- quality-v2: preserve exact control. Train-only market calibration is a hypothesis, evaluated as a separately versioned probability input, not silently rewrite control.
- quality-v3: investigate P13/P15 trade-off and concentration on frozen common inputs; do not weaken the selector because this one past draw had a higher rawP13 estimate.
- robust: emit original/candidate hashes, refinement status/applied, precise existing fallback rejection/timeout/safety reason. If reason is absent sayUNKNOWN and add a regression for provenance; identical bytes are an unchanged fallback, not a distinct successful model.
- sports-shadow: verify sportinput coverage/time/identity and ablate calibrated/bounded residuals; more9+coupons on one draw does not establish predictive superiority.
- SportsV3: integrate and exercise the actual accepted predictor code, produce genuine fitted manifests when source evidence permits; never rebrand current SportsV2/data pipeline as trainedV3.

## Reporting and first solver handoff
At each completed/bounded step report DONE / RUNNING / REMAINS / BLOCKER / NEXT exact checkpoint and artifact. Parent provides operational chat status; no nested tasks or new monitors from model jobs. Implementation and review receipts remain separate from this planning receipt. No guarantee of PLAY/13+/profit.
**Current first task: R1a thenR1b in retrospective-reconstruction-protocol.md.** Task_idTOTOAI-RESUME-20260915. Build only the proposed inactive closed-market scenario adapter/runner and focused tests; hash-bind sanitizedRAW→nativeEVSurface, no labels to generator, no archived/live provenance bypass. Independent review, then first4999 3-arm4980/166 pilot and5000–5006 bounded sequential continuation. R2 exact sports reconstruction is independent, not a prerequisite forR1. A already completed: do not readopt/retest oldlibrary merely because the old first-task text said so. No nested workers or publication within implementation assignments.

No new project audit, source search, history fetch or paused task resumption is part of this plan.
