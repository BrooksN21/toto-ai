# B: RAW loader GREEN; model generation explicitly BLOCKED

Task **TOTOAI-RESUME-20260915**. Stage B is **not complete**: its input-only slice is complete. No claim that three/five models were tested.

## Written and verified
- `src/toto_ai/research/__init__.py`
- `src/toto_ai/research/raw_package_replay.py`
- `tests/test_raw_package_replay.py`
- Focused pytest: **22 passed in 0.50s**, exit0. Ruff check: **passed**, exit0.
- Read-only genuine5000RAW verification succeeded (archive payload/metadata/snapshot binding; original capture before Moscow T-10; active identity; strict empty outcome sentinels). Whitelist projection drops results, scores, payments and unknown fields before creating immutable input. BK and crowd matrices use existing native conversion.
- Native pool78748 caps requested4980 at **780 RUB / 26 coupons / stake30**. This is an early-pool stress input, not a4980package benchmark.
- Export: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/B-raw-adapter/input5000/research-input.json`.
- File SHA256: `f9ce1e70f2259a7b6b78c4d3bd53831d6904427a1dd8ad3adc8ea9ef4423f45c`.
- Semantic input SHA256: `bef6c6484d4dec864608780a85ae876adda1ff9fd049a46efc816f41980b7e8b`.
- Admission: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/B-raw-adapter/input5000/generation-blocked.json`.
- All outputs are **CURRENT_CODE_RETROSPECTIVE_REPLAY_NOT_PROSPECTIVE**, operator_compatible=false, automatic_wagering=false. No FinalInput/SchedulerPlan/consent created.

Exact command (choose a previously nonexistent output directory):
```sh
.venv/bin/python -m toto_ai.research.raw_package_replay prepare --manifest reports/rehearsal/TOTOAI-RESUME-20260915/B-raw-adapter/manifest.json --output reports/rehearsal/TOTOAI-RESUME-20260915/B-raw-adapter/input5000-verify
```
`prepare` exits0 for verified **input-only** export; `generate` writes the same honest blocker receipt and exits2. It does not pretend to generate packages. No generation timeout/exhaustiveness claim is applicable.

## Single blocker and exact native seam
**GENERATION_BLOCKED: native quality-v2 provenance/core coupling.**
`src/toto_ai/ev/package.py:317 _select_safety_aware_package` calls `ev/package_quality.py:269 validate_selection_provenance` at lines386–397; lines398–434 add provenance errors to structural infeasibility and return an infeasible package. Missing5000historical scheduler/ledger cannot be invented. Operational admission must remain unchanged.

`optimizer/strategy_historical_benchmark.py:151 historical_ev_config` sets mode=research; `ev/package.py:244` then selects plain EVtopN, skipping safety-aware quality-v2. This shortcut is **not parity**, tested explicitly. Neither it nor budget-oracle was used for generation.

Quality-v3 and robust have numeric helpers (`uncertainty_package.py:97 select_uncertainty_package`, `robust_package.py:70 select_robust_package`), but exact control/anchors are missing. Production robust also includes sports probabilities/candidates; absent sports cannot be replaced with BK under the sports model name.

## Narrow next-stage design for review — NOT implemented
1. Extract the existing safety-aware numeric selection from its operational artifact wrapper; move rather than duplicate optimization, preserving thresholds, EV eligibility, objective, tie-breaking, sampling and seeds. Keep all scheduler validation/failure behavior in the existing wrapper.
2. Add a distinct immutable **ResearchGenerationContext**: verified RAW input hash, explicit numeric config, explicit seed, false operator flags; not historical scheduler/consent/provenance. Do not silently toggle provenance_required to green.
3. Both validated contexts call the same pure core. Bind research context hash separately from probability-only hash. Apply native pool cap and reject missing numeric fields.
4. Prove unchanged operational behavior and exact ordered coupon parity on existing4999frozen input/config/seed **without outcomes**, plus failure-path tests. Only then use5000input.
5. Generate qv2/qv3/robust under declared same-budget/control/seed rules, freeze coupon hashes before loading separate actual labels. Sports branches remain SKIPPED until valid inputs exist. Report identical robust/control as identical, with actual fallback/selection reason, not a distinct-model gain.
6. Native-core extraction changes existing code; requires **separate review/stage**, not a silent pre5007refactor in this worker's scope. Current loader/export can be reviewed independently now.

## Current result / handoff
quality-v2, quality-v3, robust: **NOT_RUN**. sports-shadow and Sports-v3: **SKIPPED_NO_SPORTS**. Packages0; parity4999not run; no outcomes read/scored; ROI unavailable. No lift claim, training, oracle, DB writes, scheduler/liveCLI edits, consent/operator writes, A9changes, ACTIVE_PLAN edits or Git operations. No process left running.

Publisher: B test and research directory are now GREEN but were excluded while unfinished; review these exact paths separately. File/output hashes and checks are in `B-raw-adapter.json`. Next solver scope is reviewed core extraction, **not another RAW audit**.
