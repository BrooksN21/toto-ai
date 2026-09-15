# C — native validation checkpoint 2026-09-15T14:41:10.462313+00:00

## Executed, no new API calls
- 50/50 sources PASS native history validation and DB payload-hash binding;500/500 historical rows retained; no raw-integrity rejections.
- 4999:26 raw snapshots,13/15 event-level feature rows; actual final input/plan/BK15 native PASS. Source capture06Sep strictly precedes07Sep17:00MSK input and17:20 cutoff.
- 5007:24 raw snapshots fromtoday16:45MSK,12/15 feature rows; early training input/plan/BK15 native PASS. Data asof17:20MSK; this is NOT evening-final equal-input comparison. Captures remain before19:50 cutoff.
- Zero API/DB/code/scheduler/consent mutations. Existing raw bytes copied exactly into ignoredfrozen-raw; source timestamps and updatedAt preserved. Labels physically separate; validator script does not load labels.

## Integrity versus permission/coverage
- Native _load_history_snapshot, v3_probability_features._history, build_team_window, build_sports_v3_feature_table and augment_observed_features actually executed.
- Full build_v3_predictors called25 times:25 explicit `independently reviewed reference required` rejections. Independent gender/age/squad review references were NOT fabricated.
- run_f4 early no-authority branch returned BLOCKED_MISSING_TRAINING_EVIDENCE/fit_executed=false; label loader nevercalled, fit output nevercreated.
- 5000–5006 still105 rows without verified native mappings/raw; two4999 targets also missing. These are missing-coverage cases, NOT50bad raw files. F4 coverage metric not evaluated until folds exist; currentmax7folds differs from requested8.
- SportsV2 bound input still NOT_VALIDATED; no claim SportsV3fit-ready or model improvement.
- EarlierfileSHAversusDBpayloadSHAcomparison was comparing different objects; nativepayloadhashbindingnow50/50PASS.

## Concrete fields and artifacts
{"4999": {"37/53": 1, "41/53": 12}, "5007": {"37/53": 2, "41/53": 10}}

- sources: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/source-validation.json`, SHA256 `7a48234e2ad9d9c95e3b5e4879381ce719018eabf1660d509d0cd0ee4d074486`
- features: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/features-no-labels.json`, SHA256 `699bd6e2edefea43d401f19f42658f626ca26a3d80193da7d91677df38163bf6`
- ledger: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/readiness-ledger.json`, SHA256 `6fecb6cdc2406c448cad4d5048936d8702b0cb5aca445e4d16f06bf7d011c98f`
- inputs: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/input-validation.json`, SHA256 `b54c35baeb678120b1cf1f3d16a9dd29d0dc52b4f8d0e8f68066910510aeb269`
- f4_gate: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/f4-no-authority-receipt.json`, SHA256 `de300634fbb07eb0b1aa68de4b27efe862386acd0f861b6cf32331730515f16e`
- native_fit_contract: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/native-fit-contract.json`, SHA256 `814017502e8e793de5847e13f99d60ed311d21e572fd10dc87990d41625456ac`

## Next minimal step
Independent review of exacttarget/raw/scope refs, validate equal-inputV2 and construct sealed event/fold inputs following native-fit-contract.json. Missingopponenthistories/standings/BKmargin remain explicit. No fit, no further API calls, no worker processes running.

## Final bounded reference/V2 checkpoint 2026-09-15T14:51:17.646801+00:00

- Native bound schedule ledgers PASS for both drawings;15/15 review documents each match hashes. Supporting non-GOAL sources exist. This is not absence of schedule data.
- None of those schedule receipts directly binds newly derived target_projection + event-local raw team-history bytes in ReviewedReference format. Independent-reviewed bridging input not connected/approved; not fabricated.
- Strict historical gender/age_group/squad_type:0/260 complete for4999,0/240 for5007. Target men-senior declaration alone cannot establish scope of every historical row. Raw integrity still50/50PASS.
- 4999 V2 native load/hash/identity/asof/15 probability triples/final-input/plan binding and native probability_input_sha256 PASS. Sealed honest research V2 derivation saved: /Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/v2-4999-f4-derivation.json
- 5007 seven early V2 artifacts load, but all fail same-input chronology against13:42 input: sports artifact was captured after final input. Final V2 not created. This does not mean raw invalid or evening scheduler failed.
- Full F4 dataset ready=false;fit_executed=false. Previous native no-authority receipt stands; no training performed.
- Additional precise input defect: research target_projection misses required final_input_sha256. New projection must bind actual existing native final hash, not rewrite old source.
- Metadata: /Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/C-data-assembly/reference-v2-checkpoint.json SHA256 78f351d621eda0e8ef02d6d43c1f62fdaad6dd3a0ccf39441270974b1fc8e40e
- No API/code/DB/jobs/source timestamp changes; no worker processes left.
