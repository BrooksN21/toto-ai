# Sports V3 frozen CORE — independent review: REQUEST_CHANGES

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. 2026-09-06T17:50:34.738889+03:00.
Only frozen `SPORTS_V3_PROBABILITY_CORE_SNAPSHOT_01.patch` reviewed, SHA256
`07cfc27001e5b1d830388777c25ecf5ce49907924694e2798f97b1157c45d88c`. Manifest status FROZEN_INTERMEDIATE_REVIEW_NOT_FULL_COMPLETION.
All9 reconstructed bytes verified against after hashes and write-protected; no ongoing
author source read or mutation. Isolated review workspace: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/sports-v3-core-review-de4hiiw1`.

## New P1 findings (not the already-known eligibility defect)

### P1 — stale/foreign final BK accepted by native generation
Frozen `src/toto_ai/sports_stats/v3_generation.py:72–97` checks inference/model/bundle
hashes and only drawing identity for the supplied frozen payload. It never binds
that payload's ordered events/BK vector/capture to inference.final_input_sha256 or
its probability_input_sha256. Lines139–141 then attach the *old* inference final hash
to a candidate generated/evaluated under the independently supplied payload.

Independent fixture: keep legitimate synthetic request/inference from final BK
`[0.2,0.3,0.5]`, change only frozen_payload event BK to `[0.8,0.1,0.1]`. Generation
succeeds (3synthetic coupons), reports final hash `dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd`, and computes
exact_final_bk control/candidate metrics against the changed payload. No resealing
of inference is needed. Ordinary stale inference/new final input mixing can therefore
create internally inconsistent provenance and apparent same-input comparisons.

**Required correction:** bind the actual frozen serialized input/hash and ordered
per-event BK/identity to the inference context before invoking either constructor;
carry/validate exact plan/bank/stake/capacity and reject mismatches. A hash field copied
from inference is not validation of the payload consumed. Add the supplied changed-BK
regression and event-order/capture/financial-binding variants. Do not change math or
primary while fixing this adapter boundary.

### P1 — serialized training chronology is trusted without validation
Frozen `src/toto_ai/sports_stats/v3_probability.py:383–453` validates seal/version/
shapes/authority flags but not training_rows.label_available_at against prediction_as_of,
training metadata/count consistency or its model-fit evidence. Infer:488–495 checks only
train_drawings and model prediction_as_of, so contradicting serialized label chronology
is not caught. Recomputable self-hash detects byte edits, not semantic consistency.

Independent fixture: train a legitimate synthetic A4 model, set a serialized training
row's label_available_at to2099-01-01, reseal, load_model, infer for2025-01-11. Loader
accepts and inference returns PREDICTED_EXPERIMENTAL instead of rejecting/falling back.
This is an intentionally internally inconsistent serialization, not an assertion that
the current train_v3 call itself used a future label. The train API correctly rejects
future labels for A3/A4; loading/reusing an artifact must preserve that same boundary.

**Required correction:** validate serialized chronology, train/target IDs/counts,
training domain/config and row bindings; require the expected trusted model/training
manifest hash at the integration boundary rather than treating a newly self-sealed
model as approved evidence. Add load/infer regression with this exact inconsistent
training record. Do not fabricate or rewrite a historical label timestamp.

## Positive findings / deliberately limited coverage

Synthetic fit produces learned nonzero residuals and deterministic serialization;
current BK is the logit prior, not V2 double blending. Target numeric checks passed:
finite positive normalized output, L1 cap<=0.20, exact-BK source-rejected fallback,
frozen model/transform unchanged by inference. Training labels are checked before
fit, and imputation/scaling/draw calibration use earlier eligible training rows,
not target rows. This does NOT establish an F4 ablation/calibration acceptance gate.
Native `run_bk_probability_only` generation consumes V3 arrays and produces a new
synthetic candidate; not merely rescoring. However, final-input binding above blocks
acceptance. Optional parallel path is default-off; timeout returns control and
operator/activation flags stay false. No P0 reproduced in this bounded scope.

## Existing blocker and incomplete integration

Known review: `/Users/turshevr/.codex/worktrees/ab34/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/SPORTS_V3_ZERO_ELIGIBILITY_REVIEW.md`.
Its blanket/per-family scope issue remains BLOCKING pending a reviewed corrected delta;
not duplicated or retested as a new finding. The frozen manifest also explicitly lacks
comparison connection/generated-candidate worker wiring, historical F4 ablation/gate
harness and adversarial hardening. Therefore no whole-V3 or operational acceptance.
No fitted real model, forecast quality improvement, finalPLAY or activation claimed.

## Executed checks / preservation

Initial run14PASS/1review-fixture error0.54s; the fixture incorrectly added unsupported
FrozenStrategyEvent.event_name. Fixed only that reviewer fixture (retained BK mutation);
second run12PASS0.75s includes corrected reproduction, proof writer and10parallel cases.
One proof writer repeated:25unique successful pytest cases overall, not the author's
full41-case suite. Two P1 reproduction tests intentionally assert observed unsafe
acceptance to record proof; their PASS does not mean the product is accepted.

Ruff9frozen files PASS with explicit snapshot/main source roots. Initial4I001 were
relocation first-party discovery effects; no rule disabled or candidate reformatted.
Patch/9file hashes remain exact. Network/SQLite/secret access denied by isolated guard;
no real fit/replay/forecast, API, source/DB/scheduler/authority mutation or publication.
Proof: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/sports-v3-core-review-de4hiiw1/independent-proof.json` and `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/sports-v3-core-review-de4hiiw1/independent-proof-rerun.json`.
Receipt: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/SPORTS_V3_CORE_INDEPENDENT_REVIEW.json`. Source line numbers refer to exact reconstructed candidate files.

NEXT: return findings to author; require exact corrected immutable delta for scoped
rereview (including known eligibility correction). This review job is complete; no
agent waits, nested delegation, publication or additional work selected.

## Frozen02 bounded delta checkpoint — 2026-09-06T17:52:07.716219+03:00

SHA256 `ad58f76361c37b4e61ea16a4fc76c25a19f2e99fcc6be73f95d6f7f2244baf6c` verified.
Both P1-bearing modules v3_probability.py and v3_generation.py are byte-identical
to reviewed01; findings/line references remain applicable. No test rerun needed to
establish byte identity, and no independent43-test/whole02 acceptance is claimed.
Static delta adds optional comparison hook (defaultNone, after unchanged selector,
exception=>control fallback) and optional generated-candidate worker call. The new
caller passes context/frozen BK together, but does not repair the generator's absent
input validation or the loader's chronology validation. Integration is only statically
inspected, not certified. Known family-scope issue also remains blocking.
Verdict remains REQUEST_CHANGES; no provisional kernel/full-V3 ACCEPT.
Progress saved before delta inspection, then updated: `/Users/turshevr/toto-ai/plans/TOTOAI-4998-PARALLEL-INTEGRATION-20260906/SPORTS_V3_CORE_REVIEW_PROGRESS_02.json`.
No source fixes, new tests/fit/runtime/network/DB/main-code changes. Return now.
