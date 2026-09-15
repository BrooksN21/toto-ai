# Sports V3 settled-label evidence — context only

Task TOTOAI-4998-PARALLEL-INTEGRATION-20260906. Saved 2026-09-06T17:12:38.853697+03:00.
**Found:90/90 settled labels for4990–4995, plus15/15 for4996. Missing backfill
manifest references do NOT mean missing project labels.** Read-only DB and exact
saved result/attribution/feature pointers used; no API/model/test/VCS calls, no
DB/source/runtime/authority edits. Only this report created.

## Proven local result records and availability

DB: `/Users/turshevr/toto-ai/data/toto.db`, opened URI `mode=ro`, `PRAGMA query_only=ON`.
Table `drawing_result_snapshots`; exact row IDs below. Each is complete,15 unique
orders0..14,15 resolved1/X/2 results, no void. These strings are **labels, not coupons**.
`results_available_at` is conservatively the stored **retrieved_at** observation,
corroborated for4990–4995 by matching post-draw-state.updated_at and
review-request.requested_at /actual/snapshot digest. It is NOT inferred from ended_at,
match kickoff, directory date or mtime. No earlier availability is claimed.

|Drawing|DB drawing_id|Snapshot row id|Labels|results_available_at UTC|Actual outcomes|
|---|---|---|---|---|---|
|4990|12077|431|15|2026-08-30T09:10:29.255105+00:00|22X12X11212X21X|
|4991|12081|432|15|2026-08-31T09:00:10.496625+00:00|X1112X21112X221|
|4992|12083|433|15|2026-09-01T09:00:08.328659+00:00|1112XXXX2211XX1|
|4993|12086|434|15|2026-09-02T09:00:05.578334+00:00|22XX12X2X121XX2|
|4994|12089|435|15|2026-09-03T09:00:03.651343+00:00|2X11112222X1XX2|
|4995|12092|436|15|2026-09-04T09:00:10.969381+00:00|X2111X1222XX22X|
|4996|12096|437|15|2026-09-05T09:03:38.395667+00:00|X222XX2111112X2|

All90 feature-manifest event IDs/orders match DB labels exactly; all90 attribution
outcomes match DB labels. Six frozen final-input file hashes and six attribution
file hashes match the canonical aggregate's recorded references. Attribution
final-input semantic hashes match its BK-input references. Per-record checks below
explicitly report whether result_digest also matches; no generic digest equivalence
is assumed. No new raw snapshot extraction or label-manifest construction performed.

## Use for4998 versus honest historical validation

- For a genuinely **current**4998 prediction with prediction_as_of after these saved
  retrievals (including current Sep6 pre-draw input), all six draws'90 label rows are
  temporally available. Even the optional4996 labels were retrieved Sep5. **Labels
  available is not features eligible**: retain4990 source rejection,4991 missing/
  chronology restrictions, strict identity/coverage and cold-start gates.
- Frozen feature/history as_of for each training draw is its own pre-draw boundary;
  its label is normally observed later. It need only be available by the *subsequent
  prediction fold's* as_of, never forced to be before its own kickoff. Still keep
  target labels entirely out of feature construction, tuning and scoring-before-freeze.
- For retrospective folds use only earlier drawing labels satisfying recorded
  retrieved_at<=target prediction_as_of. Availability-only matrix (not a declaration
  that all these rows pass the separate feature gates):

|Target fold|Frozen Sports as_of|Earlier labels proved available|Available rows|
|---|---|---|---|
|4990|2026-08-28T15:37:40.472172Z|none|0|
|4991|2026-08-29T14:27:40.325631Z|none|0|
|4992|2026-08-31T13:00:18.142034Z|4990, 4991|30|
|4993|2026-09-01T13:30:13.640481Z|4990, 4991, 4992|45|
|4994|2026-09-02T13:30:06.081128Z|4990, 4991, 4992, 4993|60|
|4995|2026-09-03T14:55:12.104098Z|4990, 4991, 4992, 4993, 4994|75|

