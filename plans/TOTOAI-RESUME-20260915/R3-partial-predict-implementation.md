# R3 partial retrospective prediction — completed, pending review

Task TOTOAI-RESUME-20260915. 2026-09-16T10:19:56.025295+00:00

Frozen A5 was not refit. Original model/helper/native source hashes unchanged. Source freeze was explicitly released before the two new files were written. No production registration, scheduler, DB or consent changes.

32 targeted tests PASS; Ruff PASS. Final source hashes: `898cb0780e31bf3abe8d66e7ecbd44fbe849a6ea0a163e5c3396800cdce735c0` / `6f9db3117f0346f9795b2e05b6a1dd83c067dac541f98d362c533f19362285c9`.

## Actual evaluation

120 predictions frozen at 2026-09-16T10:17:17.971407+00:00; labels parsed only afterward, scored at 2026-09-16T10:19:00.139764+00:00. 21 identity approvals → 21 actual Sports applications;99 unchanged BK. All21 probabilities differ from BK. No target labels entered fit/prediction.

Prediction physical SHA: `96f17a43bbb83bdefe5aed27b202ff19bfd5741471b1edfdd37cf517a101c091`. Payload SHA: `a73f1a0bfd92148866ff74e115318425e9bef6d9063df3b9d657aca3246b41cd`.
Model physical SHA: `f334b21efd5dfd369c530d7e037b7c9ac8e6ee087d235872ac42453579d37b0e`. Model payload SHA: `8381fcf507c77152835e69325c46e446d40e5acb163bf019f03ea1c16d74fdde`. Different hash roles checked separately.

|Scope|Events|Mixed log loss|BK log loss|Mixed Brier|BK Brier|
|---|---:|---:|---:|---:|---:|
|All events|120|1.074516916|1.066438748|0.650455100|0.644661891|
|Sports applied only|21|1.155661938|1.109500983|0.707402975|0.674298928|

Lower is better. Both aggregated proper scores worsened; this is not a calibration improvement. Eight already inspected draws are not a blind test; quote-asof is unknown for all120. Training draws precede evaluation, but no historically available/prospective or profitability claim follows.

## Per-draw coverage and scores

|Draw|Sports/BK|Mixed/BK log loss|Mixed/BK Brier|
|---|---:|---:|---:|
|4999|13/2|1.081925/1.061207|0.660279/0.641298|
|5000|5/10|1.060418/1.052525|0.642261/0.636429|
|5001|1/14|1.135780/1.136531|0.691510/0.691250|
|5002|0/15|1.058562/1.058562|0.641404/0.641404|
|5003|0/15|1.028362/1.028362|0.617998/0.617998|
|5004|2/13|1.137354/1.100588|0.690003/0.668731|
|5005|0/15|1.033706/1.033706|0.622615/0.622615|
|5006|0/15|1.060029/1.060029|0.637571/0.637571|

## Handoff

Exact inputs, frozen predictions, pre-label receipt, post-freeze label bindings, metrics and one-shot scorer: `/Users/turshevr/toto-ai/reports/rehearsal/TOTOAI-RESUME-20260915/R3-fit/evaluation-v1`.
`prediction-request.json` pins both independent identity reviews and original input manifest. Original UNKNOWN rows/archives are not mutated; identity-only derived copies are sealed inside inference. Native 15-Sports-DTO contract is untouched; a separate 15-market-slot roster is enforced per drawing.
No operator/default registration or packages produced. Next: independent review and separate publication. Do not select/refit parameters on these already seen outcomes. Broader five-arm comparison remains separate work.
