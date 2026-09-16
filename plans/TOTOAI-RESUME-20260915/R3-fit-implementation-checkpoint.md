# R3 retrospective A5 — partial implementation checkpoint

Task TOTOAI-RESUME-20260915. No fit or model artifact claimed.

- Implemented only new research preparation module and focused tests:16 PASS; Ruff PASS. Existing production A5/features source hashes unchanged.
- Reuses native `_transform` (train-only medians/scales/missing indicators), authentic BK inputs, distinct retrospective schema/domain. Completion-before-evaluation and per-row history-before-decision checked; canonical train/heldout overlap forbidden. Exact row hashes must come from an independently verified set, not inferred from self-sealing or identity booleans. Unknown identity receives zero weight; unknown taxonomy/late fetch/unknown availability stay explicit.
- Current minimum >=3 full earlier drawings/45 rows AND positive-weight rows. All53 feature keys must exist (optional missing values remain null). No requirement that45 rows have full sports features. Only eligible train rows fit the transform. Heldout labels are not accepted by this API.
- API: `prepare_fit(records, heldout_rows, target_drawing=4999, prediction_as_of=<UTC>, independently_reviewed_hashes=<trusted reviewer set>)`. Each record has separately sealed `features` and `label`; exact field schemas in module ROW_FIELDS and label allowlist. Tests demonstrate schema, not genuine input evidence.
- Required data worker bridge: use real archived train groups4990/4992/4993/4995 with true canonical fixture IDs/BK/labels, source hashes, actual fetched_at, proven-or-null historical feature/quote/label availability, completion bounds and independently checked identity lineage. Do not generate a trusted review set from all data-row hashes without review. No class invention, fake FROZEN/SYNTHETIC production row or label backdating.

## Exact blocker / minimal next action

The A5 optimizer is embedded inside `v3_probability.train_v3`, not exported as a pure numerical helper. New-module-only scope cannot reuse it without duplication or falsely admitting retrospective rows into native gates. Preparation therefore returns `BLOCKED_SHARED_A5_KERNEL_EXTRACTION`, weights=[], fit_completed=false. This is unfinished fitting, not a model.

Request narrow scope expansion: mechanically extract that existing numerical loop into a shared helper, call it from native A5 unchanged and from research adapter, with exact old-vs-new numerical parity and unchanged production admission tests. No allowed-domain/feature-validator/reliability/release changes. Native inference arithmetic also remains unchanged; research serialization/inference is distinct. Do not use monkeypatching/dynamic source compilation to evade this boundary.

Once permitted and independently reviewed: finish fit+sealed prediction API, consume verified60-row matrix if available, train before4999, freeze predictions for4999–5006 before loading their labels. Report learned weights/model hash/eligible counts/logloss+Brier and source-availability limitations. These eight known outcomes are not blind holdout or profit evidence. No runtime/DB/scheduler/consent/sidecar registration or Git publication happened here.