The minimum3complete prior training drawings/45events is unchanged. Availability
counts alone do not satisfy complete usable-feature training requirements.
4990–4995 remain design-informed development replay, not newly untouched OOS data.
4996 is permitted by the saved plan as a separately bound extension after verified
terminal results, not automatically in this six-draw manifest; matching results are
now present. Its frozen feature/BK extension and any pre-result candidate fixation
must still be verified before training inclusion / an untouched-holdout claim.
Do not move the 4998 prediction_as_of forward just to admit otherwise-late labels.

## Exact data links for implementation owner

Feature source manifest:
`/Users/turshevr/toto-ai/plans/TOTOAI-SPORTS-HISTORY-PERSISTENCE-20260904/backfill-4990-4995-manifest.json` (file SHA256 `07463e8831c8e1cbcd146b9243555c2efce72a160b4c527c3243573ade270e49`).
Join via snapshot.drawing_id/number and events.target_event_id + event_order;
DB events_json carries event_id + order + result + result_status. Existing six-draw
aggregate `/Users/turshevr/toto-ai/reports/research/sports-v3-4990-4995/attribution-aggregate.json`
links exact frozen BK/final inputs and attributable outcome rows; it is a derivative
label cross-check, not evidence of earliest result availability by itself.

The following compact records provide exact DB selectors, source paths, file and
semantic hashes, retrieval evidence and frozen input joins. **Stored result/raw
hashes are different domains.** raw_snapshot_sha256 is null for all seven legacy
records; no independent raw snapshot linkage or cryptographic historical timestamp
attestation is invented. DB payload_json exists, but was not exported or inspected.
Mutable review status can change request hashes: use actual file SHA and matching
snapshot/actual fields; do not assume historical state.review_request_sha256 equals
current mutable request contents. Integrity verification for a new immutable training
manifest remains the separate implementer's job; this report is not such a manifest.

```json
[
  {
    "id": 431,
    "drawing_id": 12077,
    "drawing_number": 4990,
    "retrieved_at": "2026-08-30T09:10:29.255105+00:00",
    "ended_at": "2026-08-29T16:30:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "22X12X11212X21X",
    "snapshot_sha256": "e3de2904167837582275df72354ceaa90c499c873b921557b47f6beae4d4381d",
    "result_sha256": "17e63d6262e25a31042be88d5e66a19b5dfd31b10ed12bfa2a3edf4c447872a3",
    "payload_sha256": "cc82972848fb39108c7e237475d31c3708033ce549cb94d052ebb281abbf4a59",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-08-30T09:10:29.255105+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "review_request_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4990-20260829T163000Z-recovery-20260829T1439/post-draw/review-request.json",
    "review_request_file_sha256": "ec4f1bc15ee3605ead4a1a0ff8a9b52122d2fb118390f56561bb9769da53e010",
    "post_draw_state_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4990-20260829T163000Z-recovery-20260829T1439/post-draw/post-draw-state.json",
    "post_draw_state_file_sha256": "0231dff4e7ec756fa9842066d9197ecc309ee60735716b79ec6217ecefce2e6c",
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/constrained-hybrid-replay-v2/4990/historical-hybrid-attribution.json",
    "attribution_file_sha256": "94a448cc1af19ea6e69d13fd67d7d580c41a52cc04a80bc892e5d80493e36520",
    "attribution_actual_result_sha256": "2ef6ecc19de958ad940aa6b237cf8393d332b419f0a8618a9efef20df2e0efca",
    "result_digest_matches_attribution": false,
    "final_input_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4990-20260829T163000Z-recovery-20260829T1439/attempts/final-01-20260829T130002969207Z-520601d2/final-input.json",
    "final_input_file_sha256": "f8e46095f919586245e7939a2c9b0ad344a535cff3a6d9e25e386a14e0064932",
    "final_input_semantic_sha256": "5500b7c2f9c95cda534729ced4521064ae97b2f97bd71fa709ac9548ca580077",
    "probability_input_sha256": "d4a52b5050285eeb574569c6ff9df8f46f9ab4f69c9be7bf84e3af2e97664875",
    "feature_manifest_as_of": "2026-08-28T15:37:40.472172Z",
    "feature_to_label_event_id_order_join": "15/15 exact; drawing id verified",
    "label_to_attribution_outcome_join": "15/15 exact"
  },
  {
    "id": 432,
    "drawing_id": 12081,
    "drawing_number": 4991,
    "retrieved_at": "2026-08-31T09:00:10.496625+00:00",
    "ended_at": "2026-08-30T16:00:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "X1112X21112X221",
    "snapshot_sha256": "541e8144ff0a35375cc0ae0c98e1f77a0df3e16357462d23fea44bdc95af95fc",
    "result_sha256": "20df04b5ff69dc495be082e1952cac86a0c81e4e77b80cbf47aaf90a727448b2",
    "payload_sha256": "72e2d1a0a6b312238f9f480e154c5a3adced7efab5fee66b29a327d3f4866afd",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-08-31T09:00:10.496625+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "review_request_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4991-20260830T130000Z-recovery-20260830T1538/post-draw/review-request.json",
    "review_request_file_sha256": "c5846685dbe6ecd6bbac3c3982eb0bba1623f1e7d76cef71bbec98b0a1919a30",
    "post_draw_state_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4991-20260830T130000Z-recovery-20260830T1538/post-draw/post-draw-state.json",
    "post_draw_state_file_sha256": "ef32d730fbf3c7d4d6e648d908394ea38a329c3070958249bddffc2f47b31bea",
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/constrained-hybrid-replay-v2/4991/historical-hybrid-attribution.json",
    "attribution_file_sha256": "911b95c945de7d336afad4effb35ef0632a6d42e7801470d18f1030c53e7847c",
    "attribution_actual_result_sha256": "c8b71bd676fc74e50b5855c5f5672ca9e3e1718a0ad7f58c7d3eb54fc99e93cb",
    "result_digest_matches_attribution": false,
    "final_input_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4991-20260830T130000Z-recovery-20260830T1538/attempts/final-01-20260830T123821298809Z-be16c5f9/final-input.json",
    "final_input_file_sha256": "74e23e1fbc4bdd3bb1e30e3c1d366a60a20f06fb6d106e3b7f73d2278a99e813",
    "final_input_semantic_sha256": "3ce5c9efcc9192c4ca6655ab19029f357564414fae1fe4ad42235642bc21c5db",
    "probability_input_sha256": "4c0f0ccbeec1610cb2c3d31c8f50df2d87e263b674b289366928cb26f94fb503",
    "feature_manifest_as_of": "2026-08-29T14:27:40.325631Z",
    "feature_to_label_event_id_order_join": "15/15 exact; drawing id verified",
    "label_to_attribution_outcome_join": "15/15 exact"
  },
  {
    "id": 433,
    "drawing_id": 12083,
    "drawing_number": 4992,
    "retrieved_at": "2026-09-01T09:00:08.328659+00:00",
    "ended_at": "2026-08-31T16:30:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "1112XXXX2211XX1",
    "snapshot_sha256": "6a22463a0b60701a8013b2ba45975c20dfaea5c936540a5270f995b76c8fd989",
    "result_sha256": "2c4a9fcab5f0fb024314f2fa169db69c43387e0f9a02909db2578c9f234c83ec",
    "payload_sha256": "60241d972149e2093e4d1087c4ac5960b2de2642a19ee05673f5a3268ef966b3",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-09-01T09:00:08.328659+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "review_request_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4992-20260831T133000Z/post-draw/review-request.json",
    "review_request_file_sha256": "fecd4552d43b2ff1c6c70ab5a24b86d5693eba767b5c01fcf482ac9d4c201141",
    "post_draw_state_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4992-20260831T133000Z/post-draw/post-draw-state.json",
    "post_draw_state_file_sha256": "092a105933863cda29cab1b6c8779e098bf60b277854077cb72669560669835d",
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/constrained-hybrid-replay-v2/4992/historical-hybrid-attribution.json",
    "attribution_file_sha256": "080448cf058ec4d8b52861e0277a892faf2c4534447e435f81ef30a1398438dd",
    "attribution_actual_result_sha256": "a46376477b2bd38b533c17bcfecda80682c40b76f4a890b22a8853fdce552453",
    "result_digest_matches_attribution": false,
    "final_input_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4992-20260831T133000Z/attempts/final-01-20260831T130017731084Z-bebf2946/final-input.json",
    "final_input_file_sha256": "0e6bbba33ee32e3c0c462cc324d361da9b192a865c9cae5c1075defbd63a1e8d",
    "final_input_semantic_sha256": "c04411f4c3818df47352972ef960b5fd2b5d162dce0cd17ef2c76ccf2967961b",
    "probability_input_sha256": "b86f907aa658ebbe40da32ca27132d4dfc9a026b5b4f9808dc3d9b0baa240cb7",
    "feature_manifest_as_of": "2026-08-31T13:00:18.142034Z",
    "feature_to_label_event_id_order_join": "15/15 exact; drawing id verified",
    "label_to_attribution_outcome_join": "15/15 exact"
  },
  {
    "id": 434,
    "drawing_id": 12086,
    "drawing_number": 4993,
    "retrieved_at": "2026-09-02T09:00:05.578334+00:00",
    "ended_at": "2026-09-01T17:00:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "22XX12X2X121XX2",
    "snapshot_sha256": "e4077597b6e6e203fc22967b706b606f0a9f5663cd6e874c171016c1402e6494",
    "result_sha256": "540a4507c0d2677c74f67454422df5ce9cf06dd51f8948d0fcd1c2e4cc45822d",
    "payload_sha256": "d3f8ff3d611216568ace71f64f3c76c6cd997f87b72578eaaeb049558410bcbc",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-09-02T09:00:05.578334+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "review_request_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4993-20260901T140000Z/post-draw/review-request.json",
    "review_request_file_sha256": "de88f3d0cde6699206540e9f072b912585ee892b00876bc1e81b566ef7d9a013",
    "post_draw_state_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4993-20260901T140000Z/post-draw/post-draw-state.json",
    "post_draw_state_file_sha256": "4f7d51bee5721f13e3d03e286c02eeeae85691d3e5cf2b42b5361c50bf16cb18",
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/constrained-hybrid-replay-v2/4993/historical-hybrid-attribution.json",
    "attribution_file_sha256": "0663f44b48eab40fff8ac740e673e391e1e7f3eab7b0bf27e36afa71d9b0725c",
    "attribution_actual_result_sha256": "524f389801403e88e9760efa3668e6e4ff717d9d128bc0c3f32250cad8a18d99",
    "result_digest_matches_attribution": false,
    "final_input_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4993-20260901T140000Z/attempts/final-01-20260901T133011314613Z-c5494668/final-input.json",
    "final_input_file_sha256": "81c892362d9bee025200b2b4d9b3145c24b4d26adf7d9ddaa2ac7ac06468274d",
    "final_input_semantic_sha256": "68e0727c51b8f74b8f85324f37a2c7a70af7fbf6c063cb1c8587d40e3dce55a2",
    "probability_input_sha256": "6c7d4f5a48f4b5eaa825c78d6d87d36cb8ab1e072c493f88ab7e7ca39ab069df",
    "feature_manifest_as_of": "2026-09-01T13:30:13.640481Z",
    "feature_to_label_event_id_order_join": "15/15 exact; drawing id verified",
    "label_to_attribution_outcome_join": "15/15 exact"
  },
  {
    "id": 435,
    "drawing_id": 12089,
    "drawing_number": 4994,
    "retrieved_at": "2026-09-03T09:00:03.651343+00:00",
    "ended_at": "2026-09-02T17:00:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "2X11112222X1XX2",
    "snapshot_sha256": "542d87376940b06d8c4d1890656948a5b7d1d5eed552b24f89a07d7e9bd6bcd5",
    "result_sha256": "7e97226e648e2f42d20ab57310422e40d85b192a67032d02079610c82417afb5",
    "payload_sha256": "20e5ac67fef95707be081bf1a045aa2aca90bdcbf03aec2ee4d60c543e293851",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-09-03T09:00:03.651343+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "review_request_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4994-20260902T140000Z/post-draw/review-request.json",
    "review_request_file_sha256": "e72a6774b75f393e91923fa55432e8081e530a8a03bf50a4cb832ec64c20297b",
    "post_draw_state_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4994-20260902T140000Z/post-draw/post-draw-state.json",
    "post_draw_state_file_sha256": "8f9a9454459de7a2c87c0da8c1bccc0bc33a01c576001b4c53b418ab429886d6",
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/constrained-hybrid-replay-v2/4994/historical-hybrid-attribution.json",
    "attribution_file_sha256": "12458de33dc6d4d8cef818028fca48fc0fafb1a90e3db448f4bd14998fdac6b1",
    "attribution_actual_result_sha256": "c52baec1046c945c3c2e0fb4198f0165969e0ed6fa9fe5d173f037a9ece70134",
    "result_digest_matches_attribution": false,
    "final_input_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4994-20260902T140000Z/attempts/final-01-20260902T133005745430Z-a69ef84f/final-input.json",
    "final_input_file_sha256": "3a721619aaf69daab6e2e6f5b8e078f79bd7216aedc24b284449b619345ff119",
    "final_input_semantic_sha256": "8b0ef0767f6e0c4c56128f32cf6531bc28bf6a84919d7e05ba726a5f04ccacfd",
    "probability_input_sha256": "6c6e58ed793b00eb27ee963d120c86faf6de8fd34d055faaadb65aa7eb7864be",
    "feature_manifest_as_of": "2026-09-02T13:30:06.081128Z",
    "feature_to_label_event_id_order_join": "15/15 exact; drawing id verified",
    "label_to_attribution_outcome_join": "15/15 exact"
  },
  {
    "id": 436,
    "drawing_id": 12092,
    "drawing_number": 4995,
    "retrieved_at": "2026-09-04T09:00:10.969381+00:00",
    "ended_at": "2026-09-03T18:55:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "X2111X1222XX22X",
    "snapshot_sha256": "de34d28e3f53bf1eb7d5d4be9918a03e8d13348b4117a901d914b6396c908154",
    "result_sha256": "ea57eae7a9a9085280f05ebec92ca57fb9436fb8ff806f41f9c607d960cf9cdb",
    "payload_sha256": "93cbdd858bfd08c1e98109f8aedf8ded8b3a59ae1cea58058a96e8e03fb8573f",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-09-04T09:00:10.969381+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "review_request_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4995-20260903T155500Z/post-draw/review-request.json",
    "review_request_file_sha256": "98a94a968065d72bacdd86b367696d34d94f29e11610747b6a0e992657af1f6d",
    "post_draw_state_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4995-20260903T155500Z/post-draw/post-draw-state.json",
    "post_draw_state_file_sha256": "3a6b978b849c8cf8ded3bd0b11c5faa24251921a1c3d7a44e56a73630df5aa2b",
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/4995-equal-input-replay/historical-hybrid-attribution.json",
    "attribution_file_sha256": "580fe4e325f6daee55668acfd43eca4da0e72ede641259f3a77b2207682636a0",
    "attribution_actual_result_sha256": "c625d38f15cf29c41269843294dfa49eeddd31b4c8fdb5623d067e28bb66d43f",
    "result_digest_matches_attribution": false,
    "final_input_path": "/Users/turshevr/toto-ai/reports/rehearsal/evening-4995-20260903T155500Z/attempts/freshness_preflight-01-20260903T145504987711Z-d8fb031e/final-input.json",
    "final_input_file_sha256": "4728899b757f5e75affdc0e2ed5b4bf26fbe1b9db88cc37dd34fe31cc801c1ff",
    "final_input_semantic_sha256": "821a62023469c054cdc1a208ac5ebff67fe17842357d2b2f6d3975fe401edc95",
    "probability_input_sha256": "34e2249650d0fff58f48b16a8de1540aa0e5d504e4a524c3371ee17bfb1711f9",
    "feature_manifest_as_of": "2026-09-03T14:55:12.104098Z",
    "feature_to_label_event_id_order_join": "15/15 exact; drawing id verified",
    "label_to_attribution_outcome_join": "15/15 exact"
  },
  {
    "id": 437,
    "drawing_id": 12096,
    "drawing_number": 4996,
    "retrieved_at": "2026-09-05T09:03:38.395667+00:00",
    "ended_at": "2026-09-04T19:30:00+00:00",
    "complete": 1,
    "event_count": 15,
    "actual": "X222XX2111112X2",
    "snapshot_sha256": "560bb970a2dc11cfd88b492c00237d9df308e9c1fd5d0b276cbe23a6141ff425",
    "result_sha256": "d9909579b1ec01f196d3d12e7dcc21509127b9617d5a2a8dde80dcb66c92f865",
    "payload_sha256": "14ad88281df3a635c94964f45c0a309ad7e3fea4ae28aa7c3cca01fc1553f198",
    "raw_snapshot_sha256": null,
    "results_available_at": "2026-09-05T09:03:38.395667+00:00",
    "time_basis": "Stored drawing_result_snapshots.retrieved_at; not ended_at, kickoff, filename or filesystem mtime",
    "resolved_rows": 15,
    "attribution_path": "/Users/turshevr/toto-ai/reports/research/4996-equal-input-replay/historical-hybrid-attribution.json",
    "attribution_file_sha256": "4fea3350b7024a1d968d4a2c861ff7b31be83ce1c2611a3cef50f00001b97087",
    "attribution_actual_result_sha256": "0cbc706b9667ff370016b56aeccaa92e8bc686519296e544412973ca4f834dbf",
    "result_digest_matches_attribution": false,
    "source_hashes": {
      "final_input_sha256": "fddd407deff8816eb09c3997d79f3bb4f9ffb57360f5d1cd4e1ad338f0205968",
      "package:quality-v2": "f227a5374aba05c758a8d15cf4d4c06b8989f52cf54eced672c371a4d592b27d",
      "package:quality-v3": "ed8f95c78a8d1aa943afeb4a56b049a7121d729d0868e4a7405a9120051995c0",
      "package:robust": "9bc3b159671097718b97011e033c515cfb309be93131bb2ea6a42a58c76b3c40",
      "package:sports-v2": "fc6734ea31459dc9883cceae8fe811105cdf948284d9bad201ea596ec4761e42",
      "probability_input_sha256": "d647aa67eff0d1583fe792b5bbf72f99a88dffc00301855c0fbb4b9bd140e7fb",
      "scheduler_plan_sha256": "c798ade8a64b989518ea54c7c839708f4b1713dbadcb22f9a06f6022db59e045",
      "sports_artifact_sha256": "59c7574b3c7d678e3f689b80d3f47590314c822aad7ab7f14f648bd6c7b57ca2",
      "sports_probability_input_sha256": "41ec6fe4d67e17aa9d9380de2daa7d3495f40e9eb5240e75ec5921848e5a1e54"
    },
    "feature_manifest_extension": "4996 absent from4990–4995manifest; not silently appended or declared training-ready",
    "supporting_status_path": "/Users/turshevr/toto-ai/reports/research/4996-postmortem-automation/retrospective-status.json"
  }
]
```

## Remaining gaps / exact next handoff

Supply these existing timestamped result references to the V3 training input
contract rather than synthesizing labels/times or declaring none exist. A separate
read-only exporter/adapter may be needed if MODELS requires standalone immutable
JSON instead of allowed DB records; none created here. It must bind exact bytes,
drawing/event IDs, result timestamp semantics and the frozen feature/BK manifests.
Any stricter requirement for independently archived raw capture proof remains unmet
by null raw_snapshot_sha256; do not weaken that requirement silently.4996 feature
extension remains separate. No change to training/validation/prospective gates,
primary4998 jobs, consent, authority or scheduler. Context task complete; stop.
